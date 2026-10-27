import type { EType } from "./types";

export const TYPE_COLOR: Record<string, string> = {
  person: "#4F8DF5", phone: "#22D3EE", vehicle: "#F59E0B", location: "#34D399", organization: "#A78BFA",
  transaction: "#F472B6", event: "#FB7185", email: "#38BDF8", account: "#F97316",
};
export const TYPE_LABEL: Record<string, string> = {
  person: "People", phone: "Phones", vehicle: "Vehicles", location: "Locations", organization: "Organizations",
  transaction: "Transactions", event: "Events", email: "Emails", account: "Accounts",
};
export const TYPE_ICON: Record<string, string> = {
  person: "users", phone: "phone", vehicle: "car", location: "pin", organization: "building",
  transaction: "rupee", event: "flag", email: "mail", account: "card",
};
export const COMM_COLORS = ["#4F8DF5", "#22D3EE", "#A78BFA", "#34D399", "#F59E0B", "#F472B6", "#FB7185", "#38BDF8", "#F97316", "#84CC16", "#E879F9", "#2DD4BF"];
export const CASE_COLORS = ["#4F8DF5", "#F59E0B", "#34D399", "#F472B6", "#A78BFA", "#22D3EE", "#FB7185", "#84CC16"];

export const REL_LABEL: Record<string, string> = {
  called: "called", messaged: "messaged", met: "met", paid: "paid", received: "received", owns: "owns", uses: "uses",
  works_for: "works for", visited: "visited", observed_at: "observed at", located_at: "located at", based_at: "based at",
  associated_with: "associated with", involved_in: "involved in", transferred_to: "transferred to", seen_near: "seen near",
  occurred_at: "occurred at", mentioned_with: "mentioned with", interviewed: "questioned",
};
export const relLabel = (r: string) => REL_LABEL[r] || r.replace(/_/g, " ");
export const DIRECTED = new Set(["paid", "received", "owns", "uses", "works_for", "visited", "observed_at", "located_at", "based_at", "involved_in", "transferred_to", "interviewed", "occurred_at"]);

export const pct = (c: number) => `${Math.round(c * 100)}%`;
export const fmtDate = (d?: string | null) => {
  if (!d) return "Undated";
  const [day, time] = d.split("T");
  const dt = new Date(day + "T00:00:00");
  if (isNaN(dt.getTime())) return d;
  const s = dt.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
  return time ? `${s} · ${time}` : s;
};
export const confTone = (c: number) => (c >= 0.85 ? "high" : c >= 0.7 ? "mid" : "low");

const esc = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
/** Split text into plain / entity segments so evidence can show exactly which words became entities. */
export function highlightParts(text: string, ents: { id: string; name: string; type: string; aliases?: string[] }[]) {
  const terms: { t: string; type: string; id: string }[] = [];
  ents.forEach((e) => {
    [e.name, ...(e.aliases || [])].forEach((t) => { if (t && t.length > 1) terms.push({ t, type: e.type, id: e.id }); });
    if (e.type === "phone") {
      const d = e.name.replace(/\D/g, "").slice(-10);
      if (d.length === 10) { terms.push({ t: d, type: e.type, id: e.id }); terms.push({ t: `${d.slice(0, 5)} ${d.slice(5)}`, type: e.type, id: e.id }); }
    }
    if (e.type === "transaction") {
      const m = e.name.match(/₹[\d,]+/);
      if (m) { terms.push({ t: m[0], type: e.type, id: e.id }); terms.push({ t: m[0].replace("₹", "Rs. "), type: e.type, id: e.id }); terms.push({ t: m[0].replace("₹", "Rs "), type: e.type, id: e.id }); }
    }
  });
  if (!terms.length) return [{ text, type: "" as string, id: "" }];
  terms.sort((a, b) => b.t.length - a.t.length);
  const rx = new RegExp("(" + terms.map((x) => esc(x.t)).join("|") + ")", "gi");
  const map = new Map(terms.map((x) => [x.t.toLowerCase(), x]));
  const out: { text: string; type: string; id: string }[] = [];
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = rx.exec(text))) {
    if (m.index > last) out.push({ text: text.slice(last, m.index), type: "", id: "" });
    const hit = map.get(m[0].toLowerCase());
    out.push({ text: m[0], type: hit?.type || "", id: hit?.id || "" });
    last = m.index + m[0].length;
    if (m[0].length === 0) rx.lastIndex++;
  }
  if (last < text.length) out.push({ text: text.slice(last), type: "", id: "" });
  return out;
}

export function safeStore(key: string, val?: string): string | null {
  try {
    if (val === undefined) return window.localStorage.getItem(key);
    window.localStorage.setItem(key, val);
  } catch { /* storage may be blocked */ }
  return null;
}

export const asType = (t: string) => t as EType;
