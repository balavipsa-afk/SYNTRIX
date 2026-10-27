# SYNTRIX

**Connect the evidence. Reveal the pattern.**
Built by **Team PAWTENTIAL** — Avipsa Bal, Pragati Bohra, Kartik Sanap

SYNTRIX is an investigation intelligence platform. You give it scattered case records (plain text, CSV call
records, JSON ledgers) and it builds one connected, time-aware network, shows you where the hidden links are,
and explains every link with the exact sentence it came from.

It gives **leads, not verdicts**. A person always makes the call.

---

## Why we built it

Investigators usually don't lack data. The data is already there, just spread across different files and
cases. A phone number in one case can show up in another, written a different way, and nobody notices.
We wanted a tool that catches that connection *and* shows the proof, so it can be checked by a human.

## What it does

- **Takes any input.** Paste text or upload `.txt`, `.csv` or `.json`. It finds people, phones, vehicles,
  places, companies, money and FIR numbers.
- **Matches the same thing written differently.** `98765 43210` = `+91-9876543210`,
  `MP 09 AB 1234` = `MP09AB1234`, `R. Kulkarni` = `Ravi Kulkarni`.
- **Network view.** Every record becomes a node. Dashed ring = appears in more than one case.
  Thicker line = more confident link.
- **Signal Engine.** Ranks leads with a score you can read (cases 50%, link confidence 30%, evidence 15%,
  connections 5%). No AI model involved, 0 model calls.
- **Connection Explainer.** Pick any two entities and see the path, the confidence, the weakest link and the
  source sentences with the entities highlighted.
- **What-If Simulator.** Switch a link off and see which connections and leads break.
- **Timeline.** Every relationship with its date, in order.

## Try it in 2 minutes

1. Click **Clear all**, set the case box to `CASE-101`, paste this and press **Analyze text**:

```
Date: 14 Oct 2026
Ravi Kulkarni called 9823456710 near Pune Station.
Ravi Kulkarni paid Rs. 2,50,000 to Sunrise Traders on 14 Oct 2026.
Vehicle MH12AB3456 was parked outside Sunrise Traders in Pune.
```

2. Change the case box to `CASE-102`, paste this and press **Analyze text**:

```
Date: 20 Oct 2026
Phone 98234 56710 was used by R. Kulkarni in Nashik.
Vehicle MH 12 AB 3456 is registered to Sunrise Traders Pvt Ltd.
Sunrise Traders paid Rs. 1,00,000 to Neha Joshi on 20 Oct 2026.
```

You should see: `3 new entities, 5 new links, 4 merges, 4 cross-case`. Open **Network**, then **Connection Explainer**
(Ravi Kulkarni → Neha Joshi) and **What-If**. More sample files are in `sample_data/`.

## How it works

```
Case records → Extract entities → Resolve duplicates → Build dated links → Rank leads → Investigator view
```

Everything runs in the browser (`frontend/src/engine.ts`). Your data stays on your machine in `localStorage`.

## Tech

- React + TypeScript + Vite (UI and graph view)
- TypeScript engine: extraction, entity resolution, graph, path-finding, What-If, Signal Engine
- Python (FastAPI + NetworkX) reference version of the same pipeline in `backend/`

## Run it

```bash
cd frontend
npm install
npm run dev      # http://localhost:5173
```

Optional Python backend (not needed by the UI):

```bash
cd backend
pip install -r requirements.txt
python run.py    # http://127.0.0.1:8000/docs
```

## Project structure

| Path | What's in it |
|---|---|
| `frontend/src/engine.ts` | The whole engine |
| `frontend/src/App.tsx` | Screens |
| `frontend/src/GraphCanvas.tsx` | Interactive network graph |
| `backend/` | Python reference version |
| `sample_data/` | Fictional demo files |

## Honest limits

- Extraction is rule-based (no ML model), so lowercase names in free text can be missed. CSV and JSON
  column headers help a lot.
- Confidence numbers are prototype scores, not calibrated probabilities.
- The timeline is a dated list, not an animated replay yet.
- A compact local LLM, PostgreSQL and logins/audit logs are **planned**, not built.
- All data here is fictional. Don't use this on real case data.

## What's next

1. Benchmark matching quality, speed and false matches on labelled data.
2. Add persistent storage, access control and audit logs.
3. Try an optional small local LLM for messy text, and only keep it if the measured results justify it.
