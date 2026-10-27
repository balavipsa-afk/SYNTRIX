"""SYNTRIX NLP layer: document parsing, entity extraction and relationship cues.

Fully offline and rule-based so the demo works anywhere. If spaCy and an English model are
installed, `spacy_boost()` is used to add PERSON / ORG / GPE mentions the rules missed.
"""
from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

# --------------------------------------------------------------------------------------
# Vocabulary
# --------------------------------------------------------------------------------------
MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8,
          "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12}
MONTH_RE = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"

STOP = set("""
the a an this that these those on at in to from by with for of and or but as is was were be been being he she they it we i you
his her their its our my your him them us me who whom which what why how when where while whereas also later then after before
during further however meanwhile subsequently thereafter today yesterday tomorrow morning evening night afternoon previously
finally initially additionally according following above below here there once again still just only both each every some any
phone mobile number no call calls called vehicle car truck bike van bus auto record records report reports statement statements
case cases date time amount transaction transactions transfer payment payments account accounts police station evidence note notes
investigator investigators officer officers fir cdr details detail subject source location address name names suspect suspects accused
witness witnesses victim victims complainant informant informants officials official members member employees employee operation
operations investigation sir madam monday tuesday wednesday thursday friday saturday sunday january february march april may june
july august september october november december jan feb mar apr jun jul aug sep sept oct nov dec during upon within without
according meanwhile near outside inside around beside behind opposite towards toward via into onto over under between among
summary description remarks status type mode purpose reason total sum rs inr rupees lakh lakhs crore crores unit section page
statement call-detail dear regards thanks thank please see note ref reference id ids tower sector area zone ward district
state city village town road street highway lane complainants driver owner manager director mr mrs ms dr prof shri smt sri
inspector insp constable surveillance route division department ledger invoice shipment cctv notes dated
""".split())

TITLE_WORDS = ("Mr|Mrs|Ms|Miss|Dr|Prof|Shri|Smt|Sri|Inspector|Insp|Constable|Officer|Accused|Suspect|Witness|Victim|"
               "Complainant|Informant|Driver|Owner|Manager|Director|Proprietor")

ORG_SUFFIX = set("""logistics finance transport transports pvt private ltd limited llp inc corp corporation traders trading enterprises
industries bank group services solutions motors travels cargo exports imports company co associates foundation trust agency systems
technologies holdings mart stores syndicate cooperative couriers carriers freight infra constructions builders developers realty
exchange remittance forex capital securities insurance pharma chemicals textiles agro foods hospitality""".split())

LOC_SUFFIX = set("""road rd street st nagar chowk market station airport hotel mall colony bridge highway square park garden gardens temple
hospital warehouse godown depot port tower junction naka bazaar plaza complex lodge dhaba circle crossing ghat pur bagh vihar enclave
campus terminal factory mill yard residency apartments hub gate toll place marg lane cross layout extension sadan bhawan bhavan mandi stand""".split())

GAZETTEER = """Bhopal Indore Delhi New Delhi Mumbai Navi Mumbai Pune Dwarka Somnath Ashta Ujjain Gwalior Jabalpur Sagar Raisen Sehore Vidisha Dewas
Ratlam Khandwa Burhanpur Hoshangabad Narmadapuram Satna Rewa Chhindwara Betul Mandsaur Neemuch Shajapur Nagpur Nashik Aurangabad Thane
Surat Ahmedabad Vadodara Rajkot Jaipur Jodhpur Udaipur Kota Ajmer Bikaner Lucknow Kanpur Varanasi Agra Allahabad Prayagraj Noida Ghaziabad
Gurgaon Gurugram Faridabad Chandigarh Amritsar Ludhiana Jalandhar Patna Ranchi Kolkata Howrah Guwahati Bhubaneswar Cuttack Raipur Bilaspur
Hyderabad Secunderabad Chennai Bengaluru Bangalore Mysuru Mysore Kochi Cochin Thiruvananthapuram Kozhikode Coimbatore Madurai Visakhapatnam
Vijayawada Goa Panaji Mangaluru Mangalore Dehradun Haridwar Shimla Srinagar Jammu Leh Gangtok Shillong Imphal Kohima Aizawl Itanagar Agartala
Dubai Singapore Kathmandu Dhaka Colombo Karachi Lahore Islamabad Abu Dhabi Sharjah Muscat Doha London Bhind Morena Guna Shivpuri Datia Damoh
Panna Chhatarpur Tikamgarh Seoni Mandla Dindori Balaghat Katni Umaria Anuppur Shahdol Singrauli Sidhi Khargone Barwani Dhar Jhabua Alirajpur
Habibganj Piplani Kolar Bairagarh Arera Colony Kohefiza Berasia Mandideep Obaidullaganj Goa Madhya Pradesh Maharashtra Gujarat Rajasthan
Uttar Pradesh Karnataka Kerala Tamil Nadu Telangana Haryana Punjab Bihar Odisha Assam Jharkhand Chhattisgarh Uttarakhand""".split("\n")
_gaz_words = " ".join(GAZETTEER).split()
# Build multi-word aware gazetteer (known two-word places first)
_MULTI = ["New Delhi", "Navi Mumbai", "Abu Dhabi", "Madhya Pradesh", "Uttar Pradesh", "Tamil Nadu"]
GAZ_SINGLE = set(w for w in _gaz_words if w not in {"New", "Navi", "Abu", "Madhya", "Uttar", "Tamil", "Pradesh", "Nadu", "Dhabi", "Delhi_"})
GAZ_SINGLE |= {"Delhi", "Mumbai", "Dhabi"} - {"Dhabi"}
GAZ_MULTI = set(_MULTI)
LOC_ALIASES = {"bombay": "mumbai", "bangalore": "bengaluru", "calcutta": "kolkata", "madras": "chennai",
               "gurgaon": "gurugram", "allahabad": "prayagraj", "mysore": "mysuru", "cochin": "kochi",
               "mangalore": "mangaluru", "hoshangabad": "narmadapuram", "new delhi": "delhi"}

