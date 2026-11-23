"""Python checker (independent of checker.mjs): does a rationale text state only facts the phone recomputed?
Rules fixed in PROTOCOL_2026-11-23.md."""
import re
from decimal import Decimal, ROUND_HALF_UP

def rnd(x, d):
    return float(Decimal(repr(float(x))).quantize(Decimal(1).scaleb(-d), rounding=ROUND_HALF_UP))

ROLES = [  # (pattern, fact) numbers bound to a role must equal that fact; order matters (first match blanks the number)
    (r"\b(\d+(?:\.\d+)?)(?:st|nd|rd|th)?\s+(?:price\s+)?percentile", "percentile"),
    (r"percentile(?: rank)?(?: of)?\s+(\d+(?:\.\d+)?)", "percentile"),
    (r"\b\d+(?:st|nd|rd|th)\s+(?:of|out of)\s+(\d+)(?![\d.])", "offers_in_search"),
    (r"(?:ranked|ranks|rank|position|place|placed)\s*#?\d+\s+(?:of|out of)\s+(\d+)(?![\d.])", "offers_in_search"),
    (r"(?:of|out of)\s+(\d+)\s+(?:offers|options|results|trips|rides)", "offers_in_search"),
    (r"(\d+)\s+(?:offers|options|results)\b", "offers_in_search"),
    (r"(?:ranked|ranks|rank|position|place|placed)\s*(?:#|no\.?\s*)?(\d+)(?![\d.])", "position"),
    (r"\b(\d+)(?:st|nd|rd|th)\b", "position"),
    (r"(?:score|\bS)\s*(?:of|=|is|:)?\s*(\d+(?:\.\d+)?)", "S"),
    (r"(\d+)\s+(?:free\s+|available\s+|empty\s+|open\s+)?seats?", "seats"),
    (r"(\d+(?:\.\d+)?)\s*(?:€|eur|euros?|r\$|\$|brl|uah)?\s*(?:per|/)\s*km", "price_per_km"),
    (r"(?:€|r\$|\$)\s*(\d+(?:\.\d+)?)", "price_per_km"),
]

LEVELS = [("very comfortable", "VeryComfortable"), ("uncomfortable", "Uncomfortable"),
          ("comfortable", "Comfortable"), ("bearable", "Bearable")]
WEIGHTS = [0.4, 0.2, 40, 20]

def allowed_numbers(f):
    v = [f["position"], f["offers_in_search"], f["S"], f["fC"], f["fK"], f["fB"], f["percentile"],
         f["seats"], f["price_per_km"]] + WEIGHTS
    return v

def num_ok(tok, f):
    t = tok.replace(",", "")
    d = len(t.split(".")[1]) if "." in t else 0
    x = float(t)
    return any(rnd(a, d) == rnd(x, d) for a in allowed_numbers(f))

LEGEND = r"\(?\s*(?:where|with)?\s*(?:percentile\s+)?1\s*(?:=|is|means|being)\s*(?:the\s+)?cheapest\s*\)?"
STRIP = [r"trip_[A-Z]+-\d+", r"\bout of 10\b", r"\bnot\s+(?:among\s+)?(?:the\s+)?(?:cheapest|most expensive)\b"]

def check(text, f):
    text = re.sub(LEGEND, " ", text, flags=re.I)  # echo of the legend given in the prompt, not a claim
    for p in STRIP: text = re.sub(p, " ", text, flags=re.I)  # offer ids, the 0-10 scale, negated extremes
    low = text.lower()
    reasons = []
    rules = re.findall(r"\bR(\d{1,2})\b", text)
    ok_rules = {f["rule"], f["trade_rule"]} - {None}
    for r in rules:
        if "R" + r not in ok_rules: reasons.append("rule R" + r)
    body = re.sub(r"\bR\d{1,2}\b", " ", text)
    for pat, key in ROLES:
        for m in list(re.finditer(pat, body, re.I)):
            tok = m.group(1); d = len(tok.split(".")[1]) if "." in tok else 0
            facts = [f["S"], f["fC"], f["fK"], f["fB"]] if key == "S" else [f[key]]   # "score" may name a factor score
            if all(rnd(float(tok), d) != rnd(v, d) for v in facts): reasons.append(key + " " + tok)
            body = body[:m.start(1)] + " " * len(tok) + body[m.end(1):]
    for tok in re.findall(r"(?<![\w.])\d+(?:,\d{3})*(?:\.\d+)?", body):
        if not num_ok(tok, f): reasons.append("number " + tok)
    rest = low
    for phrase, lab in LEVELS:
        if re.search(r"\b" + phrase + r"\b", rest):
            if lab != f["level"]: reasons.append("level " + phrase)
            rest = re.sub(r"\b" + phrase + r"\b", " ", rest)
    auto = re.search(r"\b(automatic|instant|instantly)\b", low)
    manual = re.search(r"\b(manual|approval|approve)\b", low)
    if auto and f["booking"] != "auto": reasons.append("booking automatic")
    if manual and f["booking"] != "manual": reasons.append("booking manual")
    if re.search(r"\bcheapest\b", low) and f["percentile"] > 25: reasons.append("cheapest")
    if re.search(r"\b(most expensive|priciest)\b", low) and f["percentile"] < 75: reasons.append("most expensive")
    return (len(reasons) == 0), reasons
