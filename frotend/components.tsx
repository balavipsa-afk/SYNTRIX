import React, { useEffect, useMemo, useRef, useState } from "react";
import { Icon } from "./Icon";
import { api } from "./api";
import { TYPE_COLOR, TYPE_ICON, highlightParts } from "./util";

export function useDebounced<T>(value: T, ms = 250): T {
  const [v, setV] = useState(value);
  useEffect(() => { const t = setTimeout(() => setV(value), ms); return () => clearTimeout(t); }, [value, ms]);
  return v;
}

export function CountUp({ value, duration = 700 }: { value: number; duration?: number }) {
  const [shown, setShown] = useState(value);
  const from = useRef(value);
  useEffect(() => {
    const start = performance.now(), a = from.current, b = value;
    if (a === b) return;
    let raf = 0;
    const tick = (t: number) => {
      const k = Math.min(1, (t - start) / duration), e = 1 - Math.pow(1 - k, 3);
      setShown(Math.round(a + (b - a) * e));
      if (k < 1) raf = requestAnimationFrame(tick); else from.current = b;
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [value, duration]);
  return <>{shown.toLocaleString()}</>;
}

export function TypeDot({ type, size = 26 }: { type: string; size?: number }) {
  const c = TYPE_COLOR[type] || "#8aa";
  return (
    <span className="typedot" style={{ width: size, height: size, color: c, borderColor: c + "66", background: c + "1f" }}>
      <Icon name={TYPE_ICON[type] || "dot"} size={Math.round(size * 0.58)} />
    </span>
  );
}

export function Gauge({ value, size = 132, label = "PATH CONFIDENCE" }: { value: number; size?: number; label?: string }) {
  const r = size / 2 - 10, c = 2 * Math.PI * r, v = Math.max(0, Math.min(100, value));
  const tone = v >= 80 ? "#34D399" : v >= 55 ? "#F59E0B" : "#FB7185";
  return (
    <div className="gauge" style={{ width: size, height: size }}>
      <svg width={size} height={size}>
        <circle cx={size / 2} cy={size / 2} r={r} className="g-track" />
        <circle cx={size / 2} cy={size / 2} r={r} className="g-val" style={{ stroke: tone, strokeDasharray: c, strokeDashoffset: c * (1 - v / 100) }} transform={`rotate(-90 ${size / 2} ${size / 2})`} />
      </svg>
      <div className="g-center"><b>{v.toFixed(v % 1 ? 1 : 0)}%</b><span>{label}</span></div>
    </div>
  );
}

export function ConfBar({ value }: { value: number }) {
  const tone = value >= 0.85 ? "high" : value >= 0.7 ? "mid" : "low";
  return <span className={"confbar " + tone}><i style={{ width: `${Math.round(value * 100)}%` }} /></span>;
}

export function Chip({ children, tone, onClick, active, title }: { children: React.ReactNode; tone?: string; onClick?: () => void; active?: boolean; title?: string }) {
  return <span title={title} className={"chip" + (tone ? " " + tone : "") + (onClick ? " click" : "") + (active ? " on" : "")} onClick={onClick}>{children}</span>;
}

export function Highlighted({ text, ents, onEntity }: { text: string; ents: any[]; onEntity?: (id: string) => void }) {
  const parts = useMemo(() => highlightParts(text, ents || []), [text, ents]);
  return (
    <>
      {parts.map((p, i) =>
        p.type ? (
          <mark key={i} className="hl" style={{ ["--c" as any]: TYPE_COLOR[p.type] }} onClick={() => onEntity && onEntity(p.id)} title={p.type}>{p.text}</mark>
        ) : (
          <React.Fragment key={i}>{p.text}</React.Fragment>
        )
      )}
    </>
  );
}

export function Empty({ icon = "info", title, children }: { icon?: string; title: string; children?: React.ReactNode }) {
  return (
    <div className="empty">
      <div className="empty-ico"><Icon name={icon} size={26} /></div>
      <b>{title}</b>
      {children && <p>{children}</p>}
    </div>
  );
}

export function Spinner({ label }: { label?: string }) {
  return <span className="spin-wrap"><span className="spinner" />{label && <span>{label}</span>}</span>;
}

/** Searchable entity dropdown backed by /api/entities */
export function EntityPicker({ value, onChange, caseId, placeholder, rev }: { value: any; onChange: (e: any) => void; caseId: string; placeholder: string; rev: number }) {
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<any[]>([]);
  const dq = useDebounced(q, 180);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    let live = true;
    api.entities({ case_id: caseId, q: dq, limit: 40 }).then((r) => live && setItems(r.items)).catch(() => {});
    return () => { live = false; };
  }, [dq, open, caseId, rev]);
  useEffect(() => {
    const h = (e: MouseEvent) => { if (box.current && !box.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);
  return (
    <div className="picker" ref={box}>
      <button className={"picker-btn" + (value ? " has" : "")} onClick={() => setOpen(!open)} type="button">
        {value ? <><TypeDot type={value.type} size={24} /><span className="pk-name">{value.name}</span></> : <span className="pk-ph">{placeholder}</span>}
        <Icon name="chevD" size={15} />
      </button>
      {open && (
        <div className="picker-pop">
          <div className="picker-search"><Icon name="search" size={15} /><input autoFocus placeholder="Search people, phones, vehicles…" value={q} onChange={(e) => setQ(e.target.value)} /></div>
          <div className="picker-list">
            {items.length === 0 && <div className="picker-none">No matches</div>}
            {items.map((e) => (
              <button key={e.id} type="button" className="picker-item" onClick={() => { onChange(e); setOpen(false); setQ(""); }}>
                <TypeDot type={e.type} size={22} />
                <span className="pi-name">{e.name}</span>
                <span className="pi-meta">{e.type} · {e.degree} links{e.cross_case ? " · cross-case" : ""}</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export type Toast = { id: number; kind: "ok" | "err" | "info"; text: string };
export function Toasts({ items, dismiss }: { items: Toast[]; dismiss: (id: number) => void }) {
  return (
    <div className="toasts">
      {items.map((t) => (
        <div key={t.id} className={"toast " + t.kind} onClick={() => dismiss(t.id)}>
          <Icon name={t.kind === "err" ? "alert" : t.kind === "ok" ? "check" : "info"} size={17} />
          <span>{t.text}</span>
        </div>
      ))}
    </div>
  );
}