INCIDENT_TAGS = ["theft", "robbery", "fraud", "burglary", "kidnapping", "smuggling", "murder", "assault", "extortion", "cheating", "forgery",
                 "hawala", "laundering", "accident", "arson", "trafficking", "cybercrime", "phishing", "blackmail", "ransom", "narcotics",
                 "weapon", "embezzlement", "counterfeit", "ransomware", "scam", "bribery", "dacoity", "stolen", "hijack", "illegal", "contraband"]

# --------------------------------------------------------------------------------------
# Data classes
# --------------------------------------------------------------------------------------
@dataclass
class Mention:
    start: int
    end: int
    text: str
    type: str                    # person phone vehicle location organization transaction event email account (date handled apart)
    prio: int = 5
    conf: float = 0.9
    value: str = ""              # cleaned value used for resolution
    meta: Dict[str, Any] = field(default_factory=dict)

    def clone(self) -> "Mention":
        return Mention(self.start, self.end, self.text, self.type, self.prio, self.conf, self.value, dict(self.meta))


@dataclass
class Unit:
    text: str
    ts: Optional[str] = None
    label: str = ""
    fields: Optional[Dict[str, str]] = None
    order: int = 0


@dataclass
class ParsedDoc:
    kind: str
    units: List[Unit]
    warnings: List[str] = field(default_factory=list)
    columns: List[str] = field(default_factory=list)


# --------------------------------------------------------------------------------------
# Dates
# --------------------------------------------------------------------------------------
_TIME = r"(?:[T\s,]+(\d{1,2}):(\d{2})(?::\d{2})?\s*(am|pm|AM|PM)?)?"
DATE_PATTERNS = [
    (re.compile(r"(?<!\d)(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})(?!\d)" + _TIME), "ymd"),
    (re.compile(r"(?<!\d)(\d{1,2})[-/.](\d{1,2})[-/.](20\d{2}|\d{2})(?!\d)" + _TIME), "dmy"),
    (re.compile(rf"(?<!\d)(\d{{1,2}})(?:st|nd|rd|th)?[\s-]+({MONTH_RE})\.?,?[\s-]+(20\d{{2}})" + _TIME, re.I), "dMy"),
    (re.compile(rf"\b({MONTH_RE})\.?[\s-]+(\d{{1,2}})(?:st|nd|rd|th)?,?[\s-]+(20\d{{2}})" + _TIME, re.I), "Mdy"),
]


def _mk_iso(y: int, m: int, d: int, hh: Optional[str], mm: Optional[str], ap: Optional[str]) -> Optional[str]:
    try:
        date(y, m, d)
    except ValueError:
        return None
    iso = f"{y:04d}-{m:02d}-{d:02d}"
    if hh is not None and mm is not None:
        h = int(hh)
        if ap:
            if ap.lower() == "pm" and h < 12:
                h += 12
            if ap.lower() == "am" and h == 12:
                h = 0
        if 0 <= h < 24 and 0 <= int(mm) < 60:
            iso += f"T{h:02d}:{int(mm):02d}"
    return iso


def find_dates(text: str) -> List[Tuple[int, int, str]]:
    out: List[Tuple[int, int, str]] = []
    taken: List[Tuple[int, int]] = []
    for rx, kind in DATE_PATTERNS:
        for m in rx.finditer(text):
            if any(not (m.end() <= a or m.start() >= b) for a, b in taken):
                continue
            g = m.groups()
            hh, mm, ap = g[3], g[4], g[5]
            try:
                if kind == "ymd":
                    iso = _mk_iso(int(g[0]), int(g[1]), int(g[2]), hh, mm, ap)
                elif kind == "dmy":
                    y = int(g[2]); y = y + 2000 if y < 100 else y
                    iso = _mk_iso(y, int(g[1]), int(g[0]), hh, mm, ap)
                elif kind == "dMy":
                    iso = _mk_iso(int(g[2]), MONTHS[g[1][:4].lower().rstrip("t") if g[1][:4].lower() == "sept" else g[1][:3].lower()], int(g[0]), hh, mm, ap)
                else:
                    iso = _mk_iso(int(g[2]), MONTHS[g[0][:4].lower().rstrip("t") if g[0][:4].lower() == "sept" else g[0][:3].lower()], int(g[1]), hh, mm, ap)
            except (KeyError, ValueError):
                iso = None
            if iso:
                out.append((m.start(), m.end(), iso))
                taken.append((m.start(), m.end()))
    out.sort()
    return out


def parse_date_value(v: str) -> Optional[str]:
    ds = find_dates(v.strip())
    return ds[0][2] if ds else None


# --------------------------------------------------------------------------------------
# Regexes for structured identifiers
# --------------------------------------------------------------------------------------
PHONE_RE = re.compile(r"(?<![\w.])(?:\+?91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}(?!\d)|(?<![\w.])\+(?!91)\d{1,3}[\s-]?\d{7,12}(?!\d)")
VEHICLE_RE = re.compile(r"\b[A-Z]{2}[\s-]?\d{1,2}[A-Z]?[\s-]?[A-Z]{1,3}[\s-]?\d{3,4}\b")
MONEY_RE = re.compile(r"(?:₹|Rs\.?|INR)\s*\d[\d,]*(?:\.\d+)?(?:\s*(?:lakhs?|lacs?|crores?|cr|k|thousand|million)\b)?|"
                      r"\b\d[\d,]*(?:\.\d+)?\s*(?:rupees|lakhs?|lacs?|crores?)\b", re.I)
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
ACCOUNT_RE = re.compile(r"(?:a/c|acct?\.?|account)(?:\s*(?:no\.?|number|#))?\s*[:\-]?\s*(\d{9,18})\b", re.I)
FIR_RE = re.compile(r"\bFIR[\s#:\-]*(?:No\.?\s*)?([A-Z]*\d[\w/\-]*)", re.I)


