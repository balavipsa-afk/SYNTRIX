# SYNTRIX

**Connect the evidence. Reveal the pattern.**

Made by **Team PAWTENTIAL**: Avipsa Bal, Pragati Bohra and Kartik Sanap.

SYNTRIX helps investigators find links that are easy to miss. You give it messy case records, and it joins
them into one picture of who and what is connected, and shows the proof for every link.

It gives **leads, not verdicts**. It never says someone is guilty. A person always makes the call.

---

## The problem we're solving

In most investigations the clues are already there. They're just spread over different files and different
cases. A phone number in one case might show up in another, written a little differently, and nobody notices.
Even when someone does spot a link, it's hard to see what it was based on.

## What SYNTRIX does

- **Reads your records.** Paste text or upload a `.txt`, `.csv` or `.json` file. It picks out people, phones,
  vehicles, places, companies and money.
- **Knows when two things are the same.** `98765 43210` and `+91-9876543210` are one phone. `MP 09 AB 1234`
  and `MP09AB1234` are one vehicle. `R. Kulkarni` and `Ravi Kulkarni` are one person.
- **Draws the network.** Everything becomes a dot, and the lines show how they're linked. A dashed red ring
  means it appears in more than one case. A thicker line means we're more sure of the link.
- **Ranks leads (Signal Engine).** Each lead gets a score you can read: how many cases it's in, how sure the
  links are, how much evidence there is, how many connections. No AI model is used, so zero model calls.
- **Explains a connection.** Pick any two things and see the path between them, how confident it is, the
  weakest link, and the exact sentences it came from.
- **Tests a theory (What-If).** Switch a link off and see which connections and leads break.
- **Shows a timeline.** Every link with its date, oldest first.

## Try it in 2 minutes

1. Open the app and click **Clear all**.
2. Type `CASE-101` in the case box, paste this, and click **Analyze text**:

```
Date: 14 Oct 2026
Ravi Kulkarni called 9823456710 near Pune Station.
Ravi Kulkarni paid Rs. 2,50,000 to Sunrise Traders on 14 Oct 2026.
Vehicle MH12AB3456 was parked outside Sunrise Traders in Pune.
```

3. Change the case box to `CASE-102`, paste this, and click **Analyze text**:

```
Date: 20 Oct 2026
Phone 98234 56710 was used by R. Kulkarni in Nashik.
Vehicle MH 12 AB 3456 is registered to Sunrise Traders Pvt Ltd.
Sunrise Traders paid Rs. 1,00,000 to Neha Joshi on 20 Oct 2026.
```

You should see: **3 new entities, 5 new links, 4 merges, 4 cross-case.** The second case was written
differently, but SYNTRIX still matched the phone, vehicle, person and company.

Now try the **Network**, then **Connection Explainer** (Ravi Kulkarni to Neha Joshi), then **What-If**.
There are more demo files in the `sample_data` folder to upload.

## Run it on your computer

You need Node.js installed.

```bash
cd frontend
npm install
npm run dev
```

Then open http://localhost:5173. That's all. The whole thing runs in your browser, and your data stays on
your own machine (saved in the browser's local storage).

## How it works

```
Records  ->  Find entities  ->  Match duplicates  ->  Build dated links  ->  Rank leads  ->  Investigator view
```

The brain of the project is one file: `frontend/src/engine.ts`.

## What's in the folder

| Folder / file | What it is |
|---|---|
| `frontend/src/engine.ts` | The engine: reads records, matches things, builds the network, scores leads |
| `frontend/src/App.tsx` | The screens (Overview, Network, Explainer, What-If, Timeline) |
| `frontend/src/GraphCanvas.tsx` | The draggable network graph |
| `backend/` | A Python (FastAPI + NetworkX) version of the same pipeline. The app doesn't need it |
| `sample_data/` | Fictional demo files you can upload |

To try the Python version: `cd backend`, `pip install -r requirements.txt`, `python run.py`.

## Built with

React, TypeScript and Vite for the app. The engine is TypeScript. The Python version uses FastAPI and NetworkX.

## Being honest about the limits

- It finds names using rules, not a trained model. Lowercase names in free text can be missed. CSV and JSON
  files work better because the column headers help.
- The confidence numbers are prototype scores, not real probabilities.
- The timeline is a dated list, not an animation yet.
- Not built yet, only planned: a small local language model, a PostgreSQL database, logins and audit logs.
- All the data here is made up. Please don't use it on real case data.

## What we'd do next

1. Test how accurate the matching is, and how fast it runs, on proper labelled data.
2. Add a real database, logins and an audit trail.
3. Try a small local language model for messy text, and keep it only if the results show it helps.


## Screenshot

<img width="1535" height="1013" alt="Screenshot 2026-10-27 123552" src="https://github.com/user-attachments/assets/52f61de7-29da-4a6a-b194-cfccc504c6f6" />


