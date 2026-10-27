import React, { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Icon, iconBody } from "./Icon";
import { CASE_COLORS, COMM_COLORS, DIRECTED, TYPE_COLOR, TYPE_ICON, TYPE_LABEL, relLabel } from "./util";
import type { GEdge, GNode } from "./types";

type P = { x: number; y: number; vx: number; vy: number; pin: boolean };

export type GraphProps = {
  nodes: GNode[];
  edges: GEdge[];
  height?: number | string;
  colorBy?: "type" | "community" | "case";
  selected?: string[];
  onSelect?: (id: string | null, multi: boolean) => void;
  onEdgeClick?: (e: GEdge) => void;
  query?: string;
  pathNodes?: Set<string>;
  pathEdges?: Set<string>;
  lostEdges?: Set<string>;
  cutNodes?: Set<string>;
  visibleNodes?: Set<string>;
  visibleEdges?: Set<string>;
  newEdges?: Set<string>;
  fitKey?: any;
  labels?: "auto" | "all" | "none";
  caseList?: string[];
  legend?: boolean;
  emptyText?: string;
};

const clamp = (v: number, a: number, b: number) => Math.max(a, Math.min(b, v));
const short = (s: string, n = 22) => (s.length > n ? s.slice(0, n - 1) + "…" : s);
const radius = (n: GNode) => 13 + Math.min(10, Math.sqrt(n.degree || 0) * 2.1);

