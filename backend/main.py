"""SYNTRIX API — FastAPI wrapper around the investigation engine."""
from __future__ import annotations

import io
import re
from typing import List, Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .engine import Engine
from .samples import SAMPLES, load_sample

app = FastAPI(title="SYNTRIX Investigation Intelligence API", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

engine = Engine()
if not engine.cases and engine.mode == "empty" and not engine.ents:
    engine.reset("demo")          # first launch: start with the fictional demo case so the UI is never blank


# ----------------------------------------------------------------------------- models
class IngestRequest(BaseModel):
    text: str
    case_id: str = "CASE-001"
    source_name: str = "manual-input"
    timestamp: Optional[str] = None


class ExplainRequest(BaseModel):
    source_id: str
    target_id: str
    removed_relationship_ids: List[str] = []
    removed_evidence_ids: List[str] = []
    min_confidence: float = 0.0
    case_id: Optional[str] = None


class WhatIfRequest(BaseModel):
    remove_relationship_ids: List[str] = []
    remove_evidence_ids: List[str] = []
    min_confidence: float = 0.0
    case_id: Optional[str] = None


class CreateCaseRequest(BaseModel):
    title: str
    description: str = ""


class ResetRequest(BaseModel):
    mode: str = "empty"


class SampleRequest(BaseModel):
    case_id: Optional[str] = None


def _csv(v: Optional[str]) -> List[str]:
    return [x for x in (v or "").split(",") if x]


# ----------------------------------------------------------------------------- routes
@app.get("/api/health")
def health():
    return {"status": "ok", "platform": "SYNTRIX", "version": "2.0.0"}


@app.get("/api/stats")
def stats():
    return engine.stats()


@app.get("/api/cases")
def cases():
    with engine.lock:
        ent_n = {}
        for e in engine.ents.values():
            for c in e["cases"]:
                ent_n[c] = ent_n.get(c, 0) + 1
        ev_n = {}
        for e in engine.evid.values():
            ev_n[e["case_id"]] = ev_n.get(e["case_id"], 0) + 1
        return [dict(c, entities=ent_n.get(c["id"], 0), evidence=ev_n.get(c["id"], 0)) for c in engine.cases.values()]


@app.post("/api/cases")
def create_case(req: CreateCaseRequest):
    return engine.create_case(req.title, req.description)


@app.get("/api/samples")
def samples():
    return [{"key": k, "name": s["name"], "file": s["file"], "kind": s["kind"], "description": s["description"], "case_title": s["case_title"]}
            for k, s in SAMPLES.items()]


@app.post("/api/samples/{key}/load")
def load_sample_route(key: str, req: SampleRequest):
    if key not in SAMPLES:
        raise HTTPException(404, "Unknown sample dataset")
    with engine.lock:
        case_id = req.case_id or "CASE-001"
        return load_sample(engine, key, case_id)


@app.post("/api/workspace/reset")
def reset(req: ResetRequest):
    return engine.reset("demo" if req.mode == "demo" else "empty")


@app.post("/api/ingest")
def ingest(req: IngestRequest):
    if not req.text.strip():
        raise HTTPException(400, "Nothing to analyse — paste some text first.")
    with engine.lock:
        engine.ensure_case(req.case_id)
        return engine.ingest(req.text, req.case_id, req.source_name or "manual-input", req.timestamp)


@app.post("/api/analyze")          # backwards-compatible alias used by the first prototype
def analyze(req: IngestRequest):
    return ingest(req)


def _bytes_to_text(raw: bytes, name: str):
    if raw[:5] == b"%PDF-":
        try:
            from pypdf import PdfReader  # type: ignore
            return "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(raw)).pages)
        except Exception:
            raise HTTPException(415, "PDF text extraction needs the optional 'pypdf' package. Export the PDF to .txt, or run: pip install pypdf")
    for enc in ("utf-8-sig", "utf-16", "latin-1"):
        try:
            return raw.decode(enc)
        except Exception:
            continue
    return raw.decode("utf-8", errors="ignore")


@app.post("/api/upload")
async def upload(case_id: str = "CASE-001", file: UploadFile = File(...)):
    raw = await file.read()
    name = file.filename or "document.txt"
    if len(raw) > 25_000_000:
        raise HTTPException(413, "File too large (limit 25 MB)")
    if not raw.strip():
        raise HTTPException(400, f"{name} is empty")
    text = _bytes_to_text(raw, name)
    with engine.lock:
        engine.ensure_case(case_id)
        return engine.ingest(text, case_id, name)


@app.get("/api/graph")
def graph(case_id: Optional[str] = None, types: str = "", min_conf: float = 0.0, until: Optional[str] = None,
          removed: str = "", removed_evidence: str = "", limit: int = 220):
    return engine.graph(case_id or None, set(_csv(types)) or None, min_conf, until or None, _csv(removed), min(max(limit, 20), 600), _csv(removed_evidence))


@app.get("/api/entities")
def entities(case_id: Optional[str] = None, type: Optional[str] = None, q: Optional[str] = None, limit: int = 300, offset: int = 0):
    return engine.list_entities(case_id or None, type or None, q or None, min(limit, 1000), offset)


@app.get("/api/entities/{entity_id}")
def entity_detail(entity_id: str):
    d = engine.entity_detail(entity_id)
    if not d:
        raise HTTPException(404, "Entity not found")
    return d


@app.get("/api/evidence")
def evidence(case_id: Optional[str] = None, q: Optional[str] = None, entity_id: Optional[str] = None, limit: int = 150, offset: int = 0):
    return engine.list_evidence(case_id or None, q or None, entity_id or None, min(limit, 500), offset)


@app.get("/api/relationships")
def relationships(case_id: Optional[str] = None):
    return engine.list_relationships(case_id or None)


@app.post("/api/explain")
def explain(req: ExplainRequest):
    try:
        return engine.explain(req.source_id, req.target_id, req.removed_relationship_ids, req.removed_evidence_ids, req.min_confidence, req.case_id)
    except KeyError:
        raise HTTPException(404, "Entity not found")


@app.post("/api/what-if")
def what_if(req: WhatIfRequest):
    return engine.what_if(req.remove_relationship_ids, req.remove_evidence_ids, req.min_confidence, req.case_id)


@app.get("/api/timeline")
def timeline(case_id: Optional[str] = None):
    return engine.timeline(case_id or None)


@app.get("/api/leads")
def leads(case_id: Optional[str] = None, limit: int = 20):
    with engine.lock:
        out = engine.leads(case_id or None, limit)
        for l in out:
            l["entity_names"] = [{"id": i, "name": engine.ents[i]["name"], "type": engine.ents[i]["type"]} for i in l["entities"] if i in engine.ents]
        return out


@app.get("/api/communities")
def communities():
    with engine.lock:
        comm = engine.communities(engine.eff_rels())
        groups = {}
        for n, c in comm.items():
            groups.setdefault(c, []).append({"id": n, "name": engine.ents[n]["name"], "type": engine.ents[n]["type"]})
        return [{"community": c, "members": m} for c, m in sorted(groups.items())]


@app.get("/api/resolution")
def resolution():
    return engine.resolution()


@app.get("/api/export")
def export():
    with engine.lock:
        return {"entities": list(engine.ents.values()), "relationships": list(engine.rels.values()), "evidence": list(engine.evid.values()),
                "cases": list(engine.cases.values()), "leads": engine.leads(None, 50)}
