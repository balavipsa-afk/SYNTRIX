"""Fictional, sanitised sample datasets used by the demo workspace and the 'Load sample' buttons."""
from __future__ import annotations

import json
from typing import Any, Dict, List

FIR_TEXT = """FIR No. 214/2026
Date: 12 Sep 2026
Complainant Suresh Patel reported that Rs. 8,50,000 was transferred from Acme Finance to Northstar Logistics on 10 Sep 2026 against a fake invoice.
Alice Mehra met Rohan Verma near Habibganj Station in Bhopal on 12/09/2026.
Phone +91-9876543210 was used by Alice Mehra to call Rohan Verma at 21:40.
Rohan Verma works for Northstar Logistics and handles the Bhopal warehouse.
CCTV observed vehicle MP09AB1234 outside Northstar Logistics warehouse on 13 Sep 2026.
Alice Mehra transferred Rs. 2,00,000 to Rohan Verma on 14 Sep 2026.
"""

ROUTE_TEXT = """Warehouse Route Surveillance Notes - Indore Division
Phone 98765 43210 was used near Indore by R. Verma on 15-09-2026.
Vehicle MP 09 AB 1234 was observed near Indore on 16/09/2026 and is registered to Northstar Logistics Pvt Ltd.
Rohan Varma met Karan Malhotra at Ujjain on 17 September 2026.
Karan Malhotra owns vehicle RJ14CD5678 which was seen at Ujjain Railway Station on 17 Sep 2026.
Karan Malhotra received Rs. 4,20,000 from Northstar Logistics on 18 Sep 2026.
Karan Malhotra called Meera Kapoor on 19 Sep 2026 about the shipment.
"""

CDR_CSV = """caller_name,caller_number,receiver_name,receiver_number,date,time,duration_sec,tower_location
Alice Mehra,9876543210,Rohan Verma,9811122233,2026-09-10,09:14,320,Bhopal
Alice Mehra,9876543210,Rohan Verma,9811122233,2026-09-11,18:02,145,Bhopal
Rohan Verma,9811122233,Alice Mehra,9876543210,2026-09-12,21:40,610,Bhopal
Rohan Verma,9811122233,Karan Malhotra,9899900011,2026-09-15,11:20,95,Indore
Rohan Verma,9811122233,Karan Malhotra,9899900011,2026-09-16,08:55,230,Indore
Karan Malhotra,9899900011,Meera Kapoor,9822200044,2026-09-19,19:30,410,Ujjain
Meera Kapoor,9822200044,Alice Mehra,9876543210,2026-09-20,10:05,75,Delhi
"""

LEDGER_JSON: List[Dict[str, Any]] = [
    {"from": "Northstar Logistics", "to": "Karan Malhotra", "amount": "Rs. 4,20,000", "date": "2026-09-18", "mode": "NEFT", "case_note": "Hawala suspected"},
    {"from": "Karan Malhotra", "to": "Meera Kapoor", "amount": "Rs. 1,50,000", "date": "2026-09-21", "mode": "UPI", "case_note": "Onward transfer"},
    {"from": "Acme Finance", "to": "Northstar Logistics", "amount": "Rs. 8,50,000", "date": "2026-09-10", "mode": "RTGS", "case_note": "Disputed invoice"},
    {"from": "Meera Kapoor", "to": "Blue Horizon Traders", "amount": "Rs. 90,000", "date": "2026-09-23", "mode": "IMPS", "case_note": "Cash-out"},
]

SAMPLES: Dict[str, Dict[str, Any]] = {
    "fir": {"name": "FIR narrative", "file": "fir_214_2026.txt", "kind": "Text", "case_title": "Operation Meridian",
            "description": "A police FIR with people, a phone, a vehicle, a warehouse and money transfers.", "content": FIR_TEXT},
    "route": {"name": "Surveillance notes", "file": "warehouse_route_notes.txt", "kind": "Text", "case_title": "Warehouse Route",
              "description": "Field notes using different spellings and formats for the same people, phone and vehicle.", "content": ROUTE_TEXT},
    "cdr": {"name": "Call detail records", "file": "call_records.csv", "kind": "CSV", "case_title": "Operation Meridian",
            "description": "Structured phone records: who called whom, when, for how long, from where.", "content": CDR_CSV},
    "ledger": {"name": "Money ledger", "file": "transfers_ledger.json", "kind": "JSON", "case_title": "Financial Trail",
               "description": "A JSON ledger of transfers between people and companies.", "content": json.dumps(LEDGER_JSON, indent=2, ensure_ascii=False)},
}
DEMO_PLAN = [("CASE-001", "fir"), ("CASE-002", "route"), ("CASE-001", "cdr"), ("CASE-003", "ledger")]


def load_sample(engine, key: str, case_id: str) -> Dict[str, Any]:
    s = SAMPLES[key]
    engine.ensure_case(case_id, s["case_title"], "Fictional / sanitised sample case")
    return engine.ingest(s["content"], case_id, s["file"])


def load_demo(engine) -> None:
    for case_id, key in DEMO_PLAN:
        load_sample(engine, key, case_id)
