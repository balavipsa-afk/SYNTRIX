import React, { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import { GraphCanvas } from "./GraphCanvas";
import { Icon } from "./Icon";
import { ConfBar, EntityPicker, Gauge, Highlighted, TypeDot } from "./components";
import { fmtDate, relLabel } from "./util";

type Tab = "overview" | "network" | "explain" | "whatif" | "timeline";
const TABS: [Tab, string, string][] = [["overview", "Overview", "dashboard"], ["network", "Network", "network"], ["explain", "Connection Explainer", "route"], ["whatif", "What-If", "sliders"], ["timeline", "Timeline", "clock"]];

export default function App() {
  const [tab, setTab] = useState<Tab>("overview");
  const [rev, setRev] = useState(0);
  const [stats, setStats] = useState<any>(null);
  const [leads, setLeads] = useState<any[]>([]);
  const [graph, setGraph] = useState<any>({ nodes: [], edges: [] });
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [caseId, setCaseId] = useState("CASE-001");
  const refresh = useCallback(() => setRev((r) => r + 1), []);

  useEffect(() => {
    Promise.all([api.stats(), api.leads("ALL"), api.graph("ALL")]).then(([s, l, g]) => { setStats(s); setLeads(l); setGraph(g); setErr(""); }).catch((e) => setErr(e.message));
  }, [rev]);

  const run = async (fn: () => Promise<any>) => {
    setBusy(true);
    try {
      const r = await fn();
      if (r && r.statements !== undefined) setMsg(`Processed ${r.statements} statements → ${r.entities_new} new entities, ${r.relationships_new} new links, ${r.merges} merges, ${r.cross_case} cross-case.`);
      refresh();
    } catch (e: any) { setErr(e.message); }
    setBusy(false);
  };
  const upload = (files: FileList | null) => files && Array.from(files).forEach((f) => run(() => api.upload(f, caseId)));

  return (
    <div className="app">
      <header>
        <div className="logo">SYNTRIX <small>INVESTIGATION INTELLIGENCE · TEAM PAWTENTIAL</small></div>
        <nav>{TABS.map(([k, l, i]) => <button key={k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}><Icon name={i} size={16} /> {l}</button>)}</nav>
      </header>
      {err && <div className="banner err">{err}</div>}
      <section className="add">
        <textarea placeholder="Paste any case text, call records, or ledger here…" value={text} onChange={(e) => setText(e.target.value)} />
        <div className="actions">
          <button disabled={busy || !text.trim()} onClick={() => run(async () => { const r = await api.ingest(text, caseId, "pasted-text"); setText(""); return r; })}>Analyze text</button>
          <label className="btn">Upload files<input type="file" multiple hidden onChange={(e) => upload(e.target.files)} /></label>
          <input className="case" value={caseId} onChange={(e) => setCaseId(e.target.value.toUpperCase())} title="Case ID this data belongs to" />
          <button onClick={() => run(() => api.reset("demo"))}>Load demo</button>
          <button onClick={() => run(() => api.reset("empty"))}>Clear all</button>
        </div>
        {msg && <div className="banner ok">{msg}</div>}
      </section>
      <main>
        {tab === "overview" && <Overview stats={stats} leads={leads} />}
        {tab === "network" && <GraphCanvas nodes={graph.nodes} edges={graph.edges} height={560} emptyText="Add records above to build the network." />}
        {tab === "explain" && <Explain rev={rev} />}
        {tab === "whatif" && <WhatIf rev={rev} />}
        {tab === "timeline" && <Timeline rev={rev} />}
      </main>
    </div>
  );
}

function Overview({ stats, leads }: any) {
  if (!stats) return <p>Loading…</p>;
  const tiles = [["Cases", stats.cases], ["Entities", stats.entities], ["Links", stats.relationships], ["Evidence", stats.evidence], ["Cross-case entities", stats.cross_case_entities], ["Merged aliases", stats.merges]];
  return (
    <>
      <div className="tiles">{tiles.map(([k, v]) => <div className="tile" key={k as string}><b>{v}</b><span>{k}</span></div>)}</div>
      <h3>Signal Engine — ranked leads <small>(leads, not verdicts)</small></h3>
      <div className="chips"><span>Deterministic · algorithm-first</span><span>Model calls: {stats.model_calls}</span><span>Last processing: {stats.last_ms} ms</span><span>Runs in your browser</span></div>
      {leads.length === 0 && <p className="muted">No leads yet — add records.</p>}
      {leads.map((l: any) => (
        <div className="lead" key={l.id}>
          <div className="score">{l.score}</div>
          <div><b>{l.title}</b><p>{l.summary}</p><div className="muted">Why this score: {l.reasons.join(" · ")}</div><div className="muted">Needs human review · evidence: {(l.evidence_ids || []).length} record(s)</div></div>
        </div>
      ))}
    </>
  );
}

function Explain({ rev }: any) {
  const [a, setA] = useState<any>(null);
  const [b, setB] = useState<any>(null);
  const [res, setRes] = useState<any>(null);
  useEffect(() => { if (a && b) api.explain(a.id, b.id).then(setRes).catch(() => setRes(null)); }, [a, b, rev]);
  return (
    <>
      <div className="row"><EntityPicker value={a} onChange={setA} caseId="ALL" placeholder="Pick entity A" rev={rev} /><Icon name="arrowR" /><EntityPicker value={b} onChange={setB} caseId="ALL" placeholder="Pick entity B" rev={rev} /></div>
      {res && !res.connected && <p className="muted">{res.message}</p>}
      {res && res.connected && (
        <div className="explain">
          <Gauge value={res.best.confidence} />
          <div>
            <p className="narr">{res.narrative}</p>
            <div className="path">{res.best.hops.map((h: any, i: number) => <React.Fragment key={i}>{i === 0 && <span className="pn"><TypeDot type={h.from_type} size={22} />{h.from_name}</span>}<span className="hop">{relLabel(h.relation)} <ConfBar value={h.confidence} /></span><span className="pn"><TypeDot type={h.to_type} size={22} />{h.to_name}</span></React.Fragment>)}</div>
            <h4>Evidence trail</h4>
            {res.evidence.map((e: any) => <div className="ev" key={e.id}><small>{fmtDate(e.timestamp)} · {e.source} · {e.case_id}</small><div><Highlighted text={e.text} ents={e.entities} /></div></div>)}
          </div>
        </div>
      )}
    </>
  );
}

function WhatIf({ rev }: any) {
  const [rels, setRels] = useState<any[]>([]);
  const [off, setOff] = useState<string[]>([]);
  const [res, setRes] = useState<any>(null);
  useEffect(() => { api.relationships("ALL").then((r) => setRels(r.slice(0, 60))); setOff([]); }, [rev]);
  useEffect(() => { api.whatIf({ remove_relationship_ids: off, min_confidence: 0 }).then(setRes).catch(() => {}); }, [off, rev]);
  const toggle = (id: string) => setOff((o) => (o.includes(id) ? o.filter((x) => x !== id) : [...o, id]));
  return (
    <div className="two">
      <div className="list">{rels.map((r) => <label key={r.id}><input type="checkbox" checked={off.includes(r.id)} onChange={() => toggle(r.id)} /> {r.source_name} <em>{relLabel(r.relation)}</em> {r.target_name} <ConfBar value={r.confidence} /></label>)}</div>
      <div>{res && <><p className="narr">{res.verdict}</p><div className="tiles"><div className="tile"><b>{res.before.components} → {res.after.components}</b><span>Groups</span></div><div className="tile"><b>{res.impact.connections_lost}</b><span>Connections lost</span></div><div className="tile"><b>{res.leads_lost.length}</b><span>Leads gone</span></div></div>
        <h4>Single points of failure</h4>{res.critical_links.map((c: any) => <div key={c.rel_id} className="muted">{c.a} — {c.b} (isolates {c.isolates})</div>)}</>}</div>
    </div>
  );
}

function Timeline({ rev }: any) {
  const [t, setT] = useState<any>({ events: [] });
  useEffect(() => { api.timeline("ALL").then(setT); }, [rev]);
  return <div>{t.events.length === 0 && <p className="muted">No dated events yet.</p>}{t.events.map((e: any) => <div className="ev" key={e.id}><small>{fmtDate(e.date)} · confidence {Math.round(e.confidence * 100)}%</small><div><b>{e.source}</b> {relLabel(e.relation)} <b>{e.target}</b></div></div>)}</div>;
}
