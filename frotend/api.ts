// Runs entirely in the browser: no server needed. Same interface as the Python backend API.
import { Engine, SAMPLES } from "./engine";

const eng = new Engine();
let history: [string, string, string][] = [];
const KEY = "syntrix-history-v2";
const persist = () => { try { const s = JSON.stringify(history); if (s.length < 2_500_000) localStorage.setItem(KEY, s); } catch { /* storage may be blocked */ } };
const run = (t: string, c: string, n: string) => { const r = eng.ingest(t, c, n); history.push([t, c, n]); persist(); return r; };
const loadDemo = () => { eng.reset(); history = []; Object.values(SAMPLES).forEach(([n, c, t]) => run(t, c, n)); };
try { const h = localStorage.getItem(KEY); if (h) { JSON.parse(h).forEach(([t, c, n]: any) => { eng.ingest(t, c, n); history.push([t, c, n]); }); } } catch { /* ignore */ }
if (!eng.ents.size && !history.length) loadDemo();

const ok = <T,>(v: T) => Promise.resolve(v);
const cs = (c?: string) => (c && c !== "ALL" ? c : undefined);
export const api = {
  stats: () => ok(eng.stats()),
  leads: (c: string) => ok(eng.leads(cs(c)).slice(0, 30).map((l) => ({ ...l, entity_names: l.entities.map((i: string) => eng.ents.get(i)) }))),
  graph: (c: string, _o: any = {}) => ok(eng.graph(cs(c))),
  entities: (o: any) => ok(eng.entities(o.q || "", o.limit || 40)),
  relationships: (_c: string) => ok(eng.relationships()),
  explain: (a: string, b: string, o: any = {}) => ok(eng.explain(a, b, o.removed || [], o.min_confidence || 0)),
  whatIf: (o: any) => ok(eng.whatIf(o.remove_relationship_ids || [], o.min_confidence || 0)),
  timeline: (_c: string) => ok(eng.timeline()),
  ingest: (text: string, c: string, name: string) => ok(run(text, c || "CASE-001", name || "pasted-text")),
  upload: async (f: File, c: string) => run(await f.text(), c || "CASE-001", f.name),
  loadSample: (k: string, c?: string) => { const [n, cc, t] = SAMPLES[k]; return ok(run(t, c || cc, n)); },
  reset: (mode: "demo" | "empty") => { if (mode === "demo") loadDemo(); else { eng.reset(); history = []; persist(); } return ok(eng.stats()); },
  cases: () => ok([...eng.cases.values()]),
};
