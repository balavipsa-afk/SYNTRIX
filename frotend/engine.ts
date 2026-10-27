// SYNTRIX in-browser engine: deterministic, algorithm-first (no LLM, 0 model calls).
const STOP = new Set("the a an this that on at in to from by with for of and or but as is was were he she they it we his her their phone mobile number call called vehicle record report case date time amount transaction transfer payment account police station evidence note notes complainant suspect accused witness victim inspector mr mrs ms dr sir fir cctv warehouse route surveillance division monday tuesday wednesday thursday friday saturday sunday january february march april may june july august september october november december jan feb mar apr jun jul aug sep sept oct nov dec during after before later then also rs inr ledger invoice".split(" "));
const ORG = /^(logistics|finance|transport|traders|trading|enterprises|industries|bank|services|solutions|motors|travels|cargo|pvt|ltd|llp|inc|corp|company|group|exports|imports|capital|agency|couriers|foundation|systems|technologies)$/i;
const LOCSUF = /^(road|street|nagar|chowk|market|station|airport|hotel|mall|colony|bridge|highway|square|park|temple|hospital|depot|port|junction|plaza|complex|place|stand)$/i;
const GAZ = new Set("Bhopal Indore Delhi Mumbai Pune Ujjain Gwalior Jabalpur Raisen Sehore Nagpur Surat Ahmedabad Jaipur Lucknow Kanpur Patna Kolkata Hyderabad Chennai Bengaluru Gurgaon Gurugram Noida Goa Nashik Agra Raipur Ranchi Dewas Ratlam Sagar Dubai Habibganj".split(" "));
const MON: any = { jan: 1, feb: 2, mar: 3, apr: 4, may: 5, jun: 6, jul: 7, aug: 8, sep: 9, oct: 10, nov: 11, dec: 12 };
const MR = "(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)";
const iso = (y: number, m: number, d: number, h?: string, mi?: string) => (m < 1 || m > 12 || d < 1 || d > 31 ? "" : `${y}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}${h ? `T${h.padStart(2, "0")}:${mi}` : ""}`);
function findDates(t: string) {
  const out: any[] = [];
  const add = (r: RegExp, f: (m: RegExpExecArray) => string) => { let m; r.lastIndex = 0; while ((m = r.exec(t))) { const v = f(m); const s = m.index, e = m.index + m[0].length; if (v && !out.some((o) => s < o.e && e > o.s)) out.push({ s, e, iso: v }); } };
  add(/\b(20\d\d)[-/.](\d{1,2})[-/.](\d{1,2})(?:[T\s]+(\d{1,2}):(\d{2}))?/g, (m) => iso(+m[1], +m[2], +m[3], m[4], m[5]));
  add(/\b(\d{1,2})[-/.](\d{1,2})[-/.](20\d\d)\b/g, (m) => iso(+m[3], +m[2], +m[1]));
  add(new RegExp(`\\b(\\d{1,2})(?:st|nd|rd|th)?[\\s-]+(${MR})\\.?,?[\\s-]+(20\\d\\d)`, "gi"), (m) => iso(+m[3], MON[m[2].slice(0, 3).toLowerCase()], +m[1]));
  add(new RegExp(`\\b(${MR})\\.?[\\s-]+(\\d{1,2})(?:st|nd|rd|th)?,?[\\s-]+(20\\d\\d)`, "gi"), (m) => iso(+m[3], MON[m[1].slice(0, 3).toLowerCase()], +m[2]));
  return out.sort((a, b) => a.s - b.s);
}
const amount = (s: string) => { const m = s.replace(/,/g, "").match(/(\d+(?:\.\d+)?)/); if (!m) return 0; let v = +m[1]; if (/crore|\bcr\b/i.test(s)) v *= 1e7; else if (/lakh|lac/i.test(s)) v *= 1e5; return v; };
export const inr = (v: number) => "₹" + Math.round(v).toLocaleString("en-IN");
const lev = (a: string, b: string) => { const d = Array.from({ length: a.length + 1 }, (_, i) => [i, ...Array(b.length).fill(0)]); for (let j = 1; j <= b.length; j++) d[0][j] = j; for (let i = 1; i <= a.length; i++) for (let j = 1; j <= b.length; j++) d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1)); return 1 - d[a.length][b.length] / Math.max(a.length, b.length, 1); };
const noisy = (v: number[]) => Math.round((1 - v.reduce((p, c) => p * (1 - Math.min(c, 0.99)), 1)) * 1000) / 1000;