def parse_amount(raw: str) -> Optional[float]:
    s = raw.lower().replace(",", "")
    m = re.search(r"(\d+(?:\.\d+)?)", s)
    if not m:
        return None
    v = float(m.group(1))
    if re.search(r"crore|\bcr\b", s):
        v *= 1e7
    elif re.search(r"lakh|lac", s):
        v *= 1e5
    elif re.search(r"thousand|\dk\b|\bk\b", s):
        v *= 1e3
    elif "million" in s:
        v *= 1e6
    return v


def fmt_inr(v: float) -> str:
    neg = v < 0
    v = abs(v)
    if v == int(v):
        s = str(int(v))
        dec = ""
    else:
        s, dec = f"{v:.2f}".split(".")
        dec = "." + dec
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts + [tail])
    return ("-" if neg else "") + "₹" + s + dec


# --------------------------------------------------------------------------------------
# Name tokens / phrases
# --------------------------------------------------------------------------------------
TOKEN_RE = re.compile(r"(?<![A-Za-z])(?:[A-Z]\.[ \t]?)*[A-Z][a-z]+(?:-[A-Z][a-z]+)?|(?<![A-Za-z])[A-Z]\.(?=[ \t]*[A-Z][a-z])")
ORG_ABBR = {"Pvt", "Co", "Corp", "Inc"}

TITLED_RE = re.compile(rf"\b(?:{TITLE_WORDS})\b\.?[ \t]*:?[ \t]+((?:[A-Z]\.[ \t]?)*[A-Z][a-z]+(?:[ \t]+[A-Z][a-z]+){{0,2}})")
NEAR_RE = re.compile(r"\b(?:near|outside|inside|around|towards?|opposite|beside|behind|adjacent\s+to|close\s+to)\s+(?:the\s+)?([A-Z][a-z]+(?:[ \t]+[A-Z][a-z]+){0,2})")
AT_RE = re.compile(r"\b(?:at|in|reached|arrived\s+at|arrived\s+in|visited|left|entered|stayed\s+at|checked\s+in\s+at)\s+(?:the\s+)?([A-Z][a-z]{2,})\b(?!['’]s)(?![ \t]+[A-Z][a-z])")
CUE_RE = re.compile(r"\b(?:met|called|phoned|rang|texted|messaged|paid|contacted|spoke\s+to|spoke\s+with|meeting\s+with|accompanied\s+by|driven\s+by|owned\s+by|"
                    r"registered\s+to|belonging\s+to|belongs\s+to|friend\s+of|brother\s+of|sister\s+of|associate\s+of|partner\s+of|transferred\s+to|"
                    r"sent\s+to|paid\s+to|alias|aka|a\.k\.a\.?)\s+([A-Z][a-z]{2,})\b(?!['’]s)(?![ \t]+[A-Z][a-z])")
GAZ_RE = re.compile(r"\b(" + "|".join(sorted([re.escape(x) for x in (GAZ_SINGLE | GAZ_MULTI)], key=len, reverse=True)) + r")\b", re.I)


def clean_person(name: str) -> str:
    n = re.sub(rf"^(?:{TITLE_WORDS})\b\.?[ \t]*:?[ \t]*", "", name.strip())
    n = re.sub(r"\s+", " ", n).strip(" .,-")
    return n


def _tok_is_stop(t: str) -> bool:
    return t.lower().rstrip(".") in STOP


def _classify_segment(toks: List[Tuple[int, int, str]]) -> Optional[Tuple[str, int, int, int]]:
    """Classify a run of capitalised tokens -> (type, start, end, prio) or None."""
    words = [w for t in toks for w in t[2].split()]
    s, e = toks[0][0], toks[-1][1]
    low = [w.lower().rstrip(".") for w in words]
    joined = " ".join(words)
    if joined in GAZ_MULTI or all(w in GAZ_SINGLE for w in words) and len(words) <= 2:
        return ("location", s, e, 4)
    if len(words) >= 2 and any(w in ORG_SUFFIX for w in low):
        return ("organization", s, e, 2)
    if len(words) >= 2 and low[-1] in LOC_SUFFIX:
        return ("location", s, e, 4)
    if len(words) == 1:
        return ("location", s, e, 4) if words[0] in GAZ_SINGLE else None
    if len(words) <= 4 and not any(w in GAZ_SINGLE for w in words):
        return ("person", s, e, 5)
    return None


