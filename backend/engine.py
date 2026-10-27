"""SYNTRIX engine: ingestion, entity resolution, temporal graph, explainability, what-if and leads.

Pure Python (standard library only). NetworkX is used for community detection when it is installed,
with a built-in fallback, so the whole platform keeps working on any machine.
"""
from __future__ import annotations

import difflib
import hashlib
import heapq
import json
import math
import os
import re
import threading
from collections import Counter, defaultdict, deque
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from . import nlp

DATA_DIR = Path(os.environ.get("SYNTRIX_DATA", str(Path(__file__).resolve().parent.parent / "data")))
DB_FILE = DATA_DIR / "syntrix.json"

PREFIX = {"person": "PER", "phone": "PHN", "vehicle": "VEH", "location": "LOC", "organization": "ORG",
          "transaction": "TXN", "event": "EVT", "email": "EML", "account": "ACC"}
SYM_REL = {"associated_with", "met", "called", "messaged", "seen_near", "mentioned_with"}
ORG_DROP = {"pvt", "ltd", "limited", "llp", "inc", "co", "corp", "private", "the", "company", "and", "&"}
RELATION_LABEL = {"called": "called", "messaged": "messaged", "met": "met", "paid": "paid", "received": "received",
                  "owns": "owns", "uses": "uses", "works_for": "works for", "visited": "visited",
                  "observed_at": "observed at", "located_at": "located at", "based_at": "based at",
                  "associated_with": "associated with", "involved_in": "involved in", "transferred_to": "transferred to",
                  "seen_near": "seen near", "occurred_at": "occurred at", "mentioned_with": "mentioned with", "interviewed": "questioned"}


def noisy_or(vals: Iterable[float]) -> float:
    p = 1.0
    for v in vals:
        p *= (1.0 - min(max(v, 0.0), 0.99))
    return round(min(0.99, 1.0 - p), 3)


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:22] or "x"


def _day(ts: Optional[str]) -> Optional[str]:
    return ts[:10] if ts else None