type M = { s: number; e: number; type: string; raw: string; val: string; role?: string; amt?: number };
function mentions(t: string): M[] {
  const c: M[] = [];
  const push = (r: RegExp, type: string, f?: (m: RegExpExecArray) => Partial<M>) => { let m; r.lastIndex = 0; while ((m = r.exec(t))) c.push({ s: m.index, e: m.index + m[0].length, type, raw: m[0], val: m[0], ...(f ? f(m) : {}) }); };
  push(/(?:\+?91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}(?!\d)/g, "phone");
  push(/\b[A-Z]{2}[\s-]?\d{1,2}[A-Z]?[\s-]?[A-Z]{1,3}[\s-]?\d{3,4}\b/g, "vehicle");
  push(/(?:₹|Rs\.?|INR)\s*\d[\d,]*(?:\.\d+)?(?:\s*(?:lakhs?|crores?))?/gi, "transaction", (m) => ({ amt: amount(m[0]) }));
  push(/\bFIR[\s#:-]*(?:No\.?\s*)?(\d[\w/-]*)/gi, "event", (m) => ({ val: "FIR " + m[1] }));
  push(/(?:\b[A-Z]\.\s?)*\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3}/g, "?");
  for (const m of c.filter((x) => x.type === "?")) {
    const w = m.raw.split(/\s+/); while (w.length && STOP.has(w[0].toLowerCase().replace(".", ""))) w.shift(); while (w.length && STOP.has(w[w.length - 1].toLowerCase())) w.pop();
    m.type = ""; if (!w.length) continue;
    const s = m.s + m.raw.indexOf(w[0]), raw = w.join(" ");
    const t2 = w.length > 1 && (ORG.test(w[w.length - 1]) || w.some((x) => /^(pvt|ltd)$/i.test(x))) ? "organization" : (LOCSUF.test(w[w.length - 1]) && w.length > 1) || GAZ.has(raw) ? "location" : w.length > 1 && !w.some((x) => GAZ.has(x)) ? "person" : "";
    if (t2) Object.assign(m, { type: t2, s, e: s + raw.length, raw, val: raw });
  }
  const re = /\b(?:near|outside|at|in)\s+([A-Z][a-z]{2,})\b/g; let q; while ((q = re.exec(t))) if (!STOP.has(q[1].toLowerCase())) c.push({ s: q.index + q[0].length - q[1].length, e: q.index + q[0].length, type: "location", raw: q[1], val: q[1] });
  const pri: any = { phone: 0, vehicle: 0, transaction: 0, event: 0, organization: 1, location: 2, person: 3 };
  const kept: M[] = [];
  for (const m of c.filter((x) => x.type).sort((a, b) => pri[a.type] - pri[b.type] || b.e - b.s - (a.e - a.s))) if (!kept.some((k) => m.s < k.e && m.e > k.s)) kept.push(m);
  return kept.sort((a, b) => a.s - b.s);
}

type V = [RegExp, string, number, boolean, (a: string, b: string) => boolean];
const COMM = (x: string) => x === "person" || x === "phone" || x === "organization", PARTY = (x: string) => x === "person" || x === "organization" || x === "account";
const VERBS: V[] = [
  [/(?:received (?:an? )?calls? from|calls? from|called by)/i, "called", .88, true, (a, b) => COMM(a) && COMM(b)],
  [/(?:called|phoned|rang|spoke (?:to|with)|to call|contacted)/i, "called", .86, false, (a, b) => COMM(a) && COMM(b)],
  [/(?:met|seen with|spotted with|accompanied|meeting with)/i, "met", .88, false, (a, b) => PARTY(a) && PARTY(b)],
  [/(?:paid|transferred|sent|deposited|remitted|gave)/i, "paid", .86, false, (a, b) => PARTY(a) && (PARTY(b) || b === "transaction")],
  [/(?:received|collected|withdrew)/i, "received", .84, false, (a, b) => PARTY(a) && (PARTY(b) || b === "transaction")],
  [/(?:owned by|registered to|belongs to)/i, "owns", .88, true, (a, b) => !PARTY(a) && PARTY(b)],
  [/(?:owns|purchased|bought)(?! by)/i, "owns", .86, false, (a, b) => PARTY(a) && !PARTY(b)],
  [/(?:used by|driven by|carried by)/i, "uses", .86, true, (a, b) => (a === "phone" || a === "vehicle") && b === "person"],
  [/(?:uses|used|drove|drives|carrying)(?! by)/i, "uses", .84, false, (a, b) => a === "person" && (b === "phone" || b === "vehicle")],
  [/(?:works? (?:for|at)|employed|director of)/i, "works_for", .84, false, (a, b) => a === "person" && b === "organization"],
  [/(?:near|outside|at|in|from|visited|reached|arrived|seen|observed|parked|spotted)/i, "presence", .8, false, (a, b) => b === "location"],
];
const RULES: [string, string, string, number][] = [["person", "phone", "uses", .86], ["organization", "vehicle", "owns", .78], ["person", "vehicle", "uses", .74], ["vehicle", "location", "observed_at", .84], ["phone", "location", "located_at", .8], ["person", "location", "visited", .8], ["organization", "location", "based_at", .74], ["person", "organization", "associated_with", .68], ["person", "person", "associated_with", .62], ["person", "transaction", "involved_in", .7], ["organization", "transaction", "involved_in", .74], ["person", "account", "owns", .84]];
function relate(ta: string, tb: string, between: string, skipMoney = false): [string, number, boolean, boolean] {
  let best: any = null;
  for (const v of VERBS) { if (skipMoney && (v[1] === "paid" || v[1] === "received")) continue; const m = between.match(v[0]); if (m && v[4](ta, tb) && (!best || m.index! >= best[0])) best = [m.index, v]; }
  if (best) { const v: V = best[1]; let rel = v[1], rev = v[3];
    if (rel === "presence") rel = ({ person: "visited", vehicle: "observed_at", phone: "located_at", organization: "based_at" } as any)[ta] || "located_at";
    if (rel === "paid" && tb !== "transaction") rel = "transferred_to";
    if (rel === "received" && tb !== "transaction") { rel = "transferred_to"; rev = true; }
    return [rel, v[2], rev, true]; }
  for (const [a, b, r, c] of RULES) { if (ta === a && tb === b) return [r, c, false, false]; if (ta === b && tb === a) return [r, c, true, false]; }
  return ["mentioned_with", .55, false, false];
}
const SYM = new Set(["associated_with", "met", "called", "messaged", "seen_near", "mentioned_with"]);
export const LABEL: any = { called: "called", met: "met", paid: "paid", received: "received", owns: "owns", uses: "uses", works_for: "works for", visited: "visited", observed_at: "observed at", located_at: "located at", based_at: "based at", associated_with: "associated with", involved_in: "involved in", transferred_to: "transferred to", seen_near: "seen near", mentioned_with: "mentioned with" };
const GENERIC = ["associated_with", "mentioned_with", "seen_near"];
function hash(s: string) { let h = 5381; for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) | 0; return (h >>> 0).toString(36); }

