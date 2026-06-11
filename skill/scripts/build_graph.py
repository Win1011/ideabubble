#!/usr/bin/env python3
"""灵感泡泡图谱生成器。

扫描泡泡库里的 .md 文件(文件名即标题,frontmatter 带 created/topics,
正文里的 [[双链]] 是关联),生成一个自包含的交互式 HTML 图谱:
- 图谱视图:力导向布局,可拖拽/缩放,Obsidian 风格
- 时间线视图:按日期分列,跨天关联画弧线
不依赖任何外部库或 CDN,离线可用。

用法: python3 build_graph.py [泡泡库目录] [-o 输出.html]
默认库目录 ~/灵感泡泡,默认输出 <库>/图谱.html
"""

import argparse
import datetime
import html
import json
import re
import sys
from pathlib import Path

LINK_RE = re.compile(r"\[\[([^\]\|#]+)(?:[#|][^\]]*)?\]\]")


def parse_frontmatter(text):
    meta = {}
    body = text
    if text.startswith("---"):
        parts = text.split("\n---", 2)
        if len(parts) >= 2:
            fm = parts[0].lstrip("-\n")
            body = parts[1].lstrip("-").lstrip("\n") if len(parts) == 2 else (
                parts[1].lstrip("-").lstrip("\n")
            )
            # 重新可靠切分:第一行是 ---,找下一个单独成行的 ---
            lines = text.splitlines()
            end = None
            for i, line in enumerate(lines[1:], start=1):
                if line.strip() == "---":
                    end = i
                    break
            if end is not None:
                fm = "\n".join(lines[1:end])
                body = "\n".join(lines[end + 1:]).lstrip("\n")
            for line in fm.splitlines():
                if ":" not in line:
                    continue
                key, _, val = line.partition(":")
                meta[key.strip()] = val.strip()
    return meta, body


def parse_topics(raw):
    if not raw:
        return []
    raw = raw.strip()
    if raw.startswith("[") and raw.endswith("]"):
        raw = raw[1:-1]
    return [t.strip().strip("'\"") for t in raw.split(",") if t.strip().strip("'\"")]


def parse_date(raw, fallback_path):
    if raw:
        m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", raw)
        if m:
            try:
                return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                pass
    ts = fallback_path.stat().st_mtime
    return datetime.date.fromtimestamp(ts)


def body_to_html(body):
    """极简 markdown 渲染:段落、加粗、双链。"""
    text = html.escape(body)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)

    def link_repl(m):
        target = m.group(1).strip()
        return '<a class="wl" data-id="%s">%s</a>' % (html.escape(target, quote=True), html.escape(target))

    text = re.sub(r"\[\[([^\]\|#]+)(?:[#|][^\]]*)?\]\]", link_repl, text)
    paras = [p.strip().replace("\n", "<br>") for p in re.split(r"\n\s*\n", text) if p.strip()]
    return "".join("<p>%s</p>" % p for p in paras)