# --------------------------------------------------------------------------------------
# Mention extraction
# --------------------------------------------------------------------------------------
def extract_mentions(text: str) -> Tuple[List[Mention], List[Tuple[int, int, str]], List[str]]:
    cands: List[Mention] = []
    dates = find_dates(text)
    for s, e, iso in dates:
        cands.append(Mention(s, e, text[s:e], "date", 0, 1.0, iso))

    for m in PHONE_RE.finditer(text):
        cands.append(Mention(m.start(), m.end(), m.group(0).strip(), "phone", 1, 0.97, m.group(0).strip()))
    for m in EMAIL_RE.finditer(text):
        cands.append(Mention(m.start(), m.end(), m.group(0), "email", 1, 0.97, m.group(0).lower()))
    for m in ACCOUNT_RE.finditer(text):
        cands.append(Mention(m.start(1), m.end(1), m.group(1), "account", 1, 0.92, m.group(1)))
    for m in MONEY_RE.finditer(text):
        amt = parse_amount(m.group(0))
        if amt and amt >= 1:
            cands.append(Mention(m.start(), m.end(), m.group(0).strip(), "transaction", 1, 0.9, str(amt), {"amount": amt}))
    for m in VEHICLE_RE.finditer(text):
        cands.append(Mention(m.start(), m.end(), m.group(0), "vehicle", 1, 0.95, m.group(0)))
    for m in FIR_RE.finditer(text):
        cands.append(Mention(m.start(), m.end(), m.group(0).strip(), "event", 1, 0.9, "FIR " + m.group(1).upper()))

    # Titled persons: "Suspect: Alice Mehra", "Mr. Sharma"
    for m in TITLED_RE.finditer(text):
        name = m.group(1)
        toks = name.split()
        if _tok_is_stop(toks[0]) or (len(toks) == 1 and toks[0] in GAZ_SINGLE):
            continue
        cands.append(Mention(m.start(1), m.end(1), name, "person", 3, 0.93, clean_person(name), {"titled": True}))

    # Capitalised phrases -> org / location / person
    toks = [(m.start(), m.end(), m.group(0).rstrip()) for m in TOKEN_RE.finditer(text)]
    groups: List[List[Tuple[int, int, str]]] = []
    for t in toks:
        if groups:
            prev = groups[-1][-1]
            gap = text[prev[1]:t[0]]
            if re.fullmatch(r"[ \t]+", gap) or (prev[2] in ORG_ABBR and re.fullmatch(r"\.?[ \t]+", gap)):
                groups[-1].append(t)
                continue
        groups.append([t])
    for g in groups:
        segs: List[List[Tuple[int, int, str]]] = [[]]
        for t in g:
            if _tok_is_stop(t[2]) and t[2].lower() not in LOC_SUFFIX:
                segs.append([])
            else:
                segs[-1].append(t)
        for sg in segs:
            if not sg:
                continue
            c = _classify_segment(sg)
            if c:
                typ, s, e, pr = c
                raw = text[s:e]
                val = clean_person(raw) if typ == "person" else re.sub(r"\s+", " ", raw).strip()
                cands.append(Mention(s, e, raw, typ, pr, 0.86 if typ == "person" else 0.88, val))

    for m in GAZ_RE.finditer(text):
        if m.group(1)[0].isupper():
            cands.append(Mention(m.start(1), m.end(1), m.group(1), "location", 4, 0.9, m.group(1)))
    for m in NEAR_RE.finditer(text):
        ws = [w for w in m.group(1).split()]
        while ws and _tok_is_stop(ws[0]):
            ws.pop(0)
        while ws and _tok_is_stop(ws[-1]):
            ws.pop()
        if ws and not any(w.lower() in ORG_SUFFIX for w in ws):
            val = " ".join(ws)
            s = m.start(1) + m.group(1).index(ws[0])
            cands.append(Mention(s, s + len(val), val, "location", 4, 0.8, val))
    for m in AT_RE.finditer(text):
        w = m.group(1)
        if not _tok_is_stop(w):
            cands.append(Mention(m.start(1), m.end(1), w, "location", 6, 0.72, w))
    for m in CUE_RE.finditer(text):
        w = m.group(1)
        if not _tok_is_stop(w) and w not in GAZ_SINGLE:
            cands.append(Mention(m.start(1), m.end(1), w, "person", 7, 0.7, w, {"partial": True}))

    cands.sort(key=lambda c: (c.prio, -(c.end - c.start), c.start))
    chosen: List[Mention] = []
    for c in cands:
        if any(not (c.end <= a.start or c.start >= a.end) for a in chosen):
            continue
        chosen.append(c)
    chosen.sort(key=lambda c: c.start)
    ents = [c for c in chosen if c.type != "date"]
    tags = [t for t in INCIDENT_TAGS if re.search(rf"\b{t}\b", text, re.I)]
    return ents, dates, tags


# --------------------------------------------------------------------------------------
# Optional spaCy boost
# --------------------------------------------------------------------------------------
_SPACY = None


def spacy_boost(text: str, existing: List[Mention]) -> List[Mention]:
    global _SPACY
    if _SPACY is False:
        return existing
    if _SPACY is None:
        try:
            import spacy  # type: ignore
            _SPACY = spacy.load("en_core_web_sm")
        except Exception:
            _SPACY = False
            return existing
    try:
        doc = _SPACY(text[:5000])
    except Exception:
        return existing
    out = list(existing)
    mapping = {"PERSON": "person", "ORG": "organization", "GPE": "location", "FAC": "location", "LOC": "location"}
    for ent in doc.ents:
        t = mapping.get(ent.label_)
        if not t:
            continue
        if any(not (ent.end_char <= a.start or ent.start_char >= a.end) for a in out):
            continue
        val = clean_person(ent.text) if t == "person" else ent.text.strip()
        if t == "person" and len(val.split()) < 2:
            continue
        out.append(Mention(ent.start_char, ent.end_char, ent.text, t, 6, 0.8, val, {"spacy": True}))
    out.sort(key=lambda c: c.start)
    return out


# --------------------------------------------------------------------------------------
# Relationship lexicon
# --------------------------------------------------------------------------------------
COMM = {"person", "phone", "organization"}
PARTY = {"person", "organization", "account"}
AGENT = {"person", "organization", "vehicle", "phone"}


