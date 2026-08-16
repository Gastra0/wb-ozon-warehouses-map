#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rebuilds index.html from wh_data.json.
Self-contained: downloads Russia GeoJSON, projects it, lays out markers, writes HTML.
"""
import json, math, random, urllib.request, re, sys, os

random.seed(31)

# ── Load data ──────────────────────────────────────────────────────────────
DATA = json.load(open("wh_data.json", encoding="utf-8"))
W    = DATA["warehouses"]
UPDATED = DATA.get("last_updated", "")

# ── Albers projection ──────────────────────────────────────────────────────
lat0, lon0 = math.radians(56), math.radians(100)
p1,   p2   = math.radians(50), math.radians(68)
n_  = 0.5*(math.sin(p1)+math.sin(p2))
C   = math.cos(p1)**2 + 2*n_*math.sin(p1)
rho0 = math.sqrt(C - 2*n_*math.sin(lat0))/n_

def alb(lon, lat):
    if lon < -20: lon += 360
    lam, phi = math.radians(lon), math.radians(lat)
    rho = math.sqrt(C - 2*n_*math.sin(phi))/n_
    return rho*math.sin(n_*(lam-lon0)), rho0 - rho*math.cos(n_*(lam-lon0))

# fetch Russia outline
url = "https://raw.githubusercontent.com/johan/world.geo.json/master/countries/RUS.geo.json"
try:
    gj = json.load(urllib.request.urlopen(url, timeout=15))
    print("GeoJSON: fetched")
except Exception as e:
    print(f"GeoJSON fetch failed: {e}"); sys.exit(1)

geom  = gj["features"][0]["geometry"]
polys = geom["coordinates"] if geom["type"]=="MultiPolygon" else [geom["coordinates"]]
axs=[]; ays=[]
for poly in polys:
    for ring in poly:
        for c in ring: x,y=alb(c[0],c[1]); axs.append(x); ays.append(y)
minx,maxx,miny,maxy = min(axs),max(axs),min(ays),max(ays)
Wd,Hd,PAD = 1400,720,24
s  = min((Wd-2*PAD)/(maxx-minx),(Hd-2*PAD)/(maxy-miny))
ox = PAD+((Wd-2*PAD)-(maxx-minx)*s)/2
oy = PAD+((Hd-2*PAD)-(maxy-miny)*s)/2
def sv(x,y): return ox+(x-minx)*s, oy+(maxy-y)*s

# outline path
rings=[]
for poly in polys:
    for ring in poly:
        pts=[sv(*alb(c[0],c[1])) for c in ring]
        if len(pts)<4: continue
        xs=[p[0] for p in pts]; ys=[p[1] for p in pts]
        if (max(xs)-min(xs))<3 and (max(ys)-min(ys))<3: continue
        rings.append(((max(xs)-min(xs))*(max(ys)-min(ys)), pts))
rings.sort(key=lambda t:-t[0])
PATH = "".join("M"+"L".join(f"{x:.1f} {y:.1f}" for x,y in pts)+"Z" for _,pts in rings)

# ── Radii ──────────────────────────────────────────────────────────────────
TIER_R = {"hub":8.0,"large":5.8,"mid":4.2}
def area_r(m2): return max(4.0, min(9.5, 0.019*math.sqrt(m2)))

for w in W:
    x,y = sv(*alb(w["lng"], w["lat"]))
    w["tx"],w["ty"] = x,y
    m2 = w.get("area_m2")
    w["r"] = round(area_r(m2) if m2 else TIER_R.get(w.get("tier","mid"), 5.8), 2)

# ── Group clusters ─────────────────────────────────────────────────────────
def grp(w):
    reg = w.get("region","")
    if reg in ("Московська обл.","Нова Москва"): return "msk"
    if reg in ("Ленінградська обл.","Санкт-Петербург"): return "spb"
    if reg == "Тульська обл.": return "tula"
    if reg == "Татарстан": return "tat"
    return None
LABEL = {"msk":"Московська обл.","spb":"СПб і Ленобл.","tula":"Тульська обл.","tat":"Татарстан"}
GAP = 3.5

buckets={}
for w in W:
    k=grp(w)
    if k: buckets.setdefault(k,[]).append(w)
buckets = {k:v for k,v in buckets.items() if len(v)>1}
grouped = {id(w) for v in buckets.values() for w in v}
singles = [w for w in W if id(w) not in grouped]

for k,mem in buckets.items():
    cx=sum(w["tx"] for w in mem)/len(mem); cy=sum(w["ty"] for w in mem)/len(mem)
    for i,w in enumerate(mem):
        a=i*2.399; rad=6+3.4*math.sqrt(i)
        w["x"]=cx+rad*math.cos(a); w["y"]=cy+rad*math.sin(a)
    for _ in range(2000):
        mv=False
        for i in range(len(mem)):
            for j in range(i+1,len(mem)):
                a,b=mem[i],mem[j]; dx,dy=b["x"]-a["x"],b["y"]-a["y"]; dd=math.hypot(dx,dy) or .01
                need=a["r"]+b["r"]+GAP
                if dd<need:
                    p=(need-dd)/2*.7; ux,uy=dx/dd,dy/dd
                    a["x"]-=ux*p; a["y"]-=uy*p; b["x"]+=ux*p; b["y"]+=uy*p; mv=True
        for w in mem: w["x"]+=(cx-w["x"])*.05; w["y"]+=(cy-w["y"])*.05
        if not mv: break
for w in singles: w["x"],w["y"]=w["tx"],w["ty"]

units=[]
CW,LH=5.7,15.5
for k,mem in buckets.items():
    cx=sum(w["x"] for w in mem)/len(mem); cy=sum(w["y"] for w in mem)/len(mem)
    pad=7; hw=max(abs(w["x"]-cx)+w["r"] for w in mem)+pad; hh=max(abs(w["y"]-cy)+w["r"] for w in mem)+pad
    units.append({"kind":"group","key":k,"label":LABEL[k],
                  "sub":f'{len(mem)} складів · WB',"cx":cx,"cy":cy,"tcx":cx,"tcy":cy,
                  "hw":hw,"hh":hh,"lw":len(LABEL[k])*6.1+12,"lh":26,"side":1,
                  "off":[(w["x"]-cx,w["y"]-cy) for w in mem]})
for w in singles:
    units.append({"kind":"single","label":w["name"],"cx":w["tx"],"cy":w["ty"],
                  "tcx":w["tx"],"tcy":w["ty"],"hw":w["r"]+2,"hh":w["r"]+2,
                  "lw":len(w["name"])*5.7+9,"lh":LH,"side":1})

def ubox(u):
    gap=u["hw"]+5
    x0,x1=(u["cx"]-u["hw"],u["cx"]+gap+u["lw"]) if u["side"]>0 else (u["cx"]-gap-u["lw"],u["cx"]+u["hw"])
    h=max(u["hh"],u["lh"]/2); return[x0,u["cy"]-h,x1,u["cy"]+h]
def ovl(A,B,p=0): return(min(A[2],B[2])-max(A[0],B[0])+p>0)and(min(A[3],B[3])-max(A[1],B[1])+p>0)

for it in range(5000):
    if it%70==30:
        for u in units:
            base=flip=0; b0=ubox(u); u["side"]*=-1; b1=ubox(u); u["side"]*=-1
            for o in units:
                if o is u: continue
                ob=ubox(o)
                if ovl(b0,ob,2.5): base+=1
                if ovl(b1,ob,2.5): flip+=1
            if flip<base: u["side"]*=-1
    mv=False
    for i in range(len(units)):
        for j in range(i+1,len(units)):
            a,b=units[i],units[j]; A,B=ubox(a),ubox(b)
            oxx=min(A[2],B[2])-max(A[0],B[0])+2.5; oyy=min(A[3],B[3])-max(A[1],B[1])+2.5
            if oxx>0 and oyy>0:
                mv=True
                if oyy<=oxx:
                    p=oyy/2*.6
                    if a["cy"]<b["cy"]: a["cy"]-=p; b["cy"]+=p
                    else: a["cy"]+=p; b["cy"]-=p
                else:
                    p=oxx/2*.6
                    if a["cx"]<b["cx"]: a["cx"]-=p; b["cx"]+=p
                    else: a["cx"]+=p; b["cx"]-=p
    for u in units:
        if it<3000: u["cx"]+=(u["tcx"]-u["cx"])*.018; u["cy"]+=(u["tcy"]-u["cy"])*.018
        u["cx"]=max(80,min(1320,u["cx"])); u["cy"]=max(22,min(698,u["cy"]))
    if not mv and it>600: break

grp_map={k:mem for k,mem in buckets.items()}
for u in units:
    if u["kind"]=="group":
        mem=grp_map[u["key"]]
        for w,(dx,dy) in zip(mem,u["off"]): w["x"]=round(u["cx"]+dx,1); w["y"]=round(u["cy"]+dy,1)
    else:
        nxt=[x for x in W if x["name"]==u["label"]]
        if nxt: nxt[0]["x"]=round(u["cx"],1); nxt[0]["y"]=round(u["cy"],1)

# ── SVG inner ──────────────────────────────────────────────────────────────
def esc(s): return(s or "").replace("&","&amp;").replace('"',"&quot;").replace("<","&lt;").replace(">","&gt;")
FO="M0 -8.2 C 2.4 -4.6, 5.6 -2.6, 5.6 1.4 C 5.6 5, 3.1 7.6, 0 7.6 C -3.1 7.6, -5.6 5, -5.6 1.4 C -5.6 -1.4, -2.6 -2.4, -1.1 -5 C -0.7 -6.2, -0.25 -7.3, 0 -8.2 Z"
FI="M0 -2.1 C 1.5 0.1, 2.9 1.3, 2.9 3.1 C 2.9 5, 1.6 6.2, 0 6.2 C -1.6 6.2, -2.9 5, -2.9 3.1 C -2.9 1.6, -1 0.9, 0 -2.1 Z"
FH=15.8
boxes,glabs,marks,fires,labs=[],[],[],[],[]
for u in units:
    if u["kind"]!="group": continue
    k=u["key"]; x0,y0=u["cx"]-u["hw"],u["cy"]-u["hh"]
    boxes.append(f'<rect class="gbox" x="{x0:.1f}" y="{y0:.1f}" width="{2*u["hw"]:.1f}" height="{2*u["hh"]:.1f}" rx="12"/>')
    if u["side"]>0: lx,an,t1,t2=u["cx"]+u["hw"]+11,"start",u["cx"]+u["hw"],u["cx"]+u["hw"]+9
    else:           lx,an,t1,t2=u["cx"]-u["hw"]-11,"end",u["cx"]-u["hw"],u["cx"]-u["hw"]-9
    boxes.append(f'<line class="gtick" x1="{t1:.1f}" y1="{u["cy"]:.1f}" x2="{t2:.1f}" y2="{u["cy"]:.1f}"/>')
    if k=="msk":
        glabs += [f'<text class="glbl" x="{lx:.1f}" y="{u["cy"]-1:.1f}" text-anchor="{an}">{esc(u["label"])}</text>',
                  f'<text class="gsub" x="{lx:.1f}" y="{u["cy"]+11:.1f}" text-anchor="{an}">{esc(u["sub"])}</text>']
    else:
        glabs.append(f'<text class="glbl" x="{lx:.1f}" y="{u["cy"]+4.2:.1f}" text-anchor="{an}">{esc(u["label"])}</text>')

for w in W:
    st,r=w["status"],w["r"]
    ring=(f'<circle class="ring burned" r="{r+4.6:.1f}"/>' if st=="burned" else
          f'<circle class="ring hit" r="{r+4.6:.1f}"/>' if st=="hit" else "")
    attrs=(f'data-n="{esc(w["name"])}" data-r="{esc(w["region"])}" data-tier="{w.get("tier","mid")}" '
           f'data-status="{st}" data-area="{esc(w.get("area",""))}" data-date="{esc(w.get("date",""))}" '
           f'data-note="{esc(w.get("note",""))}"')
    marks.append(f'<g class="pt wb s-{st}" {attrs} transform="translate({w["x"]} {w["y"]})">'
                 f'<circle class="halo" r="{r+5.5:.1f}"/>{ring}<circle class="dot" r="{r:.1f}"/>'
                 f'<circle class="hita" r="{r+8:.1f}"/></g>')
    if st=="burned":
        sc=(2*r*0.86)/FH
        fires.append(f'<g class="fire" transform="translate({w["x"]} {w["y"]}) scale({sc:.3f})">'
                     f'<path class="fout" d="{FO}"/><path class="fin" d="{FI}"/></g>')
for u in units:
    if u["kind"]!="single": continue
    wlist=[x for x in W if x["name"]==u["label"]]
    if not wlist: continue
    w=wlist[0]; gap=w["r"]+5
    lx,an=(w["x"]+gap,"start") if u["side"]>0 else (w["x"]-gap,"end")
    labs.append(f'<text class="lbl wb s-{w["status"]}" x="{lx:.1f}" y="{w["y"]+3.9:.1f}" text-anchor="{an}">{esc(w["name"])}</text>')

INNER="".join(boxes)+"".join(marks)+"".join(fires)+"".join(labs)+"".join(glabs)

# counts
total   = len(W)
burned  = sum(1 for w in W if w["status"]=="burned")
hit     = sum(1 for w in W if w["status"]=="hit")

# ── HTML template ──────────────────────────────────────────────────────────
HTML = f"""<!DOCTYPE html>
<html lang="uk">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Склади Wildberries у РФ</title>
<style>
  :root{{--wb:#d1247f;--fire:#e0402a;--amber:#dd8b1a;--paper:#edf0f6;--paper2:#f8fafd;
    --land:#dee4ef;--land-line:#a8b4cc;--land-glow:rgba(150,170,210,.32);
    --panel:rgba(255,255,255,.9);--stroke:rgba(30,45,80,.13);--ink:#1b2334;--muted:#6a7590;
    --mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace;
    --sans:"Segoe UI",system-ui,-apple-system,Roboto,Helvetica,Arial,sans-serif;}}
  *{{box-sizing:border-box}}html,body{{height:100%;margin:0}}
  body{{background:radial-gradient(140% 100% at 22% -10%,var(--paper2) 0%,var(--paper) 55%,#e2e7f1 100%);
    color:var(--ink);font-family:var(--sans);overflow:hidden}}
  .wrap{{position:relative;width:100%;height:100%}}
  svg.map{{position:absolute;inset:0;width:100%;height:100%;display:block;cursor:grab;touch-action:none}}
  svg.map.drag{{cursor:grabbing}}
  .glow-land{{fill:none;stroke:var(--land-glow);stroke-width:6}}
  .land{{fill:var(--land);stroke:var(--land-line);stroke-width:.8;stroke-linejoin:round}}
  .pt{{cursor:pointer}}.pt .hita{{fill:transparent}}
  .pt .dot{{fill:var(--wb);stroke:#fff;stroke-width:1.5;transition:transform .14s ease}}
  .pt.s-burned .dot{{fill:#3a3340;stroke:var(--fire);stroke-width:1.9}}
  .halo{{fill:none;stroke:#39415a;stroke-width:1.5;opacity:0;transition:opacity .15s}}
  .pt:hover .halo,.pt.sel .halo{{opacity:.8}}
  .pt:hover .dot,.pt.sel .dot{{transform:scale(1.16)}}
  .ring{{fill:none;stroke-width:2}}
  .ring.burned{{stroke:var(--fire);animation:throb 2.4s ease-in-out infinite}}
  .ring.hit{{stroke:var(--amber);stroke-dasharray:3.5 3.5}}
  @keyframes throb{{0%,100%{{opacity:.95}}50%{{opacity:.4}}}}
  .pt:focus{{outline:none}}.pt:focus-visible .halo{{opacity:.9;stroke-dasharray:3 2}}
  .fire{{pointer-events:none;animation:flick 1.9s ease-in-out infinite}}
  .fout{{fill:#ff7a3d;stroke:rgba(255,255,255,.55);stroke-width:.9;paint-order:stroke;stroke-linejoin:round}}
  .fin{{fill:#ffd83f}}
  @keyframes flick{{0%,100%{{opacity:1}}50%{{opacity:.72}}}}
  .lbl{{font-size:11px;font-weight:600;pointer-events:none;fill:#36415c;
    paint-order:stroke;stroke:rgba(247,249,253,.94);stroke-width:3;stroke-linejoin:round}}
  .lbl.s-burned{{fill:#b8321f}}.lbl.s-hit{{fill:#a86a0d}}
  .gbox{{fill:rgba(255,255,255,.34);stroke:#8b98b5;stroke-width:1.1;stroke-dasharray:4 3}}
  .gtick{{stroke:#8b98b5;stroke-width:1;stroke-dasharray:3 2.5}}
  .glbl{{font-size:12px;font-weight:700;fill:#313c55;pointer-events:none;
    paint-order:stroke;stroke:rgba(247,249,253,.94);stroke-width:3.2;stroke-linejoin:round}}
  .gsub{{font-size:10px;font-weight:600;fill:#75809b;font-family:var(--mono);pointer-events:none;
    paint-order:stroke;stroke:rgba(247,249,253,.94);stroke-width:3;stroke-linejoin:round}}
  .panel{{position:absolute;top:20px;left:20px;width:264px;max-width:calc(100vw - 40px);
    background:var(--panel);border:1px solid var(--stroke);border-radius:16px;
    backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px);
    box-shadow:0 20px 48px -22px rgba(30,45,80,.4);padding:17px}}
  .eyebrow{{font-family:var(--mono);font-size:10px;letter-spacing:.16em;text-transform:uppercase;
    color:var(--muted);margin-bottom:8px}}
  h1{{font-size:20px;line-height:1.2;margin:0 0 14px;font-weight:700;letter-spacing:-.2px}}
  h1 .a{{color:var(--wb)}}
  .bt{{font-family:var(--mono);font-size:9.5px;letter-spacing:.13em;text-transform:uppercase;
    color:var(--muted);margin:0 0 8px}}
  .legend{{display:flex;flex-direction:column;gap:8px}}
  .row{{display:flex;align-items:center;gap:9px;font-size:12.5px}}
  .sw{{width:11px;height:11px;border-radius:50%;flex:none}}
  .sw.wb{{background:var(--wb)}}.sw.ra{{background:var(--wb);box-shadow:0 0 0 2px var(--amber)}}
  .fico{{width:11px;flex:none;font-size:12px;line-height:1;text-align:center}}
  .num{{margin-left:auto;font-family:var(--mono);font-size:13.5px;font-weight:700}}
  .num.wb{{color:var(--wb)}}.num.f{{color:var(--fire)}}.num.a{{color:var(--amber)}}
  .sizes{{display:flex;align-items:flex-end;gap:15px;margin-top:11px;padding-top:11px;
    border-top:1px solid var(--stroke)}}
  .si{{display:flex;flex-direction:column;align-items:center;gap:5px;font-size:9.5px;color:var(--muted)}}
  .sd{{border-radius:50%;background:#96a2ba}}
  .s1{{width:17px;height:17px}}.s2{{width:12px;height:12px}}.s3{{width:8.5px;height:8.5px}}
  .sizenote{{font-size:9.5px;color:var(--muted);line-height:1.45;margin:9px 0 0}}
  .card{{position:absolute;top:20px;right:20px;width:266px;max-width:calc(100vw - 40px);
    background:var(--panel);border:1px solid var(--stroke);border-radius:16px;
    backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px);
    box-shadow:0 20px 48px -22px rgba(30,45,80,.4);padding:16px;
    opacity:0;transform:translateY(-6px);pointer-events:none;transition:.18s}}
  .card.show{{opacity:1;transform:none}}
  .ctop{{display:flex;gap:7px;align-items:center;margin-bottom:9px;flex-wrap:wrap}}
  .tag{{font-family:var(--mono);font-size:9.5px;font-weight:700;letter-spacing:.06em;
    text-transform:uppercase;padding:3px 7px;border-radius:5px}}
  .tag.wb{{background:rgba(209,36,127,.14);color:#c01f74}}.tag.tier{{background:rgba(60,72,100,.1);color:#4a5570}}
  .cname{{font-size:17px;font-weight:700;margin:0}}.creg{{font-size:12px;color:var(--muted);margin-top:3px}}
  .carea{{font-family:var(--mono);font-size:11px;color:#48546f;margin-top:8px}}
  .cst{{display:flex;align-items:center;gap:7px;margin-top:10px;font-size:12px;font-weight:600}}
  .cst .ico{{width:9px;height:9px;border-radius:50%;flex:none}}
  .cst.burned{{color:var(--fire)}}.cst.burned .ico{{background:var(--fire)}}
  .cst.hit{{color:#b0700f}}.cst.hit .ico{{background:var(--amber)}}
  .cst.ok{{color:#3d9a5b}}.cst.ok .ico{{background:#3d9a5b}}
  .cnote{{font-size:11.5px;color:#414c66;line-height:1.5;margin-top:9px;
    padding-top:9px;border-top:1px solid var(--stroke)}}
  .zoom{{position:absolute;right:20px;bottom:20px;display:flex;flex-direction:column;gap:6px}}
  .zb{{width:34px;height:34px;border-radius:10px;border:1px solid var(--stroke);
    background:var(--panel);color:var(--ink);font-size:17px;cursor:pointer;
    backdrop-filter:blur(8px);line-height:1}}.zb:hover{{background:#fff}}
  .hint{{position:absolute;left:20px;bottom:20px;font-family:var(--mono);font-size:10px;
    color:#98a2ba;letter-spacing:.04em}}
  .updated{{font-family:var(--mono);font-size:9px;color:#9aa5bd;margin-top:10px;
    padding-top:8px;border-top:1px solid var(--stroke)}}
  @media(max-width:820px){{
    .panel{{top:12px;left:12px;right:12px;width:auto;padding:14px}}
    .card{{top:auto;bottom:62px;right:12px;left:12px;width:auto}}
    .hint{{display:none}}
  }}
  @media(prefers-reduced-motion:reduce){{*{{transition:none!important;animation:none!important}}}}
</style>
</head>
<body>
<div class="wrap">
  <svg class="map" id="map" viewBox="0 0 1400 720" preserveAspectRatio="xMidYMid meet">
    <g id="cam">
      <path class="glow-land" d="{PATH}"/>
      <path class="land" d="{PATH}"/>
      {INNER}
    </g>
  </svg>
  <div class="panel">
    <div class="eyebrow">Фулфілмент-мережа · РФ</div>
    <h1>Склади <span class="a">Wildberries</span></h1>
    <p class="bt">Позначення</p>
    <div class="legend">
      <div class="row"><span class="sw wb"></span><span>Склад Wildberries</span><span class="num wb">{total}</span></div>
      <div class="row"><span class="fico">🔥</span><span>Згорів / пошкоджений</span><span class="num f">{burned}</span></div>
      <div class="row"><span class="sw ra"></span><span>Влучання — уцілів</span><span class="num a">{hit}</span></div>
    </div>
    <div class="sizes">
      <div class="si"><span class="sd s1"></span>≈200 тис. м²</div>
      <div class="si"><span class="sd s2"></span>≈100 тис.</div>
      <div class="si"><span class="sd s3"></span>≈50 тис.</div>
    </div>
    <p class="sizenote">Розмір ∝ площі, де підтверджена; решта — за класом об'єкта.</p>
    <p class="updated">🤖 Авто-оновлення: {UPDATED} · Meduza, Fontanka, BBC, UP</p>
  </div>
  <div class="card" id="card">
    <div class="ctop"><span class="tag wb">Wildberries</span><span class="tag tier" id="ctier"></span></div>
    <p class="cname" id="cname"></p>
    <div class="creg" id="creg"></div>
    <div class="carea" id="carea" style="display:none"></div>
    <div class="cst" id="cst"><span class="ico"></span><span id="csttxt"></span></div>
    <div class="cnote" id="cnote" style="display:none"></div>
  </div>
  <div class="zoom">
    <button class="zb" id="zin">+</button>
    <button class="zb" id="zout">−</button>
    <button class="zb" id="zres" style="font-size:12px">⟲</button>
  </div>
  <div class="hint">Колесо — зум · перетягування — зсув</div>
</div>
<script>
(function(){{
  var svg=document.getElementById('map'),cam=document.getElementById('cam');
  var k=1,tx=0,ty=0;
  function apply(){{
    cam.setAttribute('transform','translate('+tx+' '+ty+') scale('+k+')');
    document.querySelectorAll('.land').forEach(function(p){{p.style.strokeWidth=(0.8/k)+'px'}});
    document.querySelectorAll('.lbl').forEach(function(t){{t.style.fontSize=(11/k)+'px';t.style.strokeWidth=(3/k)+'px'}});
    document.querySelectorAll('.glbl').forEach(function(e){{e.style.fontSize=(12/k)+'px';e.style.strokeWidth=(3.2/k)+'px'}});
    document.querySelectorAll('.gsub').forEach(function(e){{e.style.fontSize=(10/k)+'px';e.style.strokeWidth=(3/k)+'px'}});
    document.querySelectorAll('.gbox').forEach(function(e){{e.style.strokeWidth=(1.1/k)+'px';e.style.strokeDasharray=(4/k)+' '+(3/k)}});
    document.querySelectorAll('.gtick').forEach(function(e){{e.style.strokeWidth=(1/k)+'px';e.style.strokeDasharray=(3/k)+' '+(2.5/k)}});
  }}
  function zoomAt(f,cx,cy){{var nk=Math.min(8,Math.max(1,k*f));if(nk===k)return;tx=cx-(cx-tx)*(nk/k);ty=cy-(cy-ty)*(nk/k);k=nk;apply()}}
  function ctr(){{var r=svg.getBoundingClientRect(),vb=svg.viewBox.baseVal,s=Math.min(r.width/vb.width,r.height/vb.height);return{{s:s,r:r,vb:vb}}}}
  function toVB(e){{var c=ctr(),ox=(c.r.width-c.vb.width*c.s)/2,oy=(c.r.height-c.vb.height*c.s)/2;return{{x:(e.clientX-c.r.left-ox)/c.s,y:(e.clientY-c.r.top-oy)/c.s}}}}
  svg.addEventListener('wheel',function(e){{e.preventDefault();var p=toVB(e);zoomAt(e.deltaY<0?1.22:1/1.22,p.x,p.y)}},{{passive:false}});
  document.getElementById('zin').onclick=function(){{zoomAt(1.4,700,360)}};
  document.getElementById('zout').onclick=function(){{zoomAt(1/1.4,700,360)}};
  document.getElementById('zres').onclick=function(){{k=1;tx=0;ty=0;apply()}};
  var drag=false,sx,sy,moved=0;
  svg.addEventListener('pointerdown',function(e){{drag=true;moved=0;sx=e.clientX;sy=e.clientY;svg.classList.add('drag');svg.setPointerCapture(e.pointerId)}});
  svg.addEventListener('pointermove',function(e){{if(!drag)return;var c=ctr();tx+=(e.clientX-sx)/c.s;ty+=(e.clientY-sy)/c.s;moved+=Math.abs(e.clientX-sx)+Math.abs(e.clientY-sy);sx=e.clientX;sy=e.clientY;apply()}});
  svg.addEventListener('pointerup',function(){{drag=false;svg.classList.remove('drag')}});
  svg.addEventListener('pointercancel',function(){{drag=false;svg.classList.remove('drag')}});
  var TIER={{hub:'Хаб',large:'Великий',mid:'Регіональний'}};
  var STAT={{burned:'Згорів / пошкоджений',hit:'Влучання — уцілів',ok:'Працює штатно'}};
  var card=document.getElementById('card'),ctier=document.getElementById('ctier'),
      cname=document.getElementById('cname'),creg=document.getElementById('creg'),
      carea=document.getElementById('carea'),cst=document.getElementById('cst'),
      csttxt=document.getElementById('csttxt'),cnote=document.getElementById('cnote');
  function show(g){{
    document.querySelectorAll('.pt.sel').forEach(function(x){{x.classList.remove('sel')}});
    g.classList.add('sel');var d=g.dataset;
    ctier.textContent=TIER[d.tier]||'';cname.textContent=d.n;creg.textContent=d.r;
    if(d.area){{carea.textContent='Площа: '+d.area;carea.style.display='block'}}else carea.style.display='none';
    cst.className='cst '+d.status;csttxt.textContent=STAT[d.status]+(d.date?' · '+d.date:'');
    if(d.note){{cnote.textContent=d.note;cnote.style.display='block'}}else cnote.style.display='none';
    card.classList.add('show');
  }}
  document.querySelectorAll('.pt').forEach(function(g){{
    g.setAttribute('tabindex','0');
    g.addEventListener('mouseenter',function(){{show(g)}});
    g.addEventListener('click',function(e){{e.stopPropagation();show(g)}});
    g.addEventListener('focus',function(){{show(g)}});
  }});
  svg.addEventListener('click',function(){{if(moved>4)return;card.classList.remove('show');document.querySelectorAll('.pt.sel').forEach(function(x){{x.classList.remove('sel')}})}});
  apply();
}})();
</script>
</body>
</html>"""

open(HTML_FILE, "w", encoding="utf-8").write(HTML)
from collections import Counter; c=Counter(w["status"] for w in W)
print(f"Built {HTML_FILE}: {len(W)} warehouses, {dict(c)}")