def collect(vault):
    nodes = {}
    order = []
    for path in sorted(vault.glob("*.md")):
        if path.name.startswith("_"):
            continue
        title = path.stem
        text = path.read_text(encoding="utf-8")
        meta, body = parse_frontmatter(text)
        date = parse_date(meta.get("created"), path)
        topics = parse_topics(meta.get("topics"))
        links = [t.strip() for t in LINK_RE.findall(body) if t.strip() and t.strip() != title]
        nodes[title] = {
            "id": title,
            "date": date.isoformat(),
            "topics": topics,
            "html": body_to_html(body),
            "links": links,
            "ghost": False,
        }
        order.append(title)

    # 未解析的链接 → 幽灵泡泡
    for title in list(order):
        for target in nodes[title]["links"]:
            if target not in nodes:
                nodes[target] = {
                    "id": target, "date": None, "topics": [],
                    "html": "<p class='ghost-hint'>还没展开的想法——下次聊聊它?</p>",
                    "links": [], "ghost": True,
                }
                order.append(target)

    index = {t: i for i, t in enumerate(order)}
    edge_set = set()
    for title in order:
        for target in nodes[title]["links"]:
            a, b = index[title], index[target]
            edge_set.add((min(a, b), max(a, b)))

    topic_order = []
    for t in order:
        for tp in nodes[t]["topics"]:
            if tp not in topic_order:
                topic_order.append(tp)

    return {
        "nodes": [nodes[t] for t in order],
        "edges": sorted(edge_set),
        "topics": topic_order,
        "generated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>灵感泡泡</title>
<style>
:root {
  --bg: #16161e; --panel: #1f1f2b; --line: #34344a;
  --text: #d8d8e8; --dim: #8a8aa3; --accent: #a78bfa;
}
* { box-sizing: border-box; margin: 0; }
body { background: var(--bg); color: var(--text); font: 14px/1.6 -apple-system, "PingFang SC", sans-serif; overflow: hidden; }
header { position: fixed; top: 0; left: 0; right: 0; z-index: 10; display: flex; align-items: center; gap: 16px;
  padding: 10px 18px; background: rgba(22,22,30,.85); backdrop-filter: blur(8px); border-bottom: 1px solid var(--line); }
header h1 { font-size: 16px; font-weight: 600; }
#stats { color: var(--dim); font-size: 12px; }
.tabs { margin-left: auto; display: flex; gap: 4px; }
.tabs button { background: none; border: 1px solid var(--line); color: var(--dim); padding: 4px 14px;
  border-radius: 999px; cursor: pointer; font-size: 13px; }
.tabs button.on { color: #fff; border-color: var(--accent); background: rgba(167,139,250,.15); }
#view-graph, #view-timeline { position: fixed; inset: 0; padding-top: 49px; }
#cv { width: 100%; height: 100%; display: block; cursor: grab; }
#view-timeline { overflow: auto; }
#view-timeline svg { display: block; }
.legend { position: fixed; left: 14px; bottom: 14px; z-index: 10; display: flex; flex-wrap: wrap; gap: 6px 12px;
  max-width: 50vw; font-size: 12px; color: var(--dim); }
.legend span { display: inline-flex; align-items: center; gap: 5px; }
.legend i { width: 9px; height: 9px; border-radius: 50%; display: inline-block; }
#panel { position: fixed; top: 49px; right: 0; bottom: 0; width: 340px; max-width: 88vw; z-index: 11;
  background: var(--panel); border-left: 1px solid var(--line); padding: 20px; overflow-y: auto;
  transform: translateX(100%); transition: transform .22s ease; }
#panel.open { transform: none; }
#panel .close { position: absolute; top: 10px; right: 12px; background: none; border: none; color: var(--dim);
  font-size: 18px; cursor: pointer; }
#panel h2 { font-size: 17px; margin-bottom: 6px; padding-right: 24px; }
#panel .meta { color: var(--dim); font-size: 12px; margin-bottom: 12px; display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
#panel .chip { border: 1px solid var(--line); border-radius: 999px; padding: 1px 9px; font-size: 11px; }
#panel .body p { margin-bottom: 10px; }
#panel .links { margin-top: 14px; border-top: 1px solid var(--line); padding-top: 10px; }
#panel .links h3 { font-size: 12px; color: var(--dim); font-weight: 500; margin-bottom: 6px; }
a.wl { color: var(--accent); cursor: pointer; text-decoration: none; border-bottom: 1px dashed rgba(167,139,250,.5); }
.ghost-hint { color: var(--dim); font-style: italic; }
#empty { position: fixed; inset: 0; display: flex; align-items: center; justify-content: center; color: var(--dim); }
</style>
</head>
<body>
<header>
  <h1>🫧 灵感泡泡</h1>
  <span id="stats"></span>
  <div class="tabs">
    <button id="tab-graph" class="on">图谱</button>
    <button id="tab-timeline">时间线</button>
  </div>
</header>
<div id="view-graph"><canvas id="cv"></canvas></div>
<div id="view-timeline" hidden></div>
<div class="legend" id="legend"></div>
<aside id="panel">
  <button class="close" id="panel-close">×</button>
  <h2 id="p-title"></h2>
  <div class="meta" id="p-meta"></div>
  <div class="body" id="p-body"></div>
  <div class="links" id="p-links"></div>
</aside>
<script>
const DATA = __DATA__;
const PALETTE = ['#a78bfa','#7dd3fc','#fda4af','#86efac','#fcd34d','#f9a8d4','#93c5fd','#fdba74','#5eead4','#c4b5fd'];
const topicColor = {};
DATA.topics.forEach((t,i)=>topicColor[t]=PALETTE[i%PALETTE.length]);
const GHOST = '#55556e', PLAIN = '#9d9db8';

const N = DATA.nodes, E = DATA.edges;
const deg = N.map(()=>0);
E.forEach(([a,b])=>{deg[a]++;deg[b]++;});
N.forEach((n,i)=>{
  n.idx=i; n.degree=deg[i];
  n.r = n.ghost ? 4.5 : 7 + 3*Math.sqrt(deg[i]);
  n.color = n.ghost ? GHOST : (n.topics.length ? topicColor[n.topics[0]] : PLAIN);
});
const byId = {}; N.forEach(n=>byId[n.id]=n);
const days = [...new Set(N.filter(n=>n.date).map(n=>n.date))].sort();
document.getElementById('stats').textContent =
  N.filter(n=>!n.ghost).length + ' 个泡泡 · ' + E.length + ' 条关联 · 跨 ' + days.length + ' 天';