@dataclass
class Verb:
    key: str
    rx: "re.Pattern[str]"
    conf: float
    reverse: bool
    allowed: Any   # callable(ta, tb) -> bool


def _v(key, pat, conf, reverse, allowed):
    return Verb(key, re.compile(pat, re.I), conf, reverse, allowed)


VERBS: List[Verb] = [
    _v("called", r"\b(?:received\s+(?:an?\s+)?(?:incoming\s+)?(?:phone\s+)?calls?\s+from|calls?\s+from|incoming\s+calls?\s+from|called\s+by|phoned\s+by|contacted\s+by)\b", .88, True, lambda a, b: a in COMM and b in COMM),
    _v("called", r"\b(?:called|phoned|dialled|dialed|rang|calling|spoke\s+(?:to|with)|talked\s+(?:to|with)|contacted|calls?\s+to|to\s+(?:call|phone|ring|contact|dial)|(?:made|placed)\s+(?:a\s+)?calls?\s+to)\b", .86, False, lambda a, b: a in COMM and b in COMM),
    _v("messaged", r"\b(?:texted|messaged|sms(?:ed)?|whatsapp(?:ed)?|chatted\s+with|emailed|mailed|to\s+(?:text|message|email))\b", .84, False, lambda a, b: (a in COMM or a == "email") and (b in COMM or b == "email")),
    _v("met", r"\b(?:met|meets?|meeting\s+with|spotted\s+with|seen\s+with|travell?ed\s+with|accompanied(?:\s+by)?|together\s+with|along\s+with|joined)\b", .88, False, lambda a, b: a in {"person", "organization"} and b in {"person", "organization"}),
    _v("paid", r"\b(?:paid|transferred|transfers?|sent|deposited|remitted|wired|credited|handed(?:\s+over)?|gave)\b", .86, False, lambda a, b: (a in PARTY and b in PARTY) or (a in PARTY and b == "transaction")),
    _v("received", r"\b(?:received|collected|got|withdrew|withdrawn)\b", .84, False, lambda a, b: (a in PARTY and b in PARTY) or (a in PARTY and b == "transaction")),
    _v("owns", r"\b(?:owns?|owned(?!\s+by)|purchased(?!\s+by)|bought(?!\s+by)|operates|runs)\b", .86, False, lambda a, b: a in {"person", "organization"} and b in {"vehicle", "account", "phone", "email", "organization"}),
    _v("owns", r"\b(?:owned\s+by|registered\s+(?:to|under|with|in\s+the\s+name\s+of)|belongs?\s+to|belonging\s+to|purchased\s+by|bought\s+by|registered\s+owner)\b", .88, True, lambda a, b: a in {"vehicle", "account", "phone", "email", "organization"} and b in {"person", "organization"}),
    _v("uses", r"\b(?:used|uses|using|carrying|carried|drove|drives?|driving|rode|rides?)\b", .84, False, lambda a, b: a == "person" and b in {"phone", "vehicle", "email", "account"}),
    _v("uses", r"\b(?:driven\s+by|used\s+by|operated\s+by|carried\s+by)\b", .86, True, lambda a, b: a in {"phone", "vehicle", "email", "account"} and b == "person"),
    _v("works_for", r"\b(?:works?\s+(?:for|at|with)|employed\s+(?:by|at|with)|employee\s+of|director\s+of|manager\s+(?:of|at)|partner\s+(?:of|in)|staff\s+of|driver\s+(?:of|for))\b", .84, False, lambda a, b: a == "person" and b == "organization"),
    _v("owns", r"\b(?:owner\s+of|proprietor\s+of|founder\s+of|runs|operates)\b", .86, False, lambda a, b: a == "person" and b == "organization"),
    _v("presence", r"\b(?:visited|went\s+to|travell?ed\s+to|reached|arrived(?:\s+(?:at|in))?|stayed(?:\s+(?:at|in))?|checked\s+in(?:to|at)?|lodged|spotted|seen|observed|sighted|detected|pinged|located|parked|stopped|entered|stationed|based)\b", .86, False, lambda a, b: a in AGENT and b in {"location", "organization"}),
    _v("presence", r"\b(?:near|outside|opposite|beside|at|in|from|inside|around)\b", .78, False, lambda a, b: a in AGENT and b == "location"),
    _v("presence", r"\b(?:near|outside|opposite|beside|inside)\b", .76, False, lambda a, b: a in {"vehicle", "person", "phone"} and b == "organization"),
    _v("associated_with", r"\b(?:associates?|associated\s+with|linked\s+(?:to|with)|connected\s+(?:to|with)|accomplices?|aides?|friends?|relatives?|brothers?|sisters?|cousins?|partners?|handlers?|colleagues?|co-?accused|acquaintances?|nephew|uncle|father|mother|son|daughter|wife|husband)\b", .82, False, lambda a, b: True),
    _v("interviewed", r"\b(?:questioned|interrogated|interviewed|arrested|detained|summoned|booked)\b", .84, False, lambda a, b: a == "person" and b == "person"),
    _v("involved_in", r"\b(?:involved\s+in|accused\s+in|booked\s+(?:in|under)|named\s+in|linked\s+to\s+(?:the\s+)?(?:case|fir))\b", .84, False, lambda a, b: b in {"event", "transaction"}),
    _v("flow", r"(?:->|→|=>|➔|>>)", .88, False, lambda a, b: True),
]