export function GraphCanvas(props: GraphProps) {
  const { nodes, edges, colorBy = "type", selected = [], query = "", labels = "auto", legend = true } = props;
  const wrap = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const vpRef = useRef<SVGGElement>(null);
  const pos = useRef<Map<string, P>>(new Map());
  const nodeEls = useRef<Map<string, SVGGElement>>(new Map());
  const edgeEls = useRef<Map<string, SVGGElement>>(new Map());
  const edgeData = useRef<Map<string, GEdge>>(new Map());
  const simIds = useRef<string[]>([]);
  const simEdges = useRef<[string, string, number, number][]>([]);
  const view = useRef({ x: 400, y: 250, k: 1 });
  const size = useRef({ w: 800, h: 500 });
  const alpha = useRef(0);
  const raf = useRef(0);
  const frozen = useRef(false);
  const drag = useRef<any>(null);
  const fitted = useRef(false);
  const propsRef = useRef(props);
  propsRef.current = props;
  const [hover, setHover] = useState<string | null>(null);
  const [paused, setPaused] = useState(false);

  const adj = useMemo(() => {
    const m = new Map<string, Set<string>>();
    edges.forEach((e) => {
      if (!m.has(e.source)) m.set(e.source, new Set());
      if (!m.has(e.target)) m.set(e.target, new Set());
      m.get(e.source)!.add(e.target);
      m.get(e.target)!.add(e.source);
    });
    return m;
  }, [edges]);

  // ---------- imperative drawing ----------
  const applyView = () => {
    const v = view.current;
    vpRef.current?.setAttribute("transform", `translate(${v.x.toFixed(1)},${v.y.toFixed(1)}) scale(${v.k.toFixed(3)})`);
    svgRef.current?.classList.toggle("z2", v.k > 1.35);
  };
  const applyPositions = () => {
    const P = pos.current;
    nodeEls.current.forEach((el, id) => {
      const p = P.get(id);
      if (p) el.setAttribute("transform", `translate(${p.x.toFixed(1)},${p.y.toFixed(1)})`);
    });
    edgeEls.current.forEach((g, id) => {
      const e = edgeData.current.get(id);
      if (!e) return;
      const a = P.get(e.source), b = P.get(e.target);
      if (!a || !b) return;
      const [line, hit, arrow, label] = [g.children[0], g.children[1], g.children[2], g.children[3]] as SVGElement[];
      for (const l of [line, hit]) {
        l.setAttribute("x1", a.x.toFixed(1)); l.setAttribute("y1", a.y.toFixed(1));
        l.setAttribute("x2", b.x.toFixed(1)); l.setAttribute("y2", b.y.toFixed(1));
      }
      if (arrow) {
        const ang = (Math.atan2(b.y - a.y, b.x - a.x) * 180) / Math.PI;
        arrow.setAttribute("transform", `translate(${(a.x + (b.x - a.x) * 0.56).toFixed(1)},${(a.y + (b.y - a.y) * 0.56).toFixed(1)}) rotate(${ang.toFixed(1)})`);
      }
      if (label) { label.setAttribute("x", ((a.x + b.x) / 2).toFixed(1)); label.setAttribute("y", ((a.y + b.y) / 2 - 5).toFixed(1)); }
    });
  };

  const stepSim = () => {
    const ids = simIds.current, P = pos.current, n = ids.length, a = alpha.current;
    if (!n) return;
    const arr = ids.map((id) => P.get(id)!);
    const rep = 1500 + Math.sqrt(n) * 260;
    for (let i = 0; i < n; i++) {
      const pi = arr[i];
      for (let j = i + 1; j < n; j++) {
        const pj = arr[j];
        let dx = pi.x - pj.x, dy = pi.y - pj.y, d2 = dx * dx + dy * dy;
        if (d2 > 250000) continue;
        if (d2 < 1) { dx = Math.random() - 0.5; dy = Math.random() - 0.5; d2 = 1; }
        const f = (rep / d2) * a * 6, d = Math.sqrt(d2);
        const fx = (dx / d) * f, fy = (dy / d) * f;
        pi.vx += fx; pi.vy += fy; pj.vx -= fx; pj.vy -= fy;
      }
    }
    for (const [s, t, rest, k] of simEdges.current) {
      const ps = P.get(s), pt = P.get(t);
      if (!ps || !pt) continue;
      const dx = pt.x - ps.x, dy = pt.y - ps.y, d = Math.sqrt(dx * dx + dy * dy) || 1;
      const f = ((d - rest) / d) * k * a;
      ps.vx += dx * f; ps.vy += dy * f; pt.vx -= dx * f; pt.vy -= dy * f;
    }
    const g = 0.02 * a;
    for (const p of arr) {
      p.vx -= p.x * g; p.vy -= p.y * g;
      p.vx *= 0.8; p.vy *= 0.8;
      if (!p.pin) { p.x += clamp(p.vx, -40, 40); p.y += clamp(p.vy, -40, 40); }
    }
  };
  const loop = () => {
    if (alpha.current > 0.02 && !frozen.current) {
      stepSim(); alpha.current *= 0.972; applyPositions();
      raf.current = requestAnimationFrame(loop);
    } else raf.current = 0;
  };
  const wake = (a: number) => {
    alpha.current = Math.max(alpha.current, a);
    if (!raf.current && !frozen.current) raf.current = requestAnimationFrame(loop);
  };
  const warm = (steps: number) => {
    alpha.current = 1;
    for (let i = 0; i < steps; i++) { stepSim(); alpha.current *= 0.972; }
  };

  const fit = (animate = true) => {
    const { w, h } = size.current;
    const P = pos.current, vis = propsRef.current.visibleNodes;
    let x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9, c = 0;
    simIds.current.forEach((id) => {
      if (vis && !vis.has(id)) return;
      const p = P.get(id); if (!p) return;
      x0 = Math.min(x0, p.x); x1 = Math.max(x1, p.x); y0 = Math.min(y0, p.y); y1 = Math.max(y1, p.y); c++;
    });
    if (!c) return;
    const bw = Math.max(1, x1 - x0), bh = Math.max(1, y1 - y0);
    const k = clamp(Math.min((w - 110) / bw, (h - 110) / bh), 0.2, 1.5);
    const target = { k, x: w / 2 - ((x0 + x1) / 2) * k, y: h / 2 - ((y0 + y1) / 2) * k };
    if (!animate) { view.current = target; applyView(); return; }
    const from = { ...view.current }, t0 = performance.now();
    const tw = (t: number) => {
      const u = clamp((t - t0) / 380, 0, 1), e = 1 - Math.pow(1 - u, 3);
      view.current = { k: from.k + (target.k - from.k) * e, x: from.x + (target.x - from.x) * e, y: from.y + (target.y - from.y) * e };
      applyView();
      if (u < 1) requestAnimationFrame(tw);
    };
    requestAnimationFrame(tw);
  };

  // ---------- (re)build simulation when data changes ----------
  useLayoutEffect(() => {
    const P = pos.current, ids = nodes.map((n) => n.id), idset = new Set(ids);
    const wasEmpty = P.size === 0;
    Array.from(P.keys()).forEach((id) => { if (!idset.has(id)) P.delete(id); });
    let added = 0;
    nodes.forEach((n) => {
      if (P.has(n.id)) return;
      const nb = edges.find((e) => (e.source === n.id && P.has(e.target)) || (e.target === n.id && P.has(e.source)));
      const ref = nb ? P.get(nb.source === n.id ? nb.target : nb.source)! : null;
      const ang = Math.random() * 6.283, rad = ref ? 40 : 60 + Math.random() * 160;
      P.set(n.id, { x: (ref ? ref.x : 0) + Math.cos(ang) * rad, y: (ref ? ref.y : 0) + Math.sin(ang) * rad, vx: 0, vy: 0, pin: false });
      added++;
    });
    const nn = Math.max(1, ids.length), spread = 62 + Math.sqrt(nn) * 3.2;
    simIds.current = ids;
    simEdges.current = edges
      .filter((e) => idset.has(e.source) && idset.has(e.target))
      .map((e) => [e.source, e.target, spread + (1 - e.confidence) * 40, 0.07] as [string, string, number, number]);
    edgeData.current = new Map(edges.map((e) => [e.id, e]));
    if (wasEmpty || added > nn * 0.5) warm(wasEmpty ? 220 : 120);
    applyPositions();
    if (!fitted.current && ids.length) { fit(false); fitted.current = true; }
    wake(added ? 0.5 : 0.18);
  }, [nodes, edges]);

  useEffect(() => { if (props.fitKey !== undefined) { const t = setTimeout(() => fit(true), 60); return () => clearTimeout(t); } }, [props.fitKey]);

  // size + wheel
  useEffect(() => {
    const el = wrap.current, svg = svgRef.current;
    if (!el || !svg) return;
    const measure = () => {
      const r = el.getBoundingClientRect();
      const first = size.current.w === 800 && size.current.h === 500 && !fitted.current;
      size.current = { w: Math.max(200, r.width), h: Math.max(200, r.height) };
      if (first || !fitted.current) { view.current.x = r.width / 2; view.current.y = r.height / 2; applyView(); }
    };
    measure();
    const ro = new ResizeObserver(() => { measure(); });
    ro.observe(el);
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const r = svg.getBoundingClientRect(), mx = e.clientX - r.left, my = e.clientY - r.top, v = view.current;
      const k1 = clamp(v.k * Math.exp(-e.deltaY * 0.0016), 0.15, 3.5);
      v.x = mx - (mx - v.x) * (k1 / v.k); v.y = my - (my - v.y) * (k1 / v.k); v.k = k1;
      applyView();
    };
    svg.addEventListener("wheel", onWheel, { passive: false });
    applyView();
    return () => { ro.disconnect(); svg.removeEventListener("wheel", onWheel); cancelAnimationFrame(raf.current); raf.current = 0; };
  }, []);

  useLayoutEffect(() => { applyPositions(); });

  // ---------- pointer interaction ----------
  const world = (e: React.PointerEvent) => {
    const r = svgRef.current!.getBoundingClientRect(), v = view.current;
    return { x: (e.clientX - r.left - v.x) / v.k, y: (e.clientY - r.top - v.y) / v.k };
  };
  const onDown = (e: React.PointerEvent) => {
    const t = e.target as Element;
    const ng = t.closest(".gn"), eg = t.closest(".ge");
    svgRef.current!.setPointerCapture(e.pointerId);
    drag.current = {
      kind: ng ? "node" : "pan", id: ng?.getAttribute("data-id"), eid: !ng && eg ? eg.getAttribute("data-id") : null,
      sx: e.clientX, sy: e.clientY, vx: view.current.x, vy: view.current.y, moved: false,
    };
  };
  const onMove = (e: React.PointerEvent) => {
    const d = drag.current; if (!d) return;
    const dx = e.clientX - d.sx, dy = e.clientY - d.sy;
    if (!d.moved && Math.hypot(dx, dy) > 4) d.moved = true;
    if (!d.moved) return;
    if (d.kind === "node") {
      const p = pos.current.get(d.id), w = world(e);
      if (p) { p.x = w.x; p.y = w.y; p.vx = p.vy = 0; p.pin = true; wake(0.3); applyPositions(); }
    } else { view.current.x = d.vx + dx; view.current.y = d.vy + dy; applyView(); }
  };
  const onUp = (e: React.PointerEvent) => {
    const d = drag.current; drag.current = null;
    if (!d) return;
    try { svgRef.current!.releasePointerCapture(e.pointerId); } catch { /* ignore */ }
    if (d.kind === "node") {
      const p = pos.current.get(d.id);
      if (d.moved) { if (p) p.pin = false; wake(0.3); }
      else props.onSelect && props.onSelect(d.id, e.shiftKey || e.metaKey || e.ctrlKey);
    } else if (!d.moved) {
      if (d.eid && props.onEdgeClick) { const ed = edgeData.current.get(d.eid); if (ed) props.onEdgeClick(ed); }
      else props.onSelect && props.onSelect(null, false);
    }
  };

  const zoomBy = (f: number) => {
    const { w, h } = size.current, v = view.current, k1 = clamp(v.k * f, 0.15, 3.5);
    v.x = w / 2 - (w / 2 - v.x) * (k1 / v.k); v.y = h / 2 - (h / 2 - v.y) * (k1 / v.k); v.k = k1; applyView();
  };
  const relayout = () => {
    pos.current.forEach((p) => { p.x = (Math.random() - 0.5) * 400; p.y = (Math.random() - 0.5) * 300; p.pin = false; });
    warm(200); applyPositions(); wake(0.4); fit(true);
  };
  const togglePause = () => { frozen.current = !frozen.current; setPaused(frozen.current); if (!frozen.current) wake(0.3); };

  // ---------- render ----------
  const q = query.trim().toLowerCase();
  const isMatch = (n: GNode) => !q || n.name.toLowerCase().includes(q) || (n.aliases || []).some((a) => a.toLowerCase().includes(q));
  const focus = hover;
  const nbrs = focus ? adj.get(focus) : null;
  const selSet = new Set(selected);
  const selNb = new Set<string>();
  selected.forEach((s) => adj.get(s)?.forEach((x) => selNb.add(x)));
  const hasPath = !!props.pathNodes && props.pathNodes.size > 0;
  const many = nodes.length > 40;
  const caseIdx = (n: GNode) => Math.max(0, (props.caseList || []).indexOf(n.cases[0]));
  const colorOf = (n: GNode) => (colorBy === "community" ? (n.community ? COMM_COLORS[(n.community - 1) % COMM_COLORS.length] : "#7b8aa8") : colorBy === "case" ? CASE_COLORS[caseIdx(n) % CASE_COLORS.length] : TYPE_COLOR[n.type] || "#8aa");
  const present = Array.from(new Set(nodes.map((n) => n.type)));

  return (
    <div className="graph-wrap" ref={wrap} style={{ height: props.height ?? 520 }}>
      <svg ref={svgRef} className={"graph-svg lab-" + labels} onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp} onPointerCancel={onUp}>
        <defs>
          <filter id="gl" x="-60%" y="-60%" width="220%" height="220%"><feGaussianBlur stdDeviation="3.5" result="b" /><feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge></filter>
        </defs>
        <g ref={vpRef}>
          <g className="edges">
            {edges.map((e) => {
              const hidden = props.visibleEdges && !props.visibleEdges.has(e.id);
              const onPath = props.pathEdges?.has(e.id), lost = props.lostEdges?.has(e.id);
              const hot = !hidden && (focus ? e.source === focus || e.target === focus : false) || selSet.has(e.source) || selSet.has(e.target);
              const dim = hasPath ? !onPath : (focus && !(e.source === focus || e.target === focus)) || (!!q && !(isMatch(nodes.find((n) => n.id === e.source)!) || isMatch(nodes.find((n) => n.id === e.target)!)));
              const cls = ["ge", hidden ? "hidden" : "", onPath ? "path" : "", lost ? "lost" : "", e.cases.length > 1 ? "cross" : "", hot && !hasPath ? "hot" : "", dim && !onPath && !lost ? "dim" : "", props.newEdges?.has(e.id) ? "new" : ""].join(" ");
              const w = Math.min(5, 1 + e.confidence * 1.8 + Math.log2(e.count) * 0.5);
              return (
                <g key={e.id} className={cls} data-id={e.id} ref={(el) => { if (el) edgeEls.current.set(e.id, el); else edgeEls.current.delete(e.id); }}>
                  <line className="eline" strokeWidth={w} />
                  <line className="ehit" strokeWidth={14} />
                  <path className="earrow" d="M-6,-4.2L4,0L-6,4.2z" style={{ display: DIRECTED.has(e.relation) ? undefined : "none" }} />
                  <text className="elabel">{relLabel(e.relation)}{e.count > 1 ? ` ×${e.count}` : ""}</text>
                </g>
              );
            })}
          </g>
          <g className="nodes">
            {nodes.map((n) => {
              const r = radius(n), c = colorOf(n);
              const hidden = props.visibleNodes && !props.visibleNodes.has(n.id);
              const sel = selSet.has(n.id);
              const dim = (!!q && !isMatch(n)) || (!!focus && n.id !== focus && !nbrs?.has(n.id)) || (hasPath && !props.pathNodes!.has(n.id)) ;
              const cls = ["gn", sel ? "sel" : "", dim ? "dim" : "", hidden ? "hidden" : "", n.cross_case ? "cross" : "", props.cutNodes?.has(n.id) ? "cut" : "", props.pathNodes?.has(n.id) ? "onpath" : "", (n.degree >= 3 || !many || sel || focus === n.id || selNb.has(n.id) || (hasPath && props.pathNodes!.has(n.id))) ? "big" : "", q && isMatch(n) ? "match" : ""].join(" ");
              return (
                <g key={n.id} className={cls} data-id={n.id} style={{ ["--c" as any]: c }}
                   ref={(el) => { if (el) nodeEls.current.set(n.id, el); else nodeEls.current.delete(n.id); }}
                   onMouseEnter={() => setHover(n.id)} onMouseLeave={() => setHover((h) => (h === n.id ? null : h))}>
                  <title>{`${n.name} · ${n.type}${n.cases.length ? " · " + n.cases.join(", ") : ""}`}</title>
                  {n.cross_case && <circle className="xring" r={r + 7} />}
                  <circle className="halo" r={r + 4} />
                  <circle className="body" r={r} />
                  <g className="glyph" transform={`translate(${-r * 0.5},${-r * 0.5}) scale(${(r * 1.0) / 24})`} fill="none" stroke="currentColor" strokeWidth={2.1} strokeLinecap="round" strokeLinejoin="round">{iconBody(TYPE_ICON[n.type] || "dot")}</g>
                  <text className="lbl" y={r + 13} textAnchor="middle">{short(n.name)}</text>
                </g>
              );
            })}
          </g>
        </g>
      </svg>

      {nodes.length === 0 && <div className="graph-empty">{props.emptyText || "Nothing to show yet — add records to build the network."}</div>}

      <div className="g-tools">
        <button title="Zoom in" onClick={() => zoomBy(1.3)}><Icon name="zoomIn" size={16} /></button>
        <button title="Zoom out" onClick={() => zoomBy(1 / 1.3)}><Icon name="zoomOut" size={16} /></button>
        <button title="Fit to screen" onClick={() => fit(true)}><Icon name="maximize" size={16} /></button>
        <button title="Re-run layout" onClick={relayout}><Icon name="refresh" size={16} /></button>
        <button title={paused ? "Resume physics" : "Freeze layout"} onClick={togglePause}><Icon name={paused ? "play" : "pause"} size={16} /></button>
      </div>
      {legend && nodes.length > 0 && (
        <div className="g-legend">
          {colorBy === "type" && present.map((t) => <span key={t}><i style={{ background: TYPE_COLOR[t] }} />{(TYPE_LABEL[t] || t).replace(/s$/, "")}</span>)}
          {colorBy === "community" && <span><i style={{ background: COMM_COLORS[0] }} /><i style={{ background: COMM_COLORS[1] }} /><i style={{ background: COMM_COLORS[2] }} />Colour = detected community</span>}
          {colorBy === "case" && (props.caseList || []).map((c, i) => <span key={c}><i style={{ background: CASE_COLORS[i % CASE_COLORS.length] }} />{c}</span>)}
          <span className="lg-x"><i className="ring" />Appears in several cases</span>
        </div>
      )}
    </div>
  );
}