// 图例
const lg = document.getElementById('legend');
lg.innerHTML = DATA.topics.map(t=>'<span><i style="background:'+topicColor[t]+'"></i>'+t+'</span>').join('')
  + (N.some(n=>n.ghost) ? '<span><i style="background:'+GHOST+'"></i>幽灵泡泡(还没展开)</span>' : '');

if (!N.length) {
  document.body.insertAdjacentHTML('beforeend','<div id="empty">还没有泡泡——去找 Claude 聊一场吧 🫧</div>');
}

// ---------- 详情面板 ----------
const panel = document.getElementById('panel');
let selected = null;
function openPanel(n){
  selected = n;
  document.getElementById('p-title').textContent = n.id;
  document.getElementById('p-meta').innerHTML =
    (n.date ? '<span>'+n.date+'</span>' : '<span>幽灵泡泡</span>') +
    n.topics.map(t=>'<span class="chip" style="border-color:'+topicColor[t]+';color:'+topicColor[t]+'">'+t+'</span>').join('');
  document.getElementById('p-body').innerHTML = n.html;
  const nbrs = [];
  E.forEach(([a,b])=>{ if(a===n.idx) nbrs.push(N[b]); else if(b===n.idx) nbrs.push(N[a]); });
  document.getElementById('p-links').innerHTML = nbrs.length
    ? '<h3>关联泡泡</h3>' + nbrs.map(m=>'<div><a class="wl" data-id="'+m.id.replace(/"/g,'&quot;')+'">'+m.id+'</a></div>').join('')
    : '';
  panel.classList.add('open');
  draw();
}
document.getElementById('panel-close').onclick = ()=>{ panel.classList.remove('open'); selected=null; draw(); };
document.addEventListener('click', e=>{
  const a = e.target.closest('a.wl');
  if (a && byId[a.dataset.id]) { openPanel(byId[a.dataset.id]); centerOn(byId[a.dataset.id]); }
});

// ---------- 力导向图 ----------
const cv = document.getElementById('cv');
const ctx = cv.getContext('2d');
let W=0, H=0, dpr=1;
function resize(){
  dpr = window.devicePixelRatio||1;
  W = cv.clientWidth; H = cv.clientHeight;
  cv.width = W*dpr; cv.height = H*dpr;
  draw();
}
window.addEventListener('resize', resize);

N.forEach((n,i)=>{
  const a = i*2.399963, r = 30*Math.sqrt(i+1);
  n.x = Math.cos(a)*r; n.y = Math.sin(a)*r;
  n.vx=0; n.vy=0; n.fixed=false;
});
let alpha = 1;
const view = { x:0, y:0, k:1 };   // 世界原点在画布中心,再加偏移和缩放

function tick(){
  if (alpha > 0.003 && N.length) {
    alpha *= 0.985;
    const rep = 3600, spring = 0.03, len = 135, grav = 0.008;
    for (let i=0;i<N.length;i++){
      for (let j=i+1;j<N.length;j++){
        const a=N[i], b=N[j];
        let dx=b.x-a.x, dy=b.y-a.y;
        let d2 = dx*dx+dy*dy || 1;
        if (d2 < 360000) {
          const f = rep/d2 * alpha;
          const d = Math.sqrt(d2);
          dx/=d; dy/=d;
          a.vx -= dx*f; a.vy -= dy*f;
          b.vx += dx*f; b.vy += dy*f;
        }
      }
    }
    E.forEach(([ia,ib])=>{
      const a=N[ia], b=N[ib];
      const dx=b.x-a.x, dy=b.y-a.y;
      const d = Math.sqrt(dx*dx+dy*dy)||1;
      const f = spring*(d-len)*alpha;
      a.vx += dx/d*f; a.vy += dy/d*f;
      b.vx -= dx/d*f; b.vy -= dy/d*f;
    });
    N.forEach(n=>{
      n.vx -= n.x*grav*alpha; n.vy -= n.y*grav*alpha;
      if (!n.fixed){ n.x += n.vx; n.y += n.vy; }
      n.vx *= 0.85; n.vy *= 0.85;
    });
    draw();
  }
  requestAnimationFrame(tick);
}

function toScreen(p){ return { x: W/2 + (p.x+view.x)*view.k, y: H/2 + (p.y+view.y)*view.k }; }
function toWorld(sx,sy){ return { x:(sx-W/2)/view.k - view.x, y:(sy-H/2)/view.k - view.y }; }

function draw(){
  ctx.setTransform(dpr,0,0,dpr,0,0);
  ctx.clearRect(0,0,W,H);
  const nbr = new Set();
  if (selected) E.forEach(([a,b])=>{
    if(a===selected.idx){nbr.add(b);} if(b===selected.idx){nbr.add(a);}
  });
  ctx.lineWidth = 1;
  E.forEach(([ia,ib])=>{
    const a=toScreen(N[ia]), b=toScreen(N[ib]);
    const hot = selected && (ia===selected.idx || ib===selected.idx);
    ctx.strokeStyle = hot ? 'rgba(167,139,250,.7)' : 'rgba(120,120,160,'+(selected?'.10':'.28')+')';
    ctx.beginPath(); ctx.moveTo(a.x,a.y); ctx.lineTo(b.x,b.y); ctx.stroke();
  });
  N.forEach(n=>{
    const p = toScreen(n);
    const dimmed = selected && n!==selected && !nbr.has(n.idx);
    ctx.globalAlpha = dimmed ? 0.25 : 1;
    ctx.beginPath();
    ctx.arc(p.x, p.y, n.r*Math.min(view.k,1.6), 0, 7);
    ctx.fillStyle = n.color;
    if (n.ghost){ ctx.setLineDash([3,3]); ctx.strokeStyle=GHOST; ctx.lineWidth=1.2; ctx.stroke(); ctx.setLineDash([]);
      ctx.globalAlpha *= .5; ctx.fill(); ctx.globalAlpha = dimmed?0.25:1; }
    else ctx.fill();
    if (n===selected){ ctx.strokeStyle='#fff'; ctx.lineWidth=1.5; ctx.stroke(); }
    if (view.k > 0.45 || n===selected || nbr.has(n.idx)){
      ctx.fillStyle = dimmed ? 'rgba(160,160,185,.4)' : '#c9c9dd';
      ctx.font = '11px -apple-system, "PingFang SC", sans-serif';
      ctx.textAlign='center';
      ctx.fillText(n.id, p.x, p.y + n.r*Math.min(view.k,1.6) + 13);
    }
    ctx.globalAlpha = 1;
  });
}

function hit(sx,sy){
  for (let i=N.length-1;i>=0;i--){
    const p = toScreen(N[i]);
    const r = N[i].r*Math.min(view.k,1.6)+5;
    if ((sx-p.x)**2+(sy-p.y)**2 < r*r) return N[i];
  }
  return null;
}
function centerOn(n){
  if (n.x===undefined) return;
  view.x = -n.x; view.y = -n.y;
  draw();
}

let dragNode=null, panning=false, last=null, moved=false;
cv.addEventListener('mousedown', e=>{
  const n = hit(e.offsetX, e.offsetY);
  moved=false; last={x:e.offsetX,y:e.offsetY};
  if (n){ dragNode=n; n.fixed=true; }
  else panning=true;
});
window.addEventListener('mousemove', e=>{
  if(!last) return;
  const r = cv.getBoundingClientRect();
  const sx = e.clientX-r.left, sy=e.clientY-r.top;
  const dx = sx-last.x, dy = sy-last.y;
  if (Math.abs(dx)+Math.abs(dy)>2) moved=true;
  if (dragNode){
    const w = toWorld(sx,sy);
    dragNode.x=w.x; dragNode.y=w.y; alpha=Math.max(alpha,0.25); draw();
  } else if (panning){
    view.x += dx/view.k; view.y += dy/view.k; draw();
  }
  last={x:sx,y:sy};
});
window.addEventListener('mouseup', e=>{
  if (dragNode){ dragNode.fixed=false; if(!moved) openPanel(dragNode); }
  else if (panning && !moved && e.target===cv){ panel.classList.remove('open'); selected=null; draw(); }
  dragNode=null; panning=false; last=null;
});
cv.addEventListener('wheel', e=>{
  e.preventDefault();
  const before = toWorld(e.offsetX, e.offsetY);
  view.k = Math.min(4, Math.max(0.15, view.k * Math.exp(-e.deltaY*0.0015)));
  const after = toWorld(e.offsetX, e.offsetY);
  view.x += after.x-before.x; view.y += after.y-before.y;
  draw();
}, {passive:false});

// ---------- 时间线 ----------
let tlBuilt = false;
function buildTimeline(){
  if (tlBuilt) return; tlBuilt = true;
  const wrap = document.getElementById('view-timeline');
  const dated = N.filter(n=>n.date);
  if (!dated.length){ wrap.innerHTML='<div style="padding:60px;color:var(--dim)">还没有泡泡</div>'; return; }
  const cols = {};
  days.forEach((d,i)=>cols[d]=i);
  const stack = days.map(()=>0);
  const colW=170, rowH=64, top=80, leftPad=60;
  dated.forEach(n=>{
    const c = cols[n.date];
    n.tx = leftPad + c*colW + colW/2;
    n.ty = top + (stack[c]++)*rowH + 40;
  });
  const width = leftPad*2 + days.length*colW;
  const height = top + Math.max(...stack, 1)*rowH + 80;
  let svg = '<svg id="tl" width="'+width+'" height="'+height+'" xmlns="http://www.w3.org/2000/svg">';
  // 列标题和分隔
  days.forEach((d,i)=>{
    const x = leftPad + i*colW + colW/2;
    svg += '<text x="'+x+'" y="34" text-anchor="middle" fill="#8a8aa3" font-size="12">'+d+'</text>';
    if (i) svg += '<line x1="'+(leftPad+i*colW)+'" y1="50" x2="'+(leftPad+i*colW)+'" y2="'+(height-20)+'" stroke="#26263a" stroke-dasharray="2,5"/>';
  });
  // 弧线
  E.forEach(([ia,ib])=>{
    const a=N[ia], b=N[ib];
    if (a.tx===undefined || b.tx===undefined) return;
    if (a.date===b.date){
      const x=a.tx, y1=Math.min(a.ty,b.ty), y2=Math.max(a.ty,b.ty);
      svg += '<path d="M '+x+' '+y1+' C '+(x-46)+' '+y1+', '+(x-46)+' '+y2+', '+x+' '+y2+'" fill="none" stroke="rgba(120,120,160,.3)"/>';
    } else {
      const [l,r2] = a.tx<b.tx ? [a,b] : [b,a];
      const mx=(l.tx+r2.tx)/2, my=Math.min(l.ty,r2.ty)-34;
      svg += '<path d="M '+l.tx+' '+l.ty+' Q '+mx+' '+my+', '+r2.tx+' '+r2.ty+'" fill="none" stroke="rgba(167,139,250,.35)" stroke-width="1.2"/>';
    }
  });
  // 节点
  dated.forEach(n=>{
    const label = n.id.length>10 ? n.id.slice(0,10)+'…' : n.id;
    svg += '<g class="tl-node" data-idx="'+n.idx+'" style="cursor:pointer">'
      + '<circle cx="'+n.tx+'" cy="'+n.ty+'" r="'+Math.min(n.r,13)+'" fill="'+n.color+'"/>'
      + '<text x="'+n.tx+'" y="'+(n.ty+Math.min(n.r,13)+15)+'" text-anchor="middle" fill="#c9c9dd" font-size="11">'
      + label.replace(/&/g,'&amp;').replace(/</g,'&lt;') + '</text></g>';
  });
  svg += '</svg>';
  wrap.innerHTML = svg;
  wrap.querySelectorAll('.tl-node').forEach(g=>{
    g.addEventListener('click', ()=>openPanel(N[+g.dataset.idx]));
  });
}

// ---------- 标签切换 ----------
const vg = document.getElementById('view-graph'), vt = document.getElementById('view-timeline');
const tg = document.getElementById('tab-graph'), tt = document.getElementById('tab-timeline');
tg.onclick = ()=>{ vg.hidden=false; vt.hidden=true; tg.classList.add('on'); tt.classList.remove('on'); resize(); };
tt.onclick = ()=>{ vg.hidden=true; vt.hidden=false; tt.classList.add('on'); tg.classList.remove('on'); buildTimeline(); };

resize();
tick();
</script>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser(description="生成灵感泡泡图谱")
    ap.add_argument("vault", nargs="?", default=str(Path.home() / "灵感泡泡"))
    ap.add_argument("-o", "--output", default=None)
    args = ap.parse_args()

    vault = Path(args.vault).expanduser()
    vault.mkdir(parents=True, exist_ok=True)
    data = collect(vault)

    out = Path(args.output) if args.output else vault / "图谱.html"
    html_text = TEMPLATE.replace("__DATA__", json.dumps(data, ensure_ascii=False))
    out.write_text(html_text, encoding="utf-8")

    real = sum(1 for n in data["nodes"] if not n["ghost"])
    ghosts = len(data["nodes"]) - real
    day_count = len({n["date"] for n in data["nodes"] if n["date"]})
    print(f"🫧 {real} 个泡泡(+{ghosts} 个幽灵) · {len(data['edges'])} 条关联 · 跨 {day_count} 天")
    print(f"图谱已生成:{out}")


if __name__ == "__main__":
    main()