TYPE_RULES: List[Tuple[str, str, str, float]] = [
    ("person", "phone", "uses", .86), ("organization", "phone", "uses", .78),
    ("person", "vehicle", "uses", .74), ("organization", "vehicle", "owns", .78),
    ("vehicle", "location", "observed_at", .84), ("phone", "location", "located_at", .80),
    ("person", "location", "visited", .80), ("organization", "location", "based_at", .74),
    ("person", "organization", "associated_with", .68), ("person", "person", "associated_with", .62),
    ("organization", "organization", "associated_with", .66),
    ("person", "transaction", "involved_in", .70), ("organization", "transaction", "involved_in", .74),
    ("account", "transaction", "involved_in", .76), ("phone", "transaction", "involved_in", .62),
    ("person", "account", "owns", .84), ("organization", "account", "owns", .82),
    ("person", "email", "uses", .84), ("organization", "email", "uses", .78),
    ("phone", "phone", "called", .80), ("person", "event", "involved_in", .76),
    ("organization", "event", "involved_in", .72), ("vehicle", "event", "involved_in", .74), ("phone", "event", "involved_in", .66),
    ("transaction", "location", "occurred_at", .70), ("event", "location", "occurred_at", .78),
    ("phone", "vehicle", "associated_with", .66), ("account", "account", "transferred_to", .70),
    ("vehicle", "vehicle", "associated_with", .62),
]
SYMMETRIC = {"associated_with", "met", "mentioned_with", "seen_near"}


def type_rule(ta: str, tb: str) -> Tuple[str, float, bool]:
    for a, b, rel, conf in TYPE_RULES:
        if ta == a and tb == b:
            return rel, conf, False
        if ta == b and tb == a:
            return rel, conf, True
    return "mentioned_with", 0.55, False


def _specialize(key: str, ta: str, tb: str) -> Tuple[str, bool]:
    """Map a lexicon key onto a concrete relation name for a type pair. Returns (relation, reverse_extra)."""
    if key == "presence":
        if tb == "location":
            return {"person": "visited", "vehicle": "observed_at", "phone": "located_at", "organization": "based_at"}.get(ta, "located_at"), False
        return "seen_near", False
    if key == "paid":
        return ("transferred_to" if tb != "transaction" else "paid"), False
    if key == "received":
        return ("transferred_to", True) if tb != "transaction" else ("received", False)
    if key == "flow":
        if ta == "phone" and tb == "phone":
            return "called", False
        if ta in PARTY and tb in PARTY:
            return "transferred_to", False
        return "associated_with", False
    return key, False


def detect_relation(ta: str, tb: str, between: str, skip: Tuple[str, ...] = ()) -> Tuple[str, float, bool, bool]:
    """Return (relation, confidence, reverse, verb_found) for ordered pair (a,b) with the text between."""
    best = None
    for v in VERBS:
        if v.key in skip:
            continue
        for m in v.rx.finditer(between):
            if v.allowed(ta, tb) if not v.reverse else v.allowed(ta, tb):
                if best is None or m.start() >= best[0]:
                    best = (m.start(), v)
    if best:
        v = best[1]
        rel, extra = _specialize(v.key, ta, tb)
        return rel, v.conf, (v.reverse != extra), True
    rel, conf, rev = type_rule(ta, tb)
    return rel, conf, rev, False


# --------------------------------------------------------------------------------------
# Document parsing
# --------------------------------------------------------------------------------------
_ABBR = re.compile(r"\b(Mr|Mrs|Ms|Dr|Prof|Sr|Jr|No|Rs|Pvt|Ltd|Inc|Co|Corp|St|vs|Insp|Sri|Smt|Shri|approx|Nos|Dept|etc)\.", re.I)
_INITIAL = re.compile(r"\b([A-Z])\.(?=\s?[A-Z])")


def split_sentences(block: str) -> List[str]:
    t = _ABBR.sub(lambda m: m.group(1) + "\u0001", block)
    t = _INITIAL.sub(lambda m: m.group(1) + "\u0001", t)
    t = re.sub(r"(a)\.(k)\.(a)\.?", "a\u0001k\u0001a", t, flags=re.I)
    t = re.sub(r"(?<=\d)\.(?=\d)", "\u0002", t)
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(\[])|;\s+", t)
    return [p.replace("\u0001", ".").replace("\u0002", ".").strip() for p in parts if p and p.strip()]


_HEADER_DATE = re.compile(r"^\s*(?:date|dated|date\s+of\s+incident|incident\s+date|timestamp|time)\s*[:\-]\s*(.+)$", re.I)


def _parse_text(name: str, text: str, default_ts: Optional[str], max_units: int) -> ParsedDoc:
    units: List[Unit] = []
    cur = default_ts
    warnings: List[str] = []
    n = 0
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        s = line.strip()
        if not s:
            continue
        hd = _HEADER_DATE.match(s)
        if hd:
            d = parse_date_value(hd.group(1))
            if d:
                cur = d
                continue
        for sent in split_sentences(s):
            if len(sent) < 4:
                continue
            ds = find_dates(sent)
            ts = ds[0][2] if ds else cur
            if ds:
                cur = ds[0][2]
            n += 1
            units.append(Unit(sent, ts, f"line {n}", None, n))
            if n >= max_units:
                warnings.append(f"Stopped after {max_units} statements (limit).")
                return ParsedDoc("text", units, warnings)
    return ParsedDoc("text", units, warnings)