class Engine:
    def __init__(self, path: Optional[Path] = None, autoload: bool = True):
        self.lock = threading.RLock()
        self.path = Path(path) if path else DB_FILE
        self._reset_state()
        self._cache: Dict[Any, Any] = {}
        if autoload:
            self._load()

    # ------------------------------------------------------------------ state
    def _reset_state(self) -> None:
        self.cases: Dict[str, Dict[str, Any]] = {}
        self.ents: Dict[str, Dict[str, Any]] = {}
        self.evid: Dict[str, Dict[str, Any]] = {}
        self.rels: Dict[str, Dict[str, Any]] = {}
        self.docs: List[Dict[str, Any]] = []
        self.merges: List[Dict[str, Any]] = []
        self.idx: Dict[Tuple[str, str], str] = {}
        self.rel_idx: Dict[Tuple[str, str, str], str] = {}
        self.person_tok: Dict[str, Set[str]] = defaultdict(set)
        self.person_init: Dict[str, Set[str]] = defaultdict(set)
        self.version = 0
        self.mode = "empty"

    def _rebuild_indexes(self) -> None:
        self.idx.clear(); self.rel_idx.clear(); self.person_tok.clear(); self.person_init.clear()
        for e in self.ents.values():
            for k in e.get("keys", [e["key"]]):
                self.idx[(e["type"], k)] = e["id"]
            if e["type"] == "person":
                self._index_person(e)
        for r in self.rels.values():
            self.rel_idx[self._rel_key(r["source"], r["target"], r["relation"])] = r["id"]

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            d = json.loads(self.path.read_text(encoding="utf-8"))
            if d.get("format") != 2:
                return  # legacy file from the first prototype — start clean
            self.cases = {c["id"]: c for c in d["cases"]}
            self.ents = {e["id"]: e for e in d["entities"]}
            self.evid = {e["id"]: e for e in d["evidence"]}
            self.rels = {r["id"]: r for r in d["relationships"]}
            self.docs = d.get("documents", [])
            self.merges = d.get("merges", [])
            self.mode = d.get("mode", "custom")
            self._rebuild_indexes()
        except Exception:
            self._reset_state()

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = {"format": 2, "mode": self.mode, "cases": list(self.cases.values()), "entities": list(self.ents.values()),
                       "evidence": list(self.evid.values()), "relationships": list(self.rels.values()),
                       "documents": self.docs, "merges": self.merges}
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self.path)
        except Exception:
            pass  # persistence is best-effort; the in-memory workspace keeps working

    def _touch(self) -> None:
        self.version += 1
        self._cache.clear()

    def reset(self, mode: str = "empty") -> Dict[str, Any]:
        with self.lock:
            self._reset_state()
            self._cache.clear()
            self.mode = "empty"
            if mode == "demo":
                from .samples import load_demo
                load_demo(self)
                self.mode = "demo"
            self._touch()
            self.save()
            return self.stats()

    # ------------------------------------------------------------------ cases
    def ensure_case(self, case_id: str, title: Optional[str] = None, description: str = "") -> Dict[str, Any]:
        if case_id not in self.cases:
            self.cases[case_id] = {"id": case_id, "title": title or case_id, "description": description,
                                   "status": "open", "documents": 0, "created": datetime.now().strftime("%Y-%m-%d")}
        return self.cases[case_id]

    def create_case(self, title: str, description: str = "") -> Dict[str, Any]:
        with self.lock:
            n = len(self.cases) + 1
            cid = f"CASE-{n:03d}"
            while cid in self.cases:
                n += 1; cid = f"CASE-{n:03d}"
            c = self.ensure_case(cid, title.strip() or cid, description)
            self._touch(); self.save()
            return c

    # ------------------------------------------------------------------ entity resolution
    def _index_person(self, e: Dict[str, Any]) -> None:
        for k in e.get("keys", [e["key"]]):
            for t in k.split():
                if len(t) >= 2:
                    self.person_tok[t].add(e["id"])
            if k:
                self.person_init[k[0]].add(e["id"])

    def _new_entity(self, typ: str, key: str, name: str, case_id: str, ts: Optional[str], extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        eid = f"{PREFIX.get(typ, 'ENT')}-{_slug(key)}-{hashlib.sha1((typ + key).encode()).hexdigest()[:4]}"
        e = {"id": eid, "type": typ, "name": name, "key": key, "keys": [key], "aliases": [], "cases": [case_id],
             "first_seen": _day(ts), "last_seen": _day(ts), "mentions": 0, "metadata": extra or {}}
        e["metadata"]["forms"] = [name] if not extra or "raw" not in extra else [extra["raw"]]
        self.ents[eid] = e
        self.idx[(typ, key)] = eid
        if typ == "person":
            self._index_person(e)
        return e

    def _alias(self, e: Dict[str, Any], text: str) -> None:
        t = text.strip()
        if t and t != e["name"] and t not in e["aliases"] and len(e["aliases"]) < 14:
            e["aliases"].append(t)

    def _log_merge(self, e: Dict[str, Any], alias: str, method: str, conf: float, case_id: str, source: str) -> Dict[str, Any]:
        rec = {"entity_id": e["id"], "entity": e["name"], "type": e["type"], "alias": alias, "method": method,
               "confidence": round(conf, 2), "case_id": case_id, "source": source}
        if not any(m["entity_id"] == e["id"] and m["alias"] == alias for m in self.merges):
            self.merges.append(rec)
        return rec

    def _norm(self, m: nlp.Mention) -> Tuple[str, str]:
        typ, v = m.type, (m.value or m.text).strip()
        if typ == "phone":
            d = re.sub(r"\D", "", v)
            if len(d) > 10 and d.startswith("91"):
                d = d[-10:]
            elif len(d) == 11 and d.startswith("0"):
                d = d[1:]
            return d, (f"+91-{d}" if len(d) == 10 else f"+{d}")
        if typ == "vehicle":
            k = re.sub(r"[\s-]", "", v.upper())
            return k, k
        if typ == "location":
            low = re.sub(r"\s+", " ", v.lower()).strip()
            canon = nlp.LOC_ALIASES.get(low, low)
            return canon, canon.title() if canon != low or low == v.lower() else (v if v[:1].isupper() else v.title())
        if typ == "organization":
            toks = [t for t in re.split(r"[^a-z0-9&]+", v.lower()) if t and t not in ORG_DROP]
            return " ".join(toks) or v.lower(), re.sub(r"\s+", " ", v).strip()
        if typ == "transaction":
            amt = m.meta.get("amount") or nlp.parse_amount(v) or 0
            return f"{amt:g}", nlp.fmt_inr(amt)
        if typ == "email":
            return v.lower(), v.lower()
        if typ == "account":
            d = re.sub(r"\D", "", v)
            return d, f"A/C ••{d[-4:]}" if len(d) >= 6 else d
        if typ == "event":
            return v.upper(), v.upper()
        return v.lower(), v

    def _resolve(self, m: nlp.Mention, case_id: str, ts: Optional[str], source: str) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        typ = m.type
        if typ == "person":
            return self._resolve_person(m, case_id, ts, source)
        key, display = self._norm(m)
        if not key:
            return None, None
        if typ == "transaction" and ts:
            key = f"{key}@{_day(ts)}"
            display = f"{display} · {_day(ts)}"
        eid = self.idx.get((typ, key))
        merge = None
        if eid:
            e = self.ents[eid]
            raw = re.sub(r"\s+", " ", m.text.strip())
            forms = e["metadata"].setdefault("forms", [e["name"]])
            if raw not in forms and typ in ("phone", "vehicle", "location", "organization", "email"):
                if len(forms) < 12:
                    forms.append(raw)
                if raw != e["name"]:
                    self._alias(e, raw)
                    merge = self._log_merge(e, raw, "normalised-identifier" if typ in ("phone", "vehicle", "email") else "name-normalisation",
                                            0.99 if typ in ("phone", "vehicle") else 0.92, case_id, source)
            return e, merge
        if typ == "organization" and len(key) >= 5:
            best = None
            for e in self.ents.values():
                if e["type"] == "organization" and abs(len(e["key"]) - len(key)) <= 3:
                    r = difflib.SequenceMatcher(None, e["key"], key).ratio()
                    if r >= 0.9 and (best is None or r > best[0]):
                        best = (r, e)
            if best:
                e = best[1]
                self._alias(e, m.text.strip()); e["keys"].append(key); self.idx[(typ, key)] = e["id"]
                e["metadata"].setdefault("forms", [e["name"]]).append(re.sub(r"\s+", " ", m.text.strip()))
                return e, self._log_merge(e, m.text.strip(), "fuzzy-name", best[0], case_id, source)
        extra = {k: v for k, v in m.meta.items() if k in ("amount",)}
        extra["raw"] = re.sub(r"\s+", " ", m.text.strip())
        return self._new_entity(typ, key, display, case_id, ts, extra), None

    def _resolve_person(self, m: nlp.Mention, case_id: str, ts: Optional[str], source: str):
        name = (m.value or m.text).strip()
        toks = [t.lower().strip(".") for t in re.split(r"\s+", name) if t.strip(".")]
        if not toks or all(len(t) < 2 for t in toks):
            return None, None
        key = " ".join(toks)
        eid = self.idx.get(("person", key))
        if eid:
            return self.ents[eid], None
        tset = set(toks)
        cand_ids: Set[str] = set()
        for t in toks:
            cand_ids |= self.person_tok.get(t, set())
        strong: List[Tuple[float, str, str]] = []
        singles: List[str] = []
        for pid in cand_ids:
            p = self.ents[pid]
            ptoks = p["key"].split()
            ps = set(ptoks)
            if tset <= ps or ps <= tset:
                if min(len(tset), len(ps)) >= 2:
                    strong.append((0.9, pid, "name-subset"))
                else:
                    singles.append(pid)
                continue
            if len(toks) == len(ptoks) >= 2 and toks[-1] == ptoks[-1] and all(
                    a == b or (len(a) == 1 and b.startswith(a)) or (len(b) == 1 and a.startswith(b)) for a, b in zip(toks[:-1], ptoks[:-1])):
                strong.append((0.85, pid, "initial-match"))
        if not strong and len(key) >= 6:
            SM = difflib.SequenceMatcher
            for pid in self.person_init.get(key[0], set()):
                pk = self.ents[pid]["key"]
                ptoks = pk.split()
                if len(ptoks) != len(toks) or abs(len(pk) - len(key)) > 2:
                    continue
                r = SM(None, pk, key).ratio()
                if r >= 0.86 and SM(None, ptoks[0], toks[0]).ratio() >= 0.85 and SM(None, ptoks[-1], toks[-1]).ratio() >= 0.75:
                    strong.append((r, pid, "fuzzy-name"))
        chosen = None
        if strong:
            strong.sort(reverse=True)
            chosen = strong[0]
        elif len(singles) == 1:
            chosen = (0.78, singles[0], "partial-name")
        elif len(singles) > 1:
            return None, None  # ambiguous bare first/last name: refuse to guess
        if chosen:
            conf, pid, method = chosen
            e = self.ents[pid]
            display = nlp.clean_person(m.text) if not m.meta.get("partial") else m.text
            if len(toks) > len(e["key"].split()):
                self._alias(e, e["name"]); e["name"] = " ".join(w.capitalize() if w.islower() else w for w in display.split())
                e["key"] = key
                if key not in e["keys"]:
                    e["keys"].append(key)
                self.idx[("person", key)] = pid
                self._index_person(e)
            else:
                if key not in e["keys"]:
                    e["keys"].append(key)
                self.idx[("person", key)] = pid
                self._alias(e, display)
            return e, self._log_merge(e, display, method, conf, case_id, source)
        display = " ".join(w if (w[:1].isupper() and not w.isupper()) else w.capitalize() for w in name.split())
        return self._new_entity("person", key, display, case_id, ts, {"partial": True} if m.meta.get("partial") else {}), None

    # ------------------------------------------------------------------ relationships
    @staticmethod
    def _rel_key(a: str, b: str, rel: str) -> Tuple[str, str, str]:
        if rel in SYM_REL and a > b:
            a, b = b, a
        return (a, b, rel)

    def _add_rel(self, a: str, b: str, rel: str, conf: float, ev_id: str, case_id: str, ts: Optional[str],
                 attrs: Optional[Dict[str, Any]] = None) -> Tuple[Dict[str, Any], bool]:
        if a == b:
            return {}, False
        key = self._rel_key(a, b, rel)
        rid = self.rel_idx.get(key)
        conf = round(min(max(conf, 0.3), 0.98), 3)
        if rid:
            r = self.rels[rid]
            if ev_id not in r["support"]:
                r["support"][ev_id] = conf
                r["evidence_ids"].append(ev_id)
                r["count"] += 1
                r["confidence"] = noisy_or(r["support"].values())
            if case_id not in r["case_ids"]:
                r["case_ids"].append(case_id)
            if ts:
                r["start_time"] = min(filter(None, [r["start_time"], ts])) if r["start_time"] else ts
                r["end_time"] = max(filter(None, [r["end_time"], ts])) if r["end_time"] else ts
            if attrs:
                r["attrs"].update({k: v for k, v in attrs.items() if v is not None})
            return r, False
        rid = "REL-" + hashlib.sha1("|".join(key).encode()).hexdigest()[:10]
        r = {"id": rid, "source": key[0] if rel in SYM_REL else a, "target": key[1] if rel in SYM_REL else b, "relation": rel,
             "confidence": conf, "support": {ev_id: conf}, "evidence_ids": [ev_id], "case_ids": [case_id],
             "start_time": ts, "end_time": ts, "count": 1, "attrs": dict(attrs or {})}
        self.rels[rid] = r
        self.rel_idx[key] = rid
        return r, True

    # ------------------------------------------------------------------ ingestion
    def ingest(self, raw: Any, case_id: str = "CASE-001", source_name: str = "manual-input",
               timestamp: Optional[str] = None) -> Dict[str, Any]:
        with self.lock:
            parsed = nlp.parse_document(source_name, raw, timestamp)
            return self._ingest_parsed(parsed, case_id, source_name, timestamp)

    def _ingest_parsed(self, parsed: nlp.ParsedDoc, case_id: str, source: str, doc_ts: Optional[str]) -> Dict[str, Any]:
        case = self.ensure_case(case_id)
        before_cases = {eid: len(e["cases"]) for eid, e in self.ents.items()}
        before_ents = set(self.ents)
        before_rels = set(self.rels)
        merges_before = len(self.merges)
        summary = {"source": source, "case_id": case_id, "format": parsed.kind, "statements": len(parsed.units), "evidence_added": 0,
                   "duplicates_skipped": 0, "no_entities": 0, "warnings": list(parsed.warnings), "dates_found": 0}
        touched: Set[str] = set()
        new_rel_ids: List[str] = []
        for unit in parsed.units:
            eid_ev = "EVD-" + hashlib.sha1(f"{case_id}|{source}|{unit.label}|{unit.text}".encode("utf-8", "ignore")).hexdigest()[:10]
            if eid_ev in self.evid:
                summary["duplicates_skipped"] += 1
                continue
            if unit.fields is not None:
                mentions, ts, free, tags, attrs = nlp.row_mentions(unit.fields, doc_ts)
                structured = True
            else:
                mentions, dates, tags = nlp.extract_mentions(unit.text)
                mentions = nlp.spacy_boost(unit.text, mentions)
                ts, free, attrs, structured = unit.ts or doc_ts, unit.text, {}, False
                summary["dates_found"] += len(dates)
            if ts:
                summary["dates_found"] += 1 if structured else 0
            items: List[Tuple[nlp.Mention, Dict[str, Any]]] = []
            seen: Set[str] = set()
            for m in mentions:
                e, merge = self._resolve(m, case_id, ts, source)
                if e is None or e["id"] in seen:
                    continue
                seen.add(e["id"])
                items.append((m, e))
            if not items:
                summary["no_entities"] += 1
                continue
            conf_ev = round(sum(m.conf for m, _ in items) / len(items), 3)
            ev = {"id": eid_ev, "case_id": case_id, "source": source, "label": unit.label, "text": unit.text[:1200], "timestamp": ts,
                  "confidence": conf_ev, "entity_ids": [e["id"] for _, e in items], "tags": sorted(set(tags))[:6]}
            self.evid[eid_ev] = ev
            summary["evidence_added"] += 1
            for m, e in items:
                e["mentions"] += 1
                if case_id not in e["cases"]:
                    e["cases"].append(case_id)
                if ts:
                    e["first_seen"] = min(filter(None, [e["first_seen"], _day(ts)]))
                    e["last_seen"] = max(filter(None, [e["last_seen"], _day(ts)]))
                touched.add(e["id"])
            rels = self._struct_relations(items, attrs, unit.text) if structured else self._text_relations(items, unit.text)
            for a, b, rel, conf, at in rels:
                r, new = self._add_rel(a, b, rel, conf, eid_ev, case_id, ts, at)
                if r and new:
                    new_rel_ids.append(r["id"])
        case["documents"] = case.get("documents", 0) + 1
        new_ents = [self.ents[i] for i in self.ents if i not in before_ents]
        cross = [e for e in self.ents.values() if e["id"] in touched and len(e["cases"]) > before_cases.get(e["id"], 1) and len(e["cases"]) >= 2]
        summary.update({
            "entities_new": len(new_ents),
            "entities_by_type": dict(Counter(e["type"] for e in new_ents)),
            "entities_touched": len(touched),
            "relationships_new": len(set(self.rels) - before_rels),
            "relationships_touched": len(new_rel_ids),
            "merges": len(self.merges) - merges_before,
            "cross_case": len(cross),
        })
        hl: List[str] = []
        for e in cross[:5]:
            hl.append(f"{e['name']} ({e['type']}) now appears in {len(e['cases'])} cases: {', '.join(e['cases'])}")
        for mg in self.merges[merges_before:merges_before + 4]:
            hl.append(f"Resolved “{mg['alias']}” → {mg['entity']} ({mg['method'].replace('-', ' ')}, {int(mg['confidence'] * 100)}%)")
        summary["highlights"] = hl
        self.docs.append({"id": "DOC-" + hashlib.sha1(f"{case_id}{source}{len(self.docs)}".encode()).hexdigest()[:8], "name": source, "case_id": case_id,
                          "statements": summary["statements"], "evidence": summary["evidence_added"], "format": parsed.kind,
                          "added": datetime.now().strftime("%Y-%m-%d %H:%M")})
        self._touch()
        self.save()
        return summary

    # --- relationship post-processing
    @staticmethod
    def _prune_generic(rels):
        generic = {"associated_with", "mentioned_with", "seen_near"}
        specific = {frozenset((a, b)) for a, b, rel, _c, _t in rels if rel not in generic}
        seen, out = set(), []
        for a, b, rel, c, t in rels:
            if rel in generic and frozenset((a, b)) in specific:
                continue
            k = (frozenset((a, b)) if rel in SYM_REL else (a, b), rel)
            if k in seen:
                continue
            seen.add(k); out.append((a, b, rel, c, t))
        return out

    # --- text relations
    def _text_relations(self, items, text):
        out = []
        n = len(items)
        for i in range(n):
            ma, ea = items[i]
            for j in range(i + 1, min(n, i + 4)):
                mb, eb = items[j]
                full = text[ma.end:mb.start]
                if mb.start < ma.end or len(full) > 150 or re.search(r"[.!?]\s+[A-Z]", full):
                    continue
                inter = items[i + 1:j]
                skip: Tuple[str, ...] = ()
                if not inter:
                    seg = full
                elif all(x[0].type == "location" for x in inter):
                    # "Phone X was used near Indore by R. Verma": drop the location phrase so the verb phrase reads naturally
                    pieces, pos = [], ma.end
                    for x in inter:
                        piece = text[pos:x[0].start]
                        piece = re.sub(r"\b(?:near|at|in|outside|around|from|inside|towards?|opposite|beside)\s*$", "", piece)
                        pieces.append(piece)
                        pos = x[0].end
                    pieces.append(text[pos:mb.start])
                    seg = re.sub(r"\s+", " ", " ".join(pieces))
                else:
                    seg = text[inter[-1][0].end:mb.start]
                    skip = ("paid", "received", "flow")
                rel, conf, rev, verb = nlp.detect_relation(ma.type, mb.type, seg, skip)
                if not verb:
                    if inter or len(seg) > 40:
                        continue
                    if ma.type == mb.type and ma.type not in ("person", "organization", "phone"):
                        continue
                    if rel == "mentioned_with" and ma.type == mb.type:
                        continue
                    if ma.type == "transaction" and mb.type == "transaction":
                        continue
                conf = conf - min(0.08, 0.01 * (len(seg) // 40)) - 0.02 * len(inter)
                a, b = (eb, ea) if rev else (ea, eb)
                at: Dict[str, Any] = {}
                for k in (ma, mb):
                    if k.type == "transaction":
                        at["amount"] = k.meta.get("amount")
                out.append((a["id"], b["id"], rel, conf, at))
        # party -> transaction -> party  =>  direct transfer between the two parties
        for i in range(n - 2):
            (m1, e1), (m2, e2), (m3, e3) = items[i], items[i + 1], items[i + 2]
            if m1.type in nlp.PARTY and m2.type == "transaction" and m3.type in nlp.PARTY:
                b2, b1 = text[m2.end:m3.start], text[m1.end:m2.start]
                amt = {"amount": m2.meta.get("amount")}
                if re.search(r"\bfrom\b", b2) and re.search(r"\b(?:received|got|collected|withdrew)\b", b1, re.I):
                    out.append((e3["id"], e1["id"], "transferred_to", .88, amt))
                elif re.search(r"\b(?:to|towards|into)\b|->|→", b2) or re.search(r"\b(?:paid|sent|transferred|deposited|gave|remitted)\b", b1, re.I):
                    out.append((e1["id"], e3["id"], "transferred_to", .88, amt))
            if m1.type == "transaction" and m2.type in nlp.PARTY and m3.type in nlp.PARTY:
                if re.search(r"\bfrom\b", text[m1.end:m2.start]) and re.search(r"\bto\b", text[m2.end:m3.start]):
                    out.append((e2["id"], e3["id"], "transferred_to", .88, {"amount": m1.meta.get("amount")}))
        return self._prune_generic(out)

    # --- structured relations (CSV / JSON rows)
    def _struct_relations(self, items, attrs, text):
        out = []
        AG = ("person", "phone", "vehicle", "organization", "account", "email")
        src = [x for x in items if x[0].meta.get("role") == "src" and x[0].type != "transaction"]
        dst = [x for x in items if x[0].meta.get("role") == "dst" and x[0].type != "transaction"]
        free = [x for x in items if x[0].meta.get("role") not in ("src", "dst")]
        amount_m = next((m for m, _ in items if m.type == "transaction"), None)
        amt = {"amount": amount_m.meta.get("amount")} if amount_m else {}

        def primary(g, order=("phone", "account", "person", "organization", "vehicle", "email")):
            for pref in order:
                for x in g:
                    if x[0].type == pref:
                        return x
            return g[0] if g else None

        def tie(group):
            p = primary(group)
            for m, e in group:
                if p and e["id"] != p[1]["id"]:
                    rel, conf, rev, _ = nlp.detect_relation(p[0].type, m.type, "")
                    a, b = (e, p[1]) if rev else (p[1], e)
                    out.append((a["id"], b["id"], rel, max(conf, .84), {}))
        tie(src); tie(dst)
        ps, pd = primary(src), primary(dst)
        if ps and pd and ps[1]["id"] != pd[1]["id"]:
            mode = " ".join(str(v) for k, v in attrs.items() if k.lower() in ("type", "mode", "channel", "purpose")).lower()
            if amount_m or re.search(r"upi|neft|imps|rtgs|transfer|payment|cheque|cash|wire", mode):
                rel = "transferred_to"
            elif re.search(r"sms|msg|message|whatsapp|chat|text", mode):
                rel = "messaged"
            elif re.search(r"meet", mode):
                rel = "met"
            elif ps[0].type in ("phone", "person") and pd[0].type in ("phone", "person"):
                rel = "called"
            else:
                rel = "associated_with"
            at = dict(amt)
            for k in ("duration", "duration_sec", "seconds", "mode", "type", "channel", "purpose"):
                if k in attrs:
                    at[k] = attrs[k]
            # prefer a person-to-person edge when both parties are named, otherwise the identifiers themselves
            sp = primary(src, ("person", "organization", "phone", "account")) if rel != "transferred_to" else primary(src, ("organization", "person", "account", "phone"))
            dp = primary(dst, ("person", "organization", "phone", "account")) if rel != "transferred_to" else primary(dst, ("organization", "person", "account", "phone"))
            if sp and dp and sp[1]["id"] != dp[1]["id"]:
                out.append((sp[1]["id"], dp[1]["id"], rel, .9, at))
            else:
                out.append((ps[1]["id"], pd[1]["id"], rel, .9, at))
        # everything not tagged as caller/receiver hangs off the source party (or the first named party)
        anchor_group = src
        if not anchor_group:
            pool = [x for x in free if x[0].type in AG]
            first = next((x for x in pool if x[0].type == "person"), None) or next((x for x in pool if x[0].type == "organization"), None) or (pool[0] if pool else None)
            anchor_group = [first] if first else []
            pool_others = [x for x in pool if first and x[1]["id"] != first[1]["id"] and x[0].type in ("phone", "vehicle", "account", "email")]
            for m, e in pool_others:
                rel, conf, rev, _ = nlp.detect_relation(first[0].type, m.type, "")
                a, b = (e, first[1]) if rev else (first[1], e)
                out.append((a["id"], b["id"], rel, max(conf, .8), {}))
            loc_targets = [first] + pool_others if first else pool
            handled = {x[1]["id"] for x in pool_others}
        else:
            loc_targets = src
            handled = set()
        anchor = primary(anchor_group, ("person", "organization", "phone", "account", "vehicle", "email")) if anchor_group else None
        for m, e in free:
            if m.type == "location":
                for lm, le in [x for x in loc_targets if x[0].type in ("person", "phone", "vehicle", "organization")][:4]:
                    rel, conf, rev, _ = nlp.detect_relation(lm.type, "location", "")
                    out.append((le["id"], e["id"], rel, max(conf, .76), {}))
            elif m.type == "transaction":
                if anchor and not (ps and pd):
                    out.append((anchor[1]["id"], e["id"], "paid" if src else "involved_in", .8, amt))
            elif m.type in AG and anchor and e["id"] != anchor[1]["id"] and e["id"] not in handled and (src or m.type in ("organization", "person")):
                rel, conf, rev, _ = nlp.detect_relation(anchor[0].type, m.type, "")
                if m.type == "organization" and anchor[0].type == "person" and set(nlp._hdr_tokens(str(m.meta.get("col", "")))) & {"employer", "company", "firm", "workplace", "works", "organisation", "organization", "org"}:
                    rel, conf, rev = "works_for", .84, False
                a, b = (e, anchor[1]) if rev else (anchor[1], e)
                out.append((a["id"], b["id"], rel, max(conf, .74), {}))
            elif m.type == "event" and anchor:
                out.append((anchor[1]["id"], e["id"], "involved_in", .76, {}))
        return self._prune_generic(out)

    # ------------------------------------------------------------------ graph helpers
    def eff_rels(self, case_id: Optional[str] = None, removed_rels: Iterable[str] = (), removed_ev: Iterable[str] = (),
                 min_conf: float = 0.0, until: Optional[str] = None, types: Optional[Set[str]] = None) -> List[Dict[str, Any]]:
        rr, rv = set(removed_rels), set(removed_ev)
        out = []
        for r in self.rels.values():
            if r["id"] in rr:
                continue
            conf = r["confidence"]
            if rv:
                sup = [c for e, c in r["support"].items() if e not in rv]
                if not sup:
                    continue
                conf = noisy_or(sup)
            if conf < min_conf:
                continue
            if case_id and case_id not in r["case_ids"]:
                continue
            if until and r["start_time"] and _day(r["start_time"]) > until:
                continue
            if types and (self.ents[r["source"]]["type"] not in types or self.ents[r["target"]]["type"] not in types):
                continue
            x = dict(r)
            x["confidence"] = conf
            out.append(x)
        return out

    @staticmethod
    def adjacency(rels: List[Dict[str, Any]]) -> Dict[str, Dict[str, Dict[str, Any]]]:
        adj: Dict[str, Dict[str, Dict[str, Any]]] = defaultdict(dict)
        for r in rels:
            for a, b in ((r["source"], r["target"]), (r["target"], r["source"])):
                cur = adj[a].get(b)
                if cur is None or r["confidence"] > cur["confidence"]:
                    adj[a][b] = r
        return adj

    @staticmethod
    def components(nodes: Iterable[str], adj) -> List[List[str]]:
        seen: Set[str] = set(); comps = []
        for n in nodes:
            if n in seen:
                continue
            q = deque([n]); seen.add(n); comp = [n]
            while q:
                u = q.popleft()
                for v in adj.get(u, {}):
                    if v not in seen:
                        seen.add(v); q.append(v); comp.append(v)
            comps.append(comp)
        return comps

    def communities(self, rels: List[Dict[str, Any]]) -> Dict[str, int]:
        adj = self.adjacency(rels)
        nodes = sorted(adj)
        if not nodes:
            return {}
        groups: List[List[str]] = []
        try:
            if len(nodes) <= 500:
                import networkx as nx  # type: ignore
                G = nx.Graph()
                for a in nodes:
                    for b, r in adj[a].items():
                        if a < b:
                            G.add_edge(a, b, weight=r["confidence"])
                groups = [sorted(g) for g in nx.community.greedy_modularity_communities(G, weight="weight")]
        except Exception:
            groups = []
        if not groups:  # deterministic label propagation fallback
            label = {n: n for n in nodes}
            for _ in range(25):
                changed = False
                for n in nodes:
                    cnt: Counter = Counter()
                    for v, r in adj[n].items():
                        cnt[label[v]] += r["confidence"]
                    if cnt:
                        top = max(cnt.items(), key=lambda kv: (kv[1], -ord(kv[0][0]) if kv[0] else 0, kv[0]))[0]
                        best = max(cnt.values())
                        if cnt[label[n]] >= best - 1e-9:
                            top = label[n]
                        if top != label[n]:
                            label[n] = top; changed = True
                if not changed:
                    break
            by: Dict[str, List[str]] = defaultdict(list)
            for n, l in label.items():
                by[l].append(n)
            groups = list(by.values())
        groups.sort(key=lambda g: (-len(g), g[0]))
        return {n: i + 1 for i, g in enumerate(groups) for n in g}

    def _betweenness(self, adj, k: int = 120) -> Dict[str, float]:
        nodes = sorted(adj)
        if len(nodes) < 3:
            return {n: 0.0 for n in nodes}
        step = max(1, len(nodes) // k)
        srcs = nodes[::step][:k]
        cb: Dict[str, float] = defaultdict(float)
        for s in srcs:
            S = []; P = defaultdict(list); sigma = defaultdict(float); sigma[s] = 1.0
            d = {s: 0}; q = deque([s])
            while q:
                v = q.popleft(); S.append(v)
                for w in adj[v]:
                    if w not in d:
                        d[w] = d[v] + 1; q.append(w)
                    if d[w] == d[v] + 1:
                        sigma[w] += sigma[v]; P[w].append(v)
            delta = defaultdict(float)
            while S:
                w = S.pop()
                for v in P[w]:
                    delta[v] += (sigma[v] / sigma[w]) * (1 + delta[w])
                if w != s:
                    cb[w] += delta[w]
        scale = (len(nodes) / len(srcs))
        n = len(nodes)
        norm = ((n - 1) * (n - 2)) or 1
        return {v: min(1.0, cb[v] * scale / norm) for v in nodes}

    @staticmethod
    def _bridges(adj) -> List[Tuple[str, str, int]]:
        """Iterative Tarjan bridge finding. Returns (u, v, size_of_smaller_side)."""
        disc: Dict[str, int] = {}; low: Dict[str, int] = {}; size: Dict[str, int] = {}
        result: List[Tuple[str, str, int]] = []
        t = 0
        for root in sorted(adj):
            if root in disc:
                continue
            found: List[Tuple[str, str, int]] = []
            disc[root] = low[root] = t; t += 1; size[root] = 1
            stack = [(root, None, iter(sorted(adj[root])))]
            while stack:
                v, parent, it = stack[-1]
                try:
                    w = next(it)
                    if w == parent:
                        continue
                    if w in disc:
                        low[v] = min(low[v], disc[w])
                    else:
                        disc[w] = low[w] = t; t += 1; size[w] = 1
                        stack.append((w, v, iter(sorted(adj[w]))))
                except StopIteration:
                    stack.pop()
                    if stack:
                        p = stack[-1][0]
                        size[p] += size[v]
                        low[p] = min(low[p], low[v])
                        if low[v] > disc[p]:
                            found.append((p, v, size[v]))
            total = size[root]
            result.extend((a, b, min(s, total - s)) for a, b, s in found)
        return result

    # ------------------------------------------------------------------ queries
    def stats(self) -> Dict[str, Any]:
        with self.lock:
            rels = self.eff_rels()
            adj = self.adjacency(rels)
            comps = self.components(list(adj), adj)
            tc = Counter(e["type"] for e in self.ents.values())
            return {"cases": len(self.cases), "entities": len(self.ents), "relationships": len(self.rels), "evidence": len(self.evid),
                    "documents": len(self.docs), "components": len(comps), "largest_component": max((len(c) for c in comps), default=0),
                    "cross_case_entities": sum(1 for e in self.ents.values() if len(e["cases"]) > 1), "merges": len(self.merges),
                    "by_type": dict(tc), "mode": self.mode, "version": self.version,
                    "dated_evidence": sum(1 for e in self.evid.values() if e["timestamp"])}

    def graph(self, case_id: Optional[str] = None, types: Optional[Set[str]] = None, min_conf: float = 0.0, until: Optional[str] = None,
              removed: Iterable[str] = (), limit: int = 220, removed_ev: Iterable[str] = (), max_edges: int = 800) -> Dict[str, Any]:
        with self.lock:
            rels = self.eff_rels(case_id, removed, removed_ev, min_conf, until, types)
            adj = self.adjacency(rels)
            comm = self.communities(rels)
            deg = {n: len(v) for n, v in adj.items()}
            ids = set(deg)
            if case_id:
                ids |= {e["id"] for e in self.ents.values() if case_id in e["cases"] and (not types or e["type"] in types)}
            elif until is None and not types and min_conf == 0 and len(self.ents) <= 80:
                ids |= set(self.ents)
            ranked = sorted(ids, key=lambda i: (-deg.get(i, 0), -len(self.ents[i]["cases"]), self.ents[i]["name"]))
            truncated = len(ranked) > limit
            keep = set(ranked[:limit])
            nodes = []
            for i in ranked[:limit]:
                e = self.ents[i]
                nodes.append({"id": i, "name": e["name"], "type": e["type"], "cases": e["cases"], "degree": deg.get(i, 0),
                              "community": comm.get(i, 0), "cross_case": len(e["cases"]) > 1, "aliases": e["aliases"],
                              "first_seen": e["first_seen"], "last_seen": e["last_seen"], "mentions": e["mentions"]})
            kept = [r for r in rels if r["source"] in keep and r["target"] in keep]
            total_edges = len(kept)
            if total_edges > max_edges:
                kept = sorted(kept, key=lambda r: (-(r["confidence"] + 0.05 * min(r["count"], 6)), r["id"]))[:max_edges]
            edges = [{"id": r["id"], "source": r["source"], "target": r["target"], "relation": r["relation"],
                      "confidence": r["confidence"], "count": r["count"], "cases": r["case_ids"], "start_time": r["start_time"],
                      "end_time": r["end_time"], "evidence_ids": r["evidence_ids"][:8], "attrs": r["attrs"]} for r in kept]
            return {"nodes": nodes, "edges": edges, "truncated": truncated, "total_nodes": len(ranked), "total_edges": total_edges,
                    "edges_truncated": total_edges > max_edges, "communities": len(set(comm.values()))}

    def list_entities(self, case_id=None, typ=None, q=None, limit=200, offset=0) -> Dict[str, Any]:
        with self.lock:
            deg: Counter = Counter()
            for r in self.rels.values():
                deg[r["source"]] += 1; deg[r["target"]] += 1
            xs = [e for e in self.ents.values() if (not case_id or case_id in e["cases"]) and (not typ or e["type"] == typ)]
            if q:
                ql = q.lower()
                xs = [e for e in xs if ql in e["name"].lower() or any(ql in a.lower() for a in e["aliases"])]
            xs.sort(key=lambda e: (-deg[e["id"]], e["name"]))
            return {"total": len(xs), "items": [dict(e, degree=deg[e["id"]], cross_case=len(e["cases"]) > 1) for e in xs[offset:offset + limit]]}

    def entity_detail(self, eid: str) -> Optional[Dict[str, Any]]:
        with self.lock:
            e = self.ents.get(eid)
            if not e:
                return None
            nbrs = []
            ev_ids: List[str] = []
            for r in self.rels.values():
                if eid in (r["source"], r["target"]):
                    other = r["target"] if r["source"] == eid else r["source"]
                    nbrs.append({"rel_id": r["id"], "relation": r["relation"], "direction": "out" if r["source"] == eid else "in",
                                 "other_id": other, "other": self.ents[other]["name"], "other_type": self.ents[other]["type"],
                                 "confidence": r["confidence"], "count": r["count"], "time": r["start_time"], "cases": r["case_ids"]})
                    ev_ids.extend(r["evidence_ids"])
            nbrs.sort(key=lambda x: -x["confidence"])
            ev_ids = list(dict.fromkeys(ev_ids))
            evs = [self.evid[i] for i in ev_ids if i in self.evid][:10]
            return {"entity": e, "neighbors": nbrs, "evidence": evs, "merges": [m for m in self.merges if m["entity_id"] == eid]}

    def list_evidence(self, case_id=None, q=None, entity_id=None, limit=150, offset=0) -> Dict[str, Any]:
        with self.lock:
            xs = [e for e in self.evid.values() if (not case_id or e["case_id"] == case_id) and (not entity_id or entity_id in e["entity_ids"])]
            if q:
                ql = q.lower()
                xs = [e for e in xs if ql in e["text"].lower() or ql in e["source"].lower()]
            xs.sort(key=lambda e: (e["timestamp"] or "9999", e["id"]))
            used = Counter()
            for r in self.rels.values():
                for i in r["evidence_ids"]:
                    used[i] += 1
            page = xs[offset:offset + limit]
            items = []
            for e in page:
                items.append(dict(e, entities=[{"id": i, "name": self.ents[i]["name"], "type": self.ents[i]["type"], "aliases": self.ents[i]["aliases"]}
                                               for i in e["entity_ids"] if i in self.ents], links=used[e["id"]]))
            return {"total": len(xs), "items": items}

    def list_relationships(self, case_id=None) -> List[Dict[str, Any]]:
        with self.lock:
            return [{"id": r["id"], "source": r["source"], "target": r["target"], "source_name": self.ents[r["source"]]["name"],
                     "target_name": self.ents[r["target"]]["name"], "source_type": self.ents[r["source"]]["type"],
                     "target_type": self.ents[r["target"]]["type"], "relation": r["relation"], "confidence": r["confidence"],
                     "count": r["count"], "start_time": r["start_time"], "case_ids": r["case_ids"], "evidence_ids": r["evidence_ids"]}
                    for r in sorted(self.rels.values(), key=lambda r: -r["confidence"]) if not case_id or case_id in r["case_ids"]]

    def timeline(self, case_id=None) -> Dict[str, Any]:
        with self.lock:
            events = []
            undated = 0
            for r in self.rels.values():
                if case_id and case_id not in r["case_ids"]:
                    continue
                if not r["start_time"]:
                    undated += 1
                    continue
                a, b = self.ents[r["source"]], self.ents[r["target"]]
                events.append({"id": r["id"], "date": r["start_time"], "end": r["end_time"], "relation": r["relation"], "source": a["name"], "source_type": a["type"],
                               "target": b["name"], "target_type": b["type"], "confidence": r["confidence"], "count": r["count"],
                               "cases": r["case_ids"], "evidence_id": r["evidence_ids"][0] if r["evidence_ids"] else None,
                               "text": self.evid.get(r["evidence_ids"][0], {}).get("text", "") if r["evidence_ids"] else ""})
            events.sort(key=lambda e: e["date"])
            days = Counter(e["date"][:10] for e in events)
            return {"events": events, "undated": undated, "range": [events[0]["date"][:10], events[-1]["date"][:10]] if events else None,
                    "histogram": sorted(days.items())}

    def resolution(self) -> Dict[str, Any]:
        with self.lock:
            multi = [e for e in self.ents.values() if e["aliases"]]
            return {"merges": list(reversed(self.merges))[:300], "entities_with_aliases": len(multi),
                    "by_method": dict(Counter(m["method"] for m in self.merges))}

    # ------------------------------------------------------------------ explain
    def _best_path(self, adj, s: str, t: str, banned: Optional[Set[str]] = None) -> Optional[List[str]]:
        banned = banned or set()
        dist = {s: 0.0}; prev: Dict[str, str] = {}
        pq = [(0.0, s)]
        while pq:
            d, u = heapq.heappop(pq)
            if u == t:
                break
            if d > dist.get(u, 1e18):
                continue
            for v, r in adj.get(u, {}).items():
                if r["id"] in banned:
                    continue
                w = d + (-math.log(max(r["confidence"], 0.01))) + 0.05
                if w < dist.get(v, 1e18):
                    dist[v] = w; prev[v] = u; heapq.heappush(pq, (w, v))
        if t not in prev and s != t:
            return None
        path = [t]
        while path[-1] != s:
            path.append(prev[path[-1]])
        return path[::-1]

    def explain(self, s: str, t: str, removed: Iterable[str] = (), removed_ev: Iterable[str] = (), min_conf: float = 0.0,
                case_id: Optional[str] = None) -> Dict[str, Any]:
        with self.lock:
            if s not in self.ents or t not in self.ents:
                raise KeyError("Entity not found")
            rels = self.eff_rels(case_id, removed, removed_ev, min_conf)
            adj = self.adjacency(rels)
            a, b = self.ents[s], self.ents[t]
            base = {"source": {"id": s, "name": a["name"], "type": a["type"]}, "target": {"id": t, "name": b["name"], "type": b["type"]}}
            if s == t:
                return dict(base, connected=False, message="Pick two different entities.", paths=[])
            first = self._best_path(adj, s, t)
            if not first:
                return dict(base, connected=False, paths=[], message="No evidence-supported path connects these two entities with the current assumptions.")
            paths = [first]
            for i in range(len(first) - 1):
                ban = {adj[first[i]][first[i + 1]]["id"]}
                alt = self._best_path(adj, s, t, ban)
                if alt and alt not in paths:
                    paths.append(alt)
            out_paths = []
            for p in paths:
                hops = []
                for u, v in zip(p, p[1:]):
                    r = adj[u][v]
                    forward = r["source"] == u
                    hops.append({"from": u, "to": v, "from_name": self.ents[u]["name"], "to_name": self.ents[v]["name"], "from_type": self.ents[u]["type"],
                                 "to_type": self.ents[v]["type"], "relation": r["relation"], "label": RELATION_LABEL.get(r["relation"], r["relation"]),
                                 "directed": forward, "confidence": r["confidence"], "count": r["count"], "time": r["start_time"], "rel_id": r["id"],
                                 "cases": r["case_ids"], "evidence_ids": r["evidence_ids"], "amount": r["attrs"].get("amount")})
                conf = 1.0
                for h in hops:
                    conf *= h["confidence"]
                ev_ids = list(dict.fromkeys(i for h in hops for i in h["evidence_ids"]))
                times = sorted(h["time"] for h in hops if h["time"])
                cases = sorted({c for h in hops for c in h["cases"]})
                out_paths.append({"nodes": [{"id": n, "name": self.ents[n]["name"], "type": self.ents[n]["type"]} for n in p], "hops": hops,
                                  "confidence": round(conf * 100, 1), "evidence_ids": ev_ids, "cases": cases,
                                  "time_window": {"from": times[0] if times else None, "to": times[-1] if times else None},
                                  "weakest": min(hops, key=lambda h: h["confidence"]) if hops else None})
            out_paths.sort(key=lambda p: -p["confidence"])
            best = out_paths[0]
            ev = [dict(self.evid[i], entities=[{"id": x, "name": self.ents[x]["name"], "type": self.ents[x]["type"], "aliases": self.ents[x]["aliases"]} for x in self.evid[i]["entity_ids"] if x in self.ents])
                  for i in best["evidence_ids"] if i in self.evid]
            ev.sort(key=lambda e: e["timestamp"] or "9999")
            return dict(base, connected=True, paths=out_paths, best=best, evidence=ev, narrative=self._narrate(best),
                        note="This is an investigation lead built from the available records. It is not a finding of guilt.")

    def _narrate(self, p: Dict[str, Any]) -> str:
        hops = p["hops"]
        a, b = p["nodes"][0]["name"], p["nodes"][-1]["name"]
        if len(hops) == 1:
            h = hops[0]
            s = f"{a} and {b} are directly linked: {h['from_name']} {h['label']} {h['to_name']}"
        else:
            via = ", ".join(n["name"] for n in p["nodes"][1:-1])
            s = f"{a} reaches {b} in {len(hops)} steps through {via}"
        if p["time_window"]["from"]:
            f, t = p["time_window"]["from"][:10], p["time_window"]["to"][:10]
            s += f", with the supporting records dated {f}" + (f" to {t}" if t != f else "")
        s += f". Overall path confidence is {p['confidence']}%"
        w = p["weakest"]
        if w and len(hops) > 1:
            s += f"; the weakest link is “{w['from_name']} {w['label']} {w['to_name']}” at {int(w['confidence'] * 100)}%"
        if len(p["cases"]) > 1:
            s += f". The path crosses {len(p['cases'])} cases ({', '.join(p['cases'])}), which no single-case view would reveal"
        return s + "."

    # ------------------------------------------------------------------ what-if
    def _metrics(self, rels: List[Dict[str, Any]], case_id: Optional[str]) -> Dict[str, Any]:
        adj = self.adjacency(rels)
        comps = self.components(list(adj), adj)
        in_scope = [e for e in self.ents.values() if not case_id or case_id in e["cases"]]
        cross = sum(1 for r in rels if len(r["case_ids"]) > 1)
        return {"entities": len(in_scope), "connected_entities": len(adj), "relationships": len(rels), "components": len(comps),
                "largest_component": max((len(c) for c in comps), default=0), "cross_case_links": cross,
                "connected_pairs": sum(len(c) * (len(c) - 1) // 2 for c in comps)}

    def what_if(self, remove_rels: Iterable[str] = (), remove_ev: Iterable[str] = (), min_conf: float = 0.0, case_id: Optional[str] = None) -> Dict[str, Any]:
        with self.lock:
            remove_rels, remove_ev = list(remove_rels), list(remove_ev)
            base_rels = self.eff_rels(case_id)
            new_rels = self.eff_rels(case_id, remove_rels, remove_ev, min_conf)
            before, after = self._metrics(base_rels, case_id), self._metrics(new_rels, case_id)
            adj0, adj1 = self.adjacency(base_rels), self.adjacency(new_rels)
            comp1 = {}
            for i, c in enumerate(self.components(list(adj1), adj1)):
                for n in c:
                    comp1[n] = i
            broken_examples = []
            lost_nodes = []
            for c in self.components(list(adj0), adj0):
                groups: Dict[str, List[str]] = defaultdict(list)
                for n in c:
                    groups[str(comp1[n]) if n in comp1 else "iso-" + n].append(n)
                if len(groups) > 1:
                    gl = sorted(groups.values(), key=len, reverse=True)
                    for n in c:
                        if n not in comp1:
                            lost_nodes.append(n)
                    pri = {"person": 0, "organization": 1, "phone": 2, "vehicle": 3}
                    for g1 in range(len(gl)):
                        for g2 in range(g1 + 1, len(gl)):
                            x = sorted(gl[g1], key=lambda n: (pri.get(self.ents[n]["type"], 9), self.ents[n]["name"]))[0]
                            y = sorted(gl[g2], key=lambda n: (pri.get(self.ents[n]["type"], 9), self.ents[n]["name"]))[0]
                            if len(broken_examples) < 12:
                                broken_examples.append({"a": self.ents[x]["name"], "a_type": self.ents[x]["type"], "b": self.ents[y]["name"], "b_type": self.ents[y]["type"]})
            ids1 = {r["id"] for r in new_rels}
            weakened = []
            m1 = {r["id"]: r for r in new_rels}
            for r in base_rels:
                if r["id"] in ids1 and m1[r["id"]]["confidence"] + 1e-6 < r["confidence"]:
                    weakened.append({"id": r["id"], "a": self.ents[r["source"]]["name"], "b": self.ents[r["target"]]["name"], "relation": r["relation"],
                                     "from": r["confidence"], "to": m1[r["id"]]["confidence"]})
            lost = [{"id": r["id"], "a": self.ents[r["source"]]["name"], "b": self.ents[r["target"]]["name"], "relation": r["relation"], "confidence": r["confidence"]}
                    for r in base_rels if r["id"] not in ids1]
            leads0 = {l["key"]: l for l in self._leads(base_rels)}
            leads1 = {l["key"]: l for l in self._leads(new_rels)}
            gone = [{"title": l["title"], "score": l["score"], "kind": l["kind"]} for k, l in leads0.items() if k not in leads1]
            dropped = [{"title": l["title"], "from": l["score"], "to": leads1[k]["score"]} for k, l in leads0.items() if k in leads1 and leads1[k]["score"] + 3 <= l["score"]]
            crit = []
            for u, v, side in sorted(self._bridges(adj1), key=lambda x: -x[2])[:6]:
                r = adj1[u][v]
                crit.append({"rel_id": r["id"], "a": self.ents[u]["name"], "b": self.ents[v]["name"], "relation": r["relation"],
                             "confidence": r["confidence"], "isolates": side})
            return {"before": before, "after": after, "removed_relationships": remove_rels, "removed_evidence": remove_ev, "min_confidence": min_conf,
                    "impact": {"relationships_removed": before["relationships"] - after["relationships"],
                               "components_changed": after["components"] - before["components"],
                               "largest_component_change": after["largest_component"] - before["largest_component"],
                               "connections_lost": before["connected_pairs"] - after["connected_pairs"],
                               "entities_cut_off": len(lost_nodes)},
                    "lost_links": lost[:25], "weakened_links": weakened[:15], "broken_examples": broken_examples,
                    "leads_lost": gone[:8], "leads_weaker": dropped[:8], "critical_links": crit,
                    "verdict": self._whatif_text(before, after, gone)}

    @staticmethod
    def _whatif_text(b, a, gone) -> str:
        lost = b["connected_pairs"] - a["connected_pairs"]
        if b["relationships"] == a["relationships"]:
            return "Nothing changed — the assumptions you removed did not carry any links."
        if lost <= 0:
            return "The network stays fully connected: your conclusions do not depend on what you removed."
        s = f"Removing these assumptions breaks {lost} previously-connected pair{'s' if lost != 1 else ''} of entities"
        if a["components"] > b["components"]:
            s += f" and splits the network into {a['components']} groups (was {b['components']})"
        if gone:
            s += f"; {len(gone)} investigation lead{'s' if len(gone) != 1 else ''} no longer hold"
        return s + ". Treat the dependent connections as hypotheses until independently corroborated."

    # ------------------------------------------------------------------ leads
    def leads(self, case_id: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
        with self.lock:
            key = ("leads", self.version, case_id)
            if key not in self._cache:
                self._cache[key] = self._leads(self.eff_rels(case_id))
            return self._cache[key][:limit]

    def _leads(self, rels: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        E = self.ents
        adj = self.adjacency(rels)
        leads: List[Dict[str, Any]] = []
        by_ent: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for r in rels:
            by_ent[r["source"]].append(r); by_ent[r["target"]].append(r)

        def ev_for(rs, n=4):
            return list(dict.fromkeys(i for r in sorted(rs, key=lambda r: -r["confidence"]) for i in r["evidence_ids"]))[:n]

        def add(kind, key, title, summary, score, ents, rs, reasons):
            leads.append({"id": "LEAD-" + hashlib.sha1(key.encode()).hexdigest()[:8], "key": key, "kind": kind, "title": title, "summary": summary,
                          "score": int(max(5, min(99, round(score)))), "entities": list(ents)[:8], "relationship_ids": [r["id"] for r in rs][:12],
                          "evidence_ids": ev_for(rs), "cases": sorted({c for r in rs for c in r["case_ids"]}), "reasons": reasons})
        # 1 — entity bridging several cases
        for eid, rs in by_ent.items():
            e = E[eid]
            cs = {c for r in rs for c in r["case_ids"]}
            if len(cs) >= 2 and e["type"] in ("person", "phone", "vehicle", "organization", "account", "email"):
                avg = sum(r["confidence"] for r in rs) / len(rs)
                nb = [E[r["target"] if r["source"] == eid else r["source"]]["name"] for r in sorted(rs, key=lambda r: -r["confidence"])[:3]]
                add("cross_case", f"cross:{eid}", f"{e['name']} links {len(cs)} separate cases",
                    f"{e['type'].capitalize()} “{e['name']}” shows up in {', '.join(sorted(cs))}. Connected to {', '.join(nb)}. Reviewing these cases side by side may expose a shared network.",
                    52 + 10 * (len(cs) - 1) + 28 * avg, [eid] + [r["target"] if r["source"] == eid else r["source"] for r in rs][:4], rs,
                    [f"Appears in {len(cs)} cases", f"Average link confidence {int(avg * 100)}%", f"{len(rs)} supporting relationships"])
        # 2 — shared identifier
        for eid, rs in by_ent.items():
            e = E[eid]
            if e["type"] in ("phone", "vehicle", "account", "email"):
                owners = {r["target"] if r["source"] == eid else r["source"] for r in rs if E[r["target"] if r["source"] == eid else r["source"]]["type"] in ("person", "organization")}
                if len(owners) >= 2:
                    names = [E[o]["name"] for o in owners]
                    add("shared_identifier", f"shared:{eid}", f"{e['name']} is tied to {len(owners)} different parties",
                        f"The {e['type']} “{e['name']}” is associated with {', '.join(names[:4])}. A shared {e['type']} can mean shared control, a handover, or a mistaken match — worth verifying.",
                        48 + 9 * min(len(owners), 4) + 14 * max(r["confidence"] for r in rs), [eid] + list(owners), rs,
                        [f"{len(owners)} distinct parties linked", "Shared identifiers are strong connectors"])
        # 3 — money flow
        out_amt: Dict[str, float] = defaultdict(float); in_amt: Dict[str, float] = defaultdict(float)
        flows: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for r in rels:
            if r["relation"] == "transferred_to":
                amt = float(r["attrs"].get("amount") or 0)
                out_amt[r["source"]] += amt; in_amt[r["target"]] += amt
                flows[r["source"]].append(r); flows[r["target"]].append(r)
        for eid in set(out_amt) | set(in_amt):
            o, i = out_amt[eid], in_amt[eid]
            tot = o + i
            if tot >= 100000 or (o > 0 and i > 0):
                kind_txt = "passes money through" if o > 0 and i > 0 else ("receives funds" if i else "sends funds")
                sc = 46 + min(30, math.log10(max(tot, 10)) * 4.2) + (12 if o > 0 and i > 0 else 0)
                add("money_flow", f"flow:{eid}", f"{E[eid]['name']} {kind_txt} ({nlp.fmt_inr(tot)} traced)",
                    f"Transfers touching {E[eid]['name']}: {nlp.fmt_inr(i)} in, {nlp.fmt_inr(o)} out across {len(flows[eid])} recorded transfer(s).",
                    sc, [eid] + [r["target"] if r["source"] == eid else r["source"] for r in flows[eid]][:4], flows[eid],
                    [f"{nlp.fmt_inr(tot)} total traced", "Both inflow and outflow" if o > 0 and i > 0 else "One-directional flow"])
        # 4 — repeated contact
        for r in rels:
            if r["relation"] in ("called", "messaged", "met") and r["count"] >= 3:
                a, b = E[r["source"]], E[r["target"]]
                add("repeated_contact", f"rep:{r['id']}", f"{a['name']} ↔ {b['name']}: {r['count']} recorded contacts",
                    f"{r['count']} separate records show {a['name']} and {b['name']} in contact ({RELATION_LABEL.get(r['relation'])}). Frequency alone isn't suspicious — check timing and content.",
                    40 + min(25, r["count"] * 3) + 15 * r["confidence"], [r["source"], r["target"]], [r],
                    [f"{r['count']} corroborating records", f"Link confidence {int(r['confidence'] * 100)}%"])
        # 5 — hotspot
        for eid, rs in by_ent.items():
            if E[eid]["type"] == "location":
                agents = {r["target"] if r["source"] == eid else r["source"] for r in rs if E[r["target"] if r["source"] == eid else r["source"]]["type"] in ("person", "vehicle", "phone", "organization")}
                if len(agents) >= 3:
                    cs = {c for r in rs for c in r["case_ids"]}
                    add("hotspot", f"hot:{eid}", f"{E[eid]['name']} is a meeting point ({len(agents)} entities)",
                        f"{', '.join(E[a]['name'] for a in list(agents)[:4])} are all placed at {E[eid]['name']}. " + (f"This spans {len(cs)} cases." if len(cs) > 1 else ""),
                        36 + 5 * min(len(agents), 6) + 8 * (len(cs) - 1), [eid] + list(agents), rs, [f"{len(agents)} entities placed here"])
        # 6 — connectors (betweenness)
        if len(adj) >= 6:
            bc = self._betweenness(adj)
            for eid, v in sorted(bc.items(), key=lambda kv: -kv[1])[:3]:
                if v >= 0.12 and E[eid]["type"] in ("person", "organization", "phone", "vehicle", "account"):
                    add("connector", f"conn:{eid}", f"{E[eid]['name']} is a key connector",
                        f"Many shortest paths between other entities pass through {E[eid]['name']}. If this link is wrong or removed, the network fragments (see the What-If Simulator).",
                        38 + 55 * min(v, 0.5), [eid] + list(adj[eid])[:4], by_ent[eid], [f"Betweenness {v:.2f}", f"{len(adj[eid])} direct connections"])
        leads.sort(key=lambda l: (-l["score"], l["title"]))
        return leads