export class Engine {
  ents = new Map<string, any>(); rels = new Map<string, any>(); evid = new Map<string, any>(); idx = new Map<string, string>(); cases = new Map<string, any>();
  merges: any[] = []; docs: any[] = []; lastMs = 0; seq = 0;
  stats() { return { cases: this.cases.size, entities: this.ents.size, relationships: this.rels.size, evidence: this.evid.size, cross_case_entities: [...this.ents.values()].filter((e) => e.cases.length > 1).length, merges: this.merges.length, last_ms: this.lastMs, model_calls: 0 }; }
  reset() { this.ents.clear(); this.rels.clear(); this.evid.clear(); this.idx.clear(); this.cases.clear(); this.merges = []; this.docs = []; this.lastMs = 0; }
  private make(type: string, key: string, name: string, cs: string, ts: string) { const id = `${type.slice(0, 3).toUpperCase()}-${++this.seq}`; const e = { id, type, name, key, aliases: [] as string[], cases: [cs], first_seen: ts?.slice(0, 10), last_seen: ts?.slice(0, 10), mentions: 0 }; this.ents.set(id, e); this.idx.set(type + "|" + key, id); return e; }
  private person(raw: string, cs: string, ts: string) {
    const toks = raw.replace(/[.,]/g, " ").toLowerCase().split(/\s+/).filter(Boolean); if (!toks.length || toks.join("").length < 3) return null; const key = toks.join(" ");
    const hit = this.idx.get("person|" + key); if (hit) return this.ents.get(hit);
    let best: any = null;
    for (const e of this.ents.values()) { if (e.type !== "person") continue; const pt = e.key.split(" "); let sc = 0, how = "";
      if (toks.length > 1 && toks.length === pt.length && toks[toks.length - 1] === pt[pt.length - 1] && toks.every((t: string, i: number) => t === pt[i] || (t.length === 1 && pt[i].startsWith(t)) || (pt[i].length === 1 && t.startsWith(pt[i])))) { sc = .85; how = "initial-match"; }
      else if (toks.length === pt.length && key.length > 5 && lev(key, e.key) >= .86 && lev(toks[0], pt[0]) >= .85 && lev(toks[toks.length - 1], pt[pt.length - 1]) >= .75) { sc = lev(key, e.key); how = "fuzzy-name"; }
      if (sc && (!best || sc > best[0])) best = [sc, e, how]; }
    const disp = raw.split(/\s+/).map((w) => w[0].toUpperCase() + w.slice(1)).join(" ");
    if (best) { const e = best[1]; this.idx.set("person|" + key, e.id); if (!e.aliases.includes(disp) && disp !== e.name) e.aliases.push(disp); this.merges.push({ entity_id: e.id, entity: e.name, alias: disp, method: best[2], confidence: Math.round(best[0] * 100) / 100 }); return e; }
    return this.make("person", key, disp, cs, ts);
  }
  private resolve(m: M, cs: string, ts: string) {
    if (m.type === "person") return this.person(m.val, cs, ts);
    let key = m.val.toLowerCase(), name = m.val.replace(/\s+/g, " ");
    if (m.type === "phone") { const d = m.val.replace(/\D/g, "").slice(-10); key = d; name = "+91-" + d; }
    else if (m.type === "vehicle") { key = m.val.replace(/[\s-]/g, "").toUpperCase(); name = key; }
    else if (m.type === "organization") key = m.val.toLowerCase().replace(/\b(pvt|ltd|limited|llp|inc|private)\b\.?/g, "").replace(/[^a-z0-9]+/g, " ").trim();
    else if (m.type === "transaction") { key = `${m.amt}@${(ts || "").slice(0, 10)}`; name = inr(m.amt || 0) + (ts ? " · " + ts.slice(0, 10) : ""); }
    else if (m.type === "location") key = key.replace(/^bombay$/, "mumbai").replace(/^bangalore$/, "bengaluru").replace(/^new delhi$/, "delhi");
    const hit = this.idx.get(m.type + "|" + key);
    if (hit) { const e = this.ents.get(hit), f = m.raw.replace(/\s+/g, " "); if (f !== e.name && !e.aliases.includes(f) && ["phone", "vehicle", "organization"].includes(m.type)) { e.aliases.push(f); this.merges.push({ entity_id: e.id, entity: e.name, alias: f, method: "normalised-identifier", confidence: .99 }); } return e; }
    return this.make(m.type, key, name, cs, ts);
  }
  private addRel(a: string, b: string, rel: string, conf: number, ev: string, cs: string, ts: string, attrs: any = {}) {
    if (a === b) return false; if (SYM.has(rel) && a > b) [a, b] = [b, a]; const k = `${a}|${b}|${rel}`; conf = Math.min(.98, Math.max(.3, conf));
    const r = this.rels.get(k);
    if (r) { if (!r.support[ev]) { r.support[ev] = conf; r.evidence_ids.push(ev); r.count++; r.confidence = noisy(Object.values(r.support)); } if (!r.case_ids.includes(cs)) r.case_ids.push(cs); if (ts) { if (!r.start_time || ts < r.start_time) r.start_time = ts; if (!r.end_time || ts > r.end_time) r.end_time = ts; } Object.assign(r.attrs, attrs); return false; }
    this.rels.set(k, { id: "REL-" + this.rels.size, source: a, target: b, relation: rel, confidence: conf, support: { [ev]: conf }, evidence_ids: [ev], case_ids: [cs], start_time: ts || undefined, end_time: ts || undefined, count: 1, attrs }); return true;
  }
  private unitRels(items: { m: M; e: any }[], text: string, cs: string, ts: string, ev: string, structured: boolean) {
    const out: any[] = [];
    if (structured) {
      const src = items.filter((x) => x.m.role === "src" && x.m.type !== "transaction"), dst = items.filter((x) => x.m.role === "dst" && x.m.type !== "transaction"), free = items.filter((x) => !x.m.role);
      const prim = (g: any[], o: string[]) => { for (const t of o) { const f = g.find((x) => x.m.type === t); if (f) return f; } return g[0]; };
      const tie = (g: any[]) => { const p = prim(g, ["phone", "account", "person", "organization"]); g.forEach((x) => { if (p && x.e.id !== p.e.id) { const [r, c, rev] = relate(p.m.type, x.m.type, ""); out.push(rev ? [x.e.id, p.e.id, r, Math.max(c, .84)] : [p.e.id, x.e.id, r, Math.max(c, .84)]); } }); };
      tie(src); tie(dst);
      const money = items.find((x) => x.m.type === "transaction");
      if (src.length && dst.length) { const a = prim(src, ["person", "organization", "phone"]), b = prim(dst, ["person", "organization", "phone"]); out.push([a.e.id, b.e.id, money ? "transferred_to" : "called", .9, money ? { amount: money.m.amt } : {}]); }
      const anchor = src.length ? prim(src, ["person", "organization", "phone"]) : free.find((x) => x.m.type === "person") || free.find((x) => x.m.type === "organization") || free[0];
      free.forEach((x) => { if (!anchor || x.e.id === anchor.e.id) return;
        if (x.m.type === "location") (src.length ? src : free).filter((y) => ["person", "phone", "vehicle", "organization"].includes(y.m.type)).slice(0, 3).forEach((y) => out.push([y.e.id, x.e.id, relate(y.m.type, "location", "")[0], .8]));
        else if (x.m.type === "transaction") { if (!(src.length && dst.length)) out.push([anchor.e.id, x.e.id, "involved_in", .8, { amount: x.m.amt }]); }
        else { const [r, c, rev] = relate(anchor.m.type, x.m.type, ""); out.push(rev ? [x.e.id, anchor.e.id, r, Math.max(c, .76)] : [anchor.e.id, x.e.id, r, Math.max(c, .76)]); } });
    } else {
      for (let i = 0; i < items.length; i++) for (let j = i + 1; j < Math.min(items.length, i + 4); j++) {
        const A = items[i], B = items[j], full = text.slice(A.m.e, B.m.s); if (B.m.s < A.m.e || full.length > 140 || /[.!?]\s+[A-Z]/.test(full)) continue;
        const inter = items.slice(i + 1, j), onlyLoc = inter.every((x) => x.m.type === "location"); let seg = full;
        if (inter.length && onlyLoc) { seg = ""; let p = A.m.e; for (const x of inter) { seg += text.slice(p, x.m.s).replace(/\b(near|at|in|outside|from)\s*$/i, ""); p = x.m.e; } seg += text.slice(p, B.m.s); } else if (inter.length) seg = text.slice(inter[inter.length - 1].m.e, B.m.s);
        const [r, c, rev, verb] = relate(A.m.type, B.m.type, seg, inter.length > 0 && !onlyLoc);
        if (!verb && (inter.length || seg.length > 40 || r === "mentioned_with" || (A.m.type === B.m.type && !["person", "organization"].includes(A.m.type)))) continue;
        const cc = c - Math.min(.08, (seg.length / 40) * .01) - .02 * inter.length, at = A.m.type === "transaction" ? { amount: A.m.amt } : B.m.type === "transaction" ? { amount: B.m.amt } : {};
        out.push(rev ? [B.e.id, A.e.id, r, cc, at] : [A.e.id, B.e.id, r, cc, at]);
      }
      for (let i = 0; i + 2 < items.length; i++) { const [x, y, z] = [items[i], items[i + 1], items[i + 2]];
        if (PARTY(x.m.type) && y.m.type === "transaction" && PARTY(z.m.type)) { const b2 = text.slice(y.m.e, z.m.s), b1 = text.slice(x.m.e, y.m.s);
          if (/\bfrom\b/.test(b2) && /received|got|collected|withdrew/i.test(b1)) out.push([z.e.id, x.e.id, "transferred_to", .88, { amount: y.m.amt }]);
          else if (/\b(to|towards|into)\b/.test(b2) || /paid|sent|transferred|deposited|gave/i.test(b1)) out.push([x.e.id, z.e.id, "transferred_to", .88, { amount: y.m.amt }]); } }
    }
    const spec = new Set(out.filter((o) => !GENERIC.includes(o[2])).map((o) => [o[0], o[1]].sort().join()));
    let n = 0; for (const o of out) { if (GENERIC.includes(o[2]) && spec.has([o[0], o[1]].sort().join())) continue; if (this.addRel(o[0], o[1], o[2], o[3], ev, cs, ts, o[4] || {})) n++; }
    return n;
  }
  ingest(raw: string, cs = "CASE-001", source = "pasted-text") {
    const t0 = performance.now(); if (!this.cases.has(cs)) this.cases.set(cs, { id: cs, title: cs });
    const before = { e: this.ents.size, r: this.rels.size, m: this.merges.length }; const had = new Map([...this.ents].map(([k, v]) => [k, v.cases.length]));
    let units: { text: string; ts: string; fields?: [string, string][] }[] = []; let ctx = (findDates(source)[0] || {}).iso || ""; const body = raw.replace(/^\uFEFF/, "").trim();
    const flat = (o: any, p = ""): [string, string][] => (o && typeof o === "object" ? Object.entries(o).flatMap(([k, v]) => flat(v, p ? p + "." + k : k)) : o == null ? [] : [[p, String(o)]]);
    let done = false; const first = body.split(/\r?\n/)[0] || "";
    if (/\.json$/i.test(source) || /^[[{]/.test(body)) { try { let d = JSON.parse(body); if (!Array.isArray(d)) { const ls = Object.values(d).filter(Array.isArray) as any[]; d = ls.length ? ls.sort((a, b) => b.length - a.length)[0] : [d]; } units = d.map((r: any) => ({ fields: flat(r), text: flat(r).map(([k, v]) => `${k}: ${v}`).join(", "), ts: "" })); done = true; } catch { /* treat as text */ } }
    if (!done && (/\.(csv|tsv)$/i.test(source) || (body.split(/\r?\n/).length > 1 && /^[\w .-]+([,;\t|][\w .-]+){2,}$/.test(first)))) {
      const dl = [",", ";", "\t", "|"].sort((a, b) => first.split(b).length - first.split(a).length)[0];
      const cut = (l: string) => { const o: string[] = []; let cur = "", q = false; for (const ch of l) { if (ch === '"') q = !q; else if (ch === dl && !q) { o.push(cur.trim()); cur = ""; } else cur += ch; } o.push(cur.trim()); return o; };
      const rows = body.split(/\r?\n/).filter((l) => l.trim()).map(cut), h = rows[0];
      units = rows.slice(1).map((r) => ({ fields: r.map((c, i) => [h[i] || "col" + i, c] as [string, string]).filter((x) => x[1]), text: r.map((c, i) => `${h[i]}: ${c}`).join(", "), ts: "" })); done = true;
    }
    if (!done) for (const line of body.split(/\r?\n/)) { const l = line.trim(); if (!l) continue; const hd = l.match(/^(?:date|dated)\s*[:-]\s*(.+)$/i); if (hd && findDates(hd[1])[0]) { ctx = findDates(hd[1])[0].iso; continue; }
      const p = l.replace(/\b(Rs|Mr|Mrs|Ms|Dr|No|Pvt|Ltd|Co|St)\./g, "$1\u0001").replace(/\b([A-Z])\.(?=\s?[A-Z])/g, "$1\u0001").replace(/(\d)\.(\d)/g, "$1\u0002$2");
      for (const s of p.split(/(?<=[.!?])\s+(?=[A-Z0-9"'(])|;\s+/)) { const tx = s.replace(/\u0001/g, ".").replace(/\u0002/g, ".").trim(); if (tx.length < 4) continue; const d = findDates(tx)[0]; if (d) ctx = d.iso; units.push({ text: tx, ts: ctx }); } }
    let ev = 0, dup = 0;
    for (const u of units.slice(0, 20000)) {
      const eid = "EVD-" + hash(cs + source + u.text); if (this.evid.has(eid)) { dup++; continue; }
      let ms: M[] = [], ts = u.ts;
      if (u.fields) { let dpart = "", tpart = ""; let pos = 1000;
        for (const [col, val] of u.fields) { const c = col.toLowerCase(), role = /caller|from|sender|source|payer|origin|remitter/.test(c) ? "src" : /receiver|callee|(^|[._])to$|recipient|dest|payee|beneficiar/.test(c) ? "dst" : undefined; pos += 100;
          const P = (type: string, v: string, extra: any = {}) => ms.push({ s: pos, e: pos + v.length, type, raw: val, val: v, role, ...extra });
          if (/date|time|timestamp/.test(c) && !/duration/.test(c)) { const d = findDates(val)[0]; if (d) dpart = d.iso; else if (/^\d{1,2}:\d{2}/.test(val)) tpart = val.slice(0, 5); continue; }
          if (/amount|value|amt|rupee/.test(c) && amount(val)) { P("transaction", val, { amt: amount(val) }); continue; }
          if (/^(\+?91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}$/.test(val)) { P("phone", val); continue; }
          if (/location|city|tower|place|area|town|site/.test(c)) { P("location", val.replace(/\b\w/g, (x) => x.toUpperCase())); continue; }
          if (role || /name|person|suspect|accused|owner|employer|company|org|merchant/.test(c)) { const w = val.split(/\s+/), T = val.replace(/\b\w/g, (x) => x.toUpperCase()); P(w.length > 1 && w.some((x) => ORG.test(x)) ? "organization" : GAZ.has(T) ? "location" : /company|employer|org|merchant/.test(c) ? "organization" : "person", T); continue; }
          if (/vehicle|plate|reg/.test(c)) { P("vehicle", val.toUpperCase()); continue; }
          mentions(val).forEach((m) => ms.push({ ...m, s: m.s + pos, e: m.e + pos })); }
        ts = dpart ? dpart + (tpart ? "T" + tpart : "") : ""; }
      else ms = mentions(u.text);
      const items: any[] = [], seen = new Set<string>();
      for (const m of ms) { const e = this.resolve(m, cs, ts); if (!e || seen.has(e.id)) continue; seen.add(e.id); items.push({ m, e }); }
      if (!items.length) continue;
      items.forEach(({ e }) => { e.mentions++; if (!e.cases.includes(cs)) e.cases.push(cs); if (ts) { const d = ts.slice(0, 10); if (!e.first_seen || d < e.first_seen) e.first_seen = d; if (!e.last_seen || d > e.last_seen) e.last_seen = d; } });
      this.evid.set(eid, { id: eid, case_id: cs, source, text: u.text.slice(0, 1000), timestamp: ts || undefined, entity_ids: items.map((x) => x.e.id) }); ev++;
      this.unitRels(items, u.fields ? "" : u.text, cs, ts, eid, !!u.fields);
    }
    this.docs.push({ name: source, case_id: cs });
    const cross = [...this.ents.values()].filter((e) => e.cases.length > (had.get(e.id) || 1) && e.cases.length > 1);
    this.lastMs = Math.max(1, Math.round(performance.now() - t0));
    return { source, statements: units.length, evidence_added: ev, duplicates_skipped: dup, entities_new: this.ents.size - before.e, relationships_new: this.rels.size - before.r, merges: this.merges.length - before.m, cross_case: cross.length, highlights: cross.slice(0, 4).map((e) => `${e.name} now appears in ${e.cases.length} cases`), ms: this.lastMs };
  }
  eff(removed: string[] = [], minConf = 0, cs?: string, until?: string) { return [...this.rels.values()].filter((r) => !removed.includes(r.id) && r.confidence >= minConf && (!cs || r.case_ids.includes(cs)) && (!until || !r.start_time || r.start_time.slice(0, 10) <= until)); }
  adj(rels: any[]) { const a = new Map<string, Map<string, any>>(); for (const r of rels) for (const [x, y] of [[r.source, r.target], [r.target, r.source]]) { if (!a.has(x)) a.set(x, new Map()); const c = a.get(x)!.get(y); if (!c || r.confidence > c.confidence) a.get(x)!.set(y, r); } return a; }
  comps(rels: any[]) { const a = this.adj(rels), seen = new Set<string>(), out: string[][] = []; for (const n of a.keys()) { if (seen.has(n)) continue; const q = [n], c: string[] = []; seen.add(n); while (q.length) { const u = q.pop()!; c.push(u); for (const v of a.get(u)!.keys()) if (!seen.has(v)) { seen.add(v); q.push(v); } } out.push(c); } return out; }
  graph(cs?: string) {
    const rels = this.eff([], 0, cs), a = this.adj(rels), lp = new Map<string, string>([...a.keys()].map((k) => [k, k]));
    for (let it = 0; it < 12; it++) for (const n of [...a.keys()].sort()) { const cnt = new Map<string, number>(); a.get(n)!.forEach((r, v) => cnt.set(lp.get(v)!, (cnt.get(lp.get(v)!) || 0) + r.confidence)); let b = lp.get(n)!, bv = cnt.get(b) || 0; cnt.forEach((v, k) => { if (v > bv + 1e-9) { b = k; bv = v; } }); lp.set(n, b); }
    const labs = [...new Set(lp.values())], ids = new Set(a.keys()); if (cs) this.ents.forEach((e) => e.cases.includes(cs) && ids.add(e.id)); else if (this.ents.size <= 80) this.ents.forEach((e) => ids.add(e.id));
    const nodes = [...ids].map((id) => { const e = this.ents.get(id); return { id, name: e.name, type: e.type, cases: e.cases, degree: a.get(id)?.size || 0, community: lp.has(id) ? labs.indexOf(lp.get(id)!) + 1 : 0, cross_case: e.cases.length > 1, aliases: e.aliases, first_seen: e.first_seen, last_seen: e.last_seen, mentions: e.mentions }; }).sort((x, y) => y.degree - x.degree).slice(0, 220);
    const keep = new Set(nodes.map((n) => n.id));
    return { nodes, edges: rels.filter((r) => keep.has(r.source) && keep.has(r.target)).sort((x, y) => y.confidence - x.confidence).slice(0, 800).map((r) => ({ id: r.id, source: r.source, target: r.target, relation: r.relation, confidence: r.confidence, count: r.count, cases: r.case_ids, start_time: r.start_time, end_time: r.end_time, evidence_ids: r.evidence_ids, attrs: r.attrs })), truncated: false, total_nodes: ids.size, total_edges: rels.length, edges_truncated: false, communities: labs.length };
  }
  entities(q = "", limit = 40) { const deg = new Map<string, number>(); this.rels.forEach((r) => [r.source, r.target].forEach((x) => deg.set(x, (deg.get(x) || 0) + 1))); const s = q.toLowerCase(); const items = [...this.ents.values()].filter((e) => !s || e.name.toLowerCase().includes(s) || e.aliases.some((a: string) => a.toLowerCase().includes(s))).map((e) => ({ ...e, degree: deg.get(e.id) || 0, cross_case: e.cases.length > 1 })).sort((a, b) => b.degree - a.degree); return { total: items.length, items: items.slice(0, limit) }; }
  relationships() { return [...this.rels.values()].sort((a, b) => b.confidence - a.confidence).map((r) => ({ id: r.id, source: r.source, target: r.target, source_name: this.ents.get(r.source).name, target_name: this.ents.get(r.target).name, relation: r.relation, confidence: r.confidence, count: r.count, start_time: r.start_time })); }
  timeline() { const events = [...this.rels.values()].filter((r) => r.start_time).sort((a, b) => a.start_time.localeCompare(b.start_time)).map((r) => ({ id: r.id, date: r.start_time, relation: r.relation, source: this.ents.get(r.source).name, target: this.ents.get(r.target).name, confidence: r.confidence, text: this.evid.get(r.evidence_ids[0])?.text })); return { events, undated: this.rels.size - events.length }; }
  explain(s: string, t: string, removed: string[] = [], minConf = 0) {
    const A = this.ents.get(s), B = this.ents.get(t); const base = { source: { id: s, name: A?.name, type: A?.type }, target: { id: t, name: B?.name, type: B?.type } };
    if (!A || !B || s === t) return { ...base, connected: false, paths: [], message: "Pick two different entities." };
    const a = this.adj(this.eff(removed, minConf)), dist = new Map([[s, 0]]), prev = new Map<string, string>(), q = new Set([s]);
    while (q.size) { let u = ""; q.forEach((x) => { if (!u || dist.get(x)! < dist.get(u)!) u = x; }); q.delete(u); if (u === t) break; a.get(u)?.forEach((r, v) => { const w = dist.get(u)! - Math.log(Math.max(r.confidence, .01)) + .05; if (w < (dist.get(v) ?? 1e9)) { dist.set(v, w); prev.set(v, u); q.add(v); } }); }
    if (!prev.has(t)) return { ...base, connected: false, paths: [], message: "No evidence-supported path connects these two entities with the current assumptions." };
    const p = [t]; while (p[0] !== s) p.unshift(prev.get(p[0])!);
    const hops = p.slice(1).map((v, i) => { const u = p[i], r = a.get(u)!.get(v); return { from: u, to: v, from_name: this.ents.get(u).name, to_name: this.ents.get(v).name, from_type: this.ents.get(u).type, to_type: this.ents.get(v).type, relation: r.relation, label: LABEL[r.relation] || r.relation, confidence: r.confidence, count: r.count, time: r.start_time, rel_id: r.id, cases: r.case_ids, evidence_ids: r.evidence_ids }; });
    const conf = Math.round(hops.reduce((x, h) => x * h.confidence, 1) * 1000) / 10, times = hops.map((h) => h.time).filter(Boolean).sort() as string[], cases = [...new Set(hops.flatMap((h) => h.cases))];
    const evs = [...new Set(hops.flatMap((h) => h.evidence_ids))].map((id) => this.evid.get(id)).filter(Boolean).map((e) => ({ ...e, entities: e.entity_ids.map((i: string) => this.ents.get(i)).filter(Boolean) })).sort((x, y) => (x.timestamp || "9").localeCompare(y.timestamp || "9"));
    const weak = hops.reduce((m, h) => (h.confidence < m.confidence ? h : m), hops[0]);
    const best = { nodes: p.map((id) => ({ id, name: this.ents.get(id).name, type: this.ents.get(id).type })), hops, confidence: conf, evidence_ids: evs.map((e) => e.id), cases, time_window: { from: times[0], to: times[times.length - 1] }, weakest: weak };
    const narrative = `${A.name} reaches ${B.name} in ${hops.length} step${hops.length > 1 ? "s" : ""}${hops.length > 1 ? " through " + p.slice(1, -1).map((i) => this.ents.get(i).name).join(", ") : ""}${times.length ? `, with records dated ${times[0].slice(0, 10)} to ${times[times.length - 1].slice(0, 10)}` : ""}. Path confidence ${conf}%${hops.length > 1 ? `; weakest link: “${weak.from_name} ${weak.label} ${weak.to_name}” at ${Math.round(weak.confidence * 100)}%` : ""}${cases.length > 1 ? `. It crosses ${cases.length} cases (${cases.join(", ")}), which no single-case view would reveal` : ""}.`;
    return { ...base, connected: true, paths: [best], best, evidence: evs, narrative };
  }
  leads(cs?: string, rels = this.eff([], 0, cs)) {
    const out: any[] = [], by = new Map<string, any[]>(); rels.forEach((r) => [r.source, r.target].forEach((x) => (by.get(x) || by.set(x, []).get(x)!).push(r)));
    const nm = (i: string) => this.ents.get(i).name, add = (kind: string, key: string, title: string, summary: string, score: number, ids: string[], rs: any[], reasons: string[]) => out.push({ id: kind + key, key: kind + key, kind, title, summary, score: Math.round(Math.min(99, score)), entities: ids, reasons, evidence_ids: [...new Set(rs.flatMap((r) => r.evidence_ids))].slice(0, 5), requires_human_review: true });
    by.forEach((rs, id) => { const e = this.ents.get(id), cases = new Set(rs.flatMap((r) => r.case_ids)), evs = new Set(rs.flatMap((r) => r.evidence_ids)), mc = rs.reduce((s, r) => s + r.confidence, 0) / rs.length;
      if (cases.size >= 2 && !["location", "transaction", "event"].includes(e.type)) { const p = [Math.min(1, (cases.size - 1) / 2), mc, Math.min(1, evs.size / 3), Math.min(1, rs.length / 5)]; add("cross_case", id, `Shared ${e.type}: ${e.name}`, `${e.name} appears in ${cases.size} cases (${[...cases].join(", ")}). Verify the records refer to the same real-world entity before drawing conclusions.`, 100 * (.5 * p[0] + .3 * p[1] + .15 * p[2] + .05 * p[3]), [id], rs, [`Cases: ${cases.size} (weight 50%)`, `Mean link confidence ${mc.toFixed(2)} (30%)`, `${evs.size} evidence record(s) (15%)`, `${rs.length} direct links (5%)`]); }
      if (["phone", "vehicle", "account", "email"].includes(e.type)) { const o = new Set(rs.map((r) => (r.source === id ? r.target : r.source)).filter((x) => ["person", "organization"].includes(this.ents.get(x).type))); if (o.size >= 2) add("shared_identifier", id, `${e.name} is tied to ${o.size} different parties`, `The ${e.type} ${e.name} links ${[...o].map(nm).join(", ")}. Shared control, a handover or a mistaken match are all possible.`, 55 + 9 * Math.min(o.size, 4), [id, ...o], rs, [`${o.size} distinct parties`, "Shared identifiers are strong connectors"]); } });
    const flow = new Map<string, number>(); rels.filter((r) => r.relation === "transferred_to").forEach((r) => { const v = +r.attrs.amount || 0; flow.set(r.source, (flow.get(r.source) || 0) + v); flow.set(r.target, (flow.get(r.target) || 0) + v); });
    flow.forEach((v, id) => { if (v >= 100000) add("money_flow", id, `${nm(id)} handles ${inr(v)} in transfers`, `Recorded transfers touching ${nm(id)} total ${inr(v)}.`, 50 + Math.min(30, Math.log10(v) * 4), [id], by.get(id)!.filter((r) => r.relation === "transferred_to"), [`${inr(v)} traced`]); });
    rels.filter((r) => ["called", "met"].includes(r.relation) && r.count >= 3).forEach((r) => add("repeated_contact", r.id, `${nm(r.source)} ↔ ${nm(r.target)}: ${r.count} contacts`, `${r.count} separate records show this contact. Frequency alone is not suspicious.`, 40 + Math.min(25, r.count * 3), [r.source, r.target], [r], [`${r.count} corroborating records`]));
    return out.sort((a, b) => b.score - a.score);
  }
  whatIf(removed: string[], minConf: number) {
    const all = this.eff(), kept = this.eff(removed, minConf), pairs = (rs: any[]) => this.comps(rs).reduce((s, c) => s + (c.length * (c.length - 1)) / 2, 0);
    const b = { components: this.comps(all).length, connected_pairs: pairs(all) }, a = { components: this.comps(kept).length, connected_pairs: pairs(kept) };
    const l1 = new Set(this.leads(undefined, kept).map((l) => l.key)), gone = this.leads(undefined, all).filter((l) => !l1.has(l.key));
    const crit = all.length <= 400 ? all.map((r) => ({ rel_id: r.id, a: this.ents.get(r.source).name, b: this.ents.get(r.target).name, relation: r.relation, isolates: b.connected_pairs - pairs(all.filter((x) => x.id !== r.id)) })).filter((c) => c.isolates > 0).sort((x, y) => y.isolates - x.isolates).slice(0, 5) : [];
    const lost = b.connected_pairs - a.connected_pairs;
    return { before: b, after: a, impact: { connections_lost: lost }, leads_lost: gone, critical_links: crit, verdict: !removed.length && !minConf ? "Nothing removed yet — tick links on the left to test an assumption." : lost > 0 ? `Removing these assumptions breaks ${lost} connected pair(s) and splits the network into ${a.components} group(s) (was ${b.components}); ${gone.length} lead(s) no longer hold. Treat the dependent connections as hypotheses until corroborated.` : "The network stays connected: your conclusions do not depend on what you removed." };
  }
}

export const SAMPLES: Record<string, [string, string, string]> = {
  fir: ["fir_214_2026.txt", "CASE-001", `FIR No. 214/2026\nDate: 12 Sep 2026\nComplainant Suresh Patel reported that Rs. 8,50,000 was transferred from Acme Finance to Northstar Logistics on 10 Sep 2026 against a fake invoice.\nAlice Mehra met Rohan Verma near Habibganj Station in Bhopal on 12/09/2026.\nPhone +91-9876543210 was used by Alice Mehra to call Rohan Verma at 21:40.\nRohan Verma works for Northstar Logistics and handles the Bhopal warehouse.\nCCTV observed vehicle MP09AB1234 outside Northstar Logistics warehouse on 13 Sep 2026.\nAlice Mehra transferred Rs. 2,00,000 to Rohan Verma on 14 Sep 2026.`],
  route: ["warehouse_route_notes.txt", "CASE-002", `Phone 98765 43210 was used near Indore by R. Verma on 15-09-2026.\nVehicle MP 09 AB 1234 was observed near Indore on 16/09/2026 and is registered to Northstar Logistics Pvt Ltd.\nRohan Varma met Karan Malhotra at Ujjain on 17 September 2026.\nKaran Malhotra owns vehicle RJ14CD5678 which was seen at Ujjain Railway Station on 17 Sep 2026.\nKaran Malhotra received Rs. 4,20,000 from Northstar Logistics on 18 Sep 2026.\nKaran Malhotra called Meera Kapoor on 19 Sep 2026 about the shipment.`],
  cdr: ["call_records.csv", "CASE-001", `caller_name,caller_number,receiver_name,receiver_number,date,time,duration_sec,tower_location\nAlice Mehra,9876543210,Rohan Verma,9811122233,2026-09-10,09:14,320,Bhopal\nAlice Mehra,9876543210,Rohan Verma,9811122233,2026-09-11,18:02,145,Bhopal\nRohan Verma,9811122233,Alice Mehra,9876543210,2026-09-12,21:40,610,Bhopal\nRohan Verma,9811122233,Karan Malhotra,9899900011,2026-09-15,11:20,95,Indore\nRohan Verma,9811122233,Karan Malhotra,9899900011,2026-09-16,08:55,230,Indore\nKaran Malhotra,9899900011,Meera Kapoor,9822200044,2026-09-19,19:30,410,Ujjain\nMeera Kapoor,9822200044,Alice Mehra,9876543210,2026-09-20,10:05,75,Delhi`],
  ledger: ["transfers_ledger.json", "CASE-003", JSON.stringify([{ from: "Northstar Logistics", to: "Karan Malhotra", amount: "Rs. 4,20,000", date: "2026-09-18", mode: "NEFT" }, { from: "Karan Malhotra", to: "Meera Kapoor", amount: "Rs. 1,50,000", date: "2026-09-21", mode: "UPI" }, { from: "Acme Finance", to: "Northstar Logistics", amount: "Rs. 8,50,000", date: "2026-09-10", mode: "RTGS" }, { from: "Meera Kapoor", to: "Blue Horizon Traders", amount: "Rs. 90,000", date: "2026-09-23", mode: "IMPS" }])],
};