HDR = {
    "vehicle": {"vehicle", "plate", "registration", "reg", "rc", "licence", "license"},
    "phone": {"phone", "mobile", "msisdn", "cell", "cdr", "tel", "telephone", "number", "no", "contact", "imsi"},
    "account": {"account", "acct", "ac", "iban", "acc"},
    "email": {"email", "mail", "e-mail"},
    "organization": {"org", "organisation", "organization", "company", "firm", "business", "employer", "entity", "merchant", "vendor", "agency"},
    "location": {"location", "place", "city", "area", "address", "site", "tower", "region", "town", "village", "locality", "venue", "state", "district", "destination_city", "origin_city", "lat", "geo"},
    "amount": {"amount", "value", "amt", "rs", "inr", "sum", "price", "money", "credit", "debit", "rupees"},
    "date": {"date", "time", "timestamp", "datetime", "dt", "when", "day"},
    "event": {"fir", "incident", "crime", "offence", "offense", "event"},
    "text": {"description", "remarks", "notes", "note", "details", "detail", "narrative", "statement", "comment", "comments", "summary", "text", "message", "purpose", "reason", "type", "mode", "category", "nature", "narration", "particulars"},
    "person": {"name", "person", "suspect", "accused", "victim", "witness", "owner", "holder", "customer", "employee", "individual", "party", "caller", "receiver", "sender", "recipient", "payer", "payee", "beneficiary", "complainant", "contact_name", "subscriber"},
}
SRC_HINT = {"caller", "from", "sender", "source", "payer", "originator", "calling", "a_party", "src", "origin", "remitter", "debtor", "debit", "a"}
DST_HINT = {"receiver", "to", "recipient", "payee", "beneficiary", "called", "destination", "b_party", "dst", "target", "creditor", "credit_to", "b"}


def _hdr_tokens(h: str) -> List[str]:
    h = re.sub(r"([a-z])([A-Z])", r"\1_\2", h)
    return [t for t in re.split(r"[^A-Za-z0-9]+", h.lower()) if t]


def classify_header(h: str) -> Tuple[Optional[str], Optional[str]]:
    toks = _hdr_tokens(h)
    role = "src" if set(toks) & SRC_HINT else ("dst" if set(toks) & DST_HINT else None)
    typ = None
    for t in ("vehicle", "email", "account", "organization", "event", "amount", "date", "location", "phone", "person", "text"):
        if set(toks) & HDR[t]:
            typ = t
            break
    # "caller" / "to" alone => infer by value later
    if typ is None and role:
        typ = "person"
    return typ, role


def _sniff_delim(sample: str) -> str:
    first = sample.split("\n", 1)[0]
    counts = {d: first.count(d) for d in [",", ";", "\t", "|"]}
    d = max(counts, key=lambda k: counts[k])
    return d if counts[d] > 0 else ","


def _parse_csv(name: str, text: str, default_ts: Optional[str], max_units: int) -> ParsedDoc:
    warnings: List[str] = []
    delim = _sniff_delim(text)
    rows = list(csv.reader(io.StringIO(text), delimiter=delim))
    rows = [r for r in rows if any(c.strip() for c in r)]
    if len(rows) < 1:
        return ParsedDoc("csv", [], ["The CSV file is empty."])
    first = rows[0]

    def looks_data(c: str) -> bool:
        c = c.strip()
        return bool(c) and (bool(PHONE_RE.fullmatch(c)) or bool(find_dates(c)) or bool(re.fullmatch(r"[\d.,₹]+", c)) or bool(VEHICLE_RE.fullmatch(c)))

    has_header = len(rows) > 1 and not any(looks_data(c) for c in first)
    cols = [c.strip() or f"col{i+1}" for i, c in enumerate(first)] if has_header else [f"col{i+1}" for i in range(len(first))]
    body = rows[1:] if has_header else rows
    units: List[Unit] = []
    for i, r in enumerate(body, start=1):
        if i > max_units:
            warnings.append(f"Stopped after {max_units} rows (limit).")
            break
        fields = {cols[j] if j < len(cols) else f"col{j+1}": c.strip() for j, c in enumerate(r) if c.strip()}
        if not fields:
            continue
        txt = ", ".join(f"{k}: {v}" for k, v in fields.items())
        units.append(Unit(txt, None, f"row {i}", fields, i))
    return ParsedDoc("csv", units, warnings, cols)


def _flatten(obj: Any, prefix: str = "") -> Dict[str, str]:
    out: Dict[str, str] = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.update(_flatten(v, f"{prefix}{k}." if prefix else f"{k}."))
    elif isinstance(obj, list):
        if all(not isinstance(x, (dict, list)) for x in obj):
            out[prefix.rstrip(".")] = ", ".join(str(x) for x in obj)
        else:
            for i, v in enumerate(obj):
                out.update(_flatten(v, f"{prefix}{i}."))
    elif obj is not None:
        out[prefix.rstrip(".")] = str(obj)
    return out


def _parse_json(name: str, text: str, default_ts: Optional[str], max_units: int) -> ParsedDoc:
    try:
        data = json.loads(text)
    except Exception:
        try:  # JSON lines
            data = [json.loads(l) for l in text.splitlines() if l.strip()]
        except Exception:
            doc = _parse_text(name, text, default_ts, max_units)
            doc.warnings.append("File was not valid JSON — processed as plain text.")
            return doc
    records: List[Any]
    if isinstance(data, dict):
        lists = [(k, v) for k, v in data.items() if isinstance(v, list) and v]
        records = max(lists, key=lambda kv: len(kv[1]))[1] if lists else [data]
    elif isinstance(data, list):
        records = data
    else:
        records = [data]
    units: List[Unit] = []
    warnings: List[str] = []
    for i, rec in enumerate(records, start=1):
        if i > max_units:
            warnings.append(f"Stopped after {max_units} records (limit).")
            break
        if isinstance(rec, str):
            units.append(Unit(rec, None, f"record {i}", None, i))
            continue
        fields = {k: v for k, v in _flatten(rec).items() if v.strip()}
        if not fields:
            continue
        units.append(Unit(", ".join(f"{k}: {v}" for k, v in fields.items()), None, f"record {i}", fields, i))
    cols = sorted({k for u in units if u.fields for k in u.fields})
    return ParsedDoc("json", units, warnings, cols)


def parse_document(name: str, raw: Any, default_ts: Optional[str] = None, max_units: int = 20000) -> ParsedDoc:
    text = raw.decode("utf-8", errors="ignore") if isinstance(raw, (bytes, bytearray)) else str(raw)
    text = text.lstrip("\ufeff")
    low = (name or "").lower()
    if not default_ts:
        ds = find_dates(name or "")
        default_ts = ds[0][2] if ds else None
    stripped = text.lstrip()
    if low.endswith(".json") or low.endswith(".jsonl") or (stripped[:1] in "[{" and low.endswith((".txt", ".log", "")) and stripped[:1] != ""):
        if low.endswith(".json") or low.endswith(".jsonl") or _looks_json(stripped):
            return _parse_json(name, text, default_ts, max_units)
    if low.endswith((".csv", ".tsv")):
        return _parse_csv(name, text, default_ts, max_units)
    return _parse_text(name, text, default_ts, max_units)


def _looks_json(s: str) -> bool:
    try:
        json.loads(s)
        return True
    except Exception:
        return False


# --------------------------------------------------------------------------------------
# Structured-row mention extraction (CSV / JSON)
# --------------------------------------------------------------------------------------
def row_mentions(fields: Dict[str, str], default_ts: Optional[str]) -> Tuple[List[Mention], Optional[str], str, List[str], Dict[str, Any]]:
    """Return (mentions, timestamp, free_text_for_verbs, tags, attrs)."""
    mentions: List[Mention] = []
    ts = None
    date_part = None
    time_part = None
    texts: List[str] = []
    attrs: Dict[str, Any] = {}
    tags: List[str] = []
    pos = 0
    for col, val in fields.items():
        typ, role = classify_header(col)
        v = val.strip()
        if not v:
            continue
        toks = set(_hdr_tokens(col))
        # value-based type detection beats ambiguous headers
        if typ in (None, "phone", "person", "text") and PHONE_RE.fullmatch(v):
            typ = "phone"
        if typ == "date":
            d = parse_date_value(v)
            if d:
                if "time" in toks and "date" not in toks and "datetime" not in toks and "timestamp" not in toks and not re.search(r"\d{4}", v):
                    tm = re.search(r"(\d{1,2}):(\d{2})", v)
                    if tm:
                        time_part = f"{int(tm.group(1)):02d}:{tm.group(2)}"
                else:
                    date_part = date_part or d
            else:
                tm = re.search(r"^(\d{1,2}):(\d{2})", v)
                if tm:
                    time_part = f"{int(tm.group(1)):02d}:{tm.group(2)}"
            continue
        if typ == "amount":
            amt = parse_amount(v)
            if amt:
                mentions.append(Mention(pos, pos + len(v), v, "transaction", 1, 0.93, str(amt), {"amount": amt, "role": role, "col": col}))
                pos += len(v) + 2
            continue
        if typ in ("phone", "vehicle", "email", "account", "organization", "location", "event", "person"):
            val_clean = v
            if typ == "phone":
                m = PHONE_RE.search(v)
                if not m:
                    texts.append(v)
                    continue
                val_clean = m.group(0)
            elif typ in ("person", "location", "organization"):
                if val_clean.islower() or val_clean.isupper():
                    val_clean = val_clean.title()
                if typ == "person":
                    ws = val_clean.split()
                    if len(ws) >= 2 and any(w.lower().strip(".") in ORG_SUFFIX for w in ws):
                        typ = "organization"
                    elif val_clean in GAZ_SINGLE or val_clean in GAZ_MULTI:
                        typ = "location"
                if typ == "person" and (PHONE_RE.search(v) or MONEY_RE.search(v) or len(v.split()) > 5):
                    # not really a name, process as free text below
                    typ = None
            elif typ == "vehicle":
                m = VEHICLE_RE.search(v.upper())
                val_clean = m.group(0) if m else v.upper()
            elif typ == "event":
                val_clean = "FIR " + v.upper() if not v.upper().startswith("FIR") else v.upper()
            elif typ == "account":
                val_clean = re.sub(r"\D", "", v) or v
            elif typ == "email":
                val_clean = v.lower()
            if typ:
                mentions.append(Mention(pos, pos + len(v), v, typ, 1, 0.94, val_clean, {"role": role, "col": col}))
                pos += len(v) + 2
                continue
        if typ == "text" or typ is None:
            if typ == "text" and len(v) < 40 and not re.search(r"[A-Z][a-z]+\s+[A-Z][a-z]+|\d{6}", v):
                texts.append(v)           # short categorical like "call", "sms", "UPI"
                attrs[col] = v
                continue
            sub, _ds, tg = extract_mentions(v)
            tags.extend(tg)
            for s in sub:
                s.meta["role"] = None
                s.meta["col"] = col
                s.start += pos
                s.end += pos
                mentions.append(s)
            pos += len(v) + 2
            texts.append(v)
            if col.lower() in {"duration", "duration_sec", "seconds", "mode", "type", "channel", "status", "purpose"}:
                attrs[col] = v
    if date_part:
        ts = date_part + (f"T{time_part}" if time_part else "")
    if not ts:
        for val in fields.values():
            ds = find_dates(val)
            if ds:
                ts = ds[0][2]
                break
    ts = ts or default_ts
    for k in ("duration", "duration_sec", "seconds", "mode", "type", "channel", "purpose", "status", "remarks"):
        for col, val in fields.items():
            if col.lower() == k and k not in attrs:
                attrs[k] = val
    return mentions, ts, " ".join(texts), tags, attrs
