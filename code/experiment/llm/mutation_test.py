"""Script-planted errors (not written by a language model): each accepted text (rule-derived rationales and the
model texts the frozen checker accepted) gets one mutation that makes it false, and the checker must reject it.
Categories the checker parses: percentile, position, seats, comfort level, booking mode, rule id, price extreme.
Out of scope by design (expected misses): seat counts in words, causal claims. No API call; deterministic."""
import json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from checker import check
OUT = os.path.join(HERE, "..", "out")
facts = json.load(open(os.path.join(OUT, "llm_facts.json")))
WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight"]
LV = ["very comfortable", "comfortable", "bearable", "uncomfortable"]

def sub1(pat, repl, t):
    m = re.search(pat, t, re.I)
    return None if not m else t[:m.start(1)] + repl(m.group(1)) + t[m.end(1):]

def mutations(t, f):
    p, n, s = f["percentile"], f["position"], f["seats"]
    other = lambda v, k: str(((int(v) + k - 1) % 99) + 1)
    yield "percentile", sub1(r"(?:percentile\s+(?:of\s+)?|(?<!\d))(\d+)(?=(?:st|nd|rd|th)?\s+(?:price\s+)?percentile)|percentile\s+(\d+)", lambda v: other(v, 13), t) \
        if False else (sub1(r"percentile\s+(\d+)", lambda v: other(v, 13), t) or sub1(r"(\d+)(?:st|nd|rd|th)?\s+(?:price\s+)?percentile", lambda v: other(v, 13), t))
    yield "position", sub1(r"(?:ranks?|ranked|position|place)\s*#?(\d+)(?![\d.])", lambda v: str(int(v) + 3), t) or sub1(r"\b(\d+)(?:st|nd|rd|th)\s+(?:of|out of|place)", lambda v: str(int(v) + 3), t)
    yield "seats", sub1(r"(\d+)\s+(?:free\s+|available\s+)?seats?", lambda v: str(int(v) % 4 + 1 if int(v) % 4 + 1 != int(v) else int(v) + 1), t)
    lv = next((x for x in LV if re.search(r"\b" + x + r"\b", t, re.I)), None)
    if lv:
        new = LV[(LV.index(lv) + 2) % 4]
        yield "level", re.sub(r"\b" + lv + r"\b", new, t, count=1, flags=re.I)
    if f["booking"] == "auto":
        yield "booking", (re.sub(r"\bautomatic\b", "manual", t, count=1, flags=re.I) if re.search(r"\bautomatic\b", t, re.I)
                          else re.sub(r"\binstant(ly)?\b", "only after the driver's approval", t, count=1, flags=re.I) if re.search(r"\binstant", t, re.I) else None)
    else:
        yield "booking", (re.sub(r"\bmanual\b", "automatic", t, count=1, flags=re.I) if re.search(r"\bmanual\b", t, re.I)
                          else re.sub(r"\b(?:driver's |the driver )?approval\b", "instant booking", t, count=1, flags=re.I) if re.search(r"approval", t, re.I) else None)
    yield "rule", sub1(r"\bR(\d{1,2})\b", lambda v: str(int(v) % 8 + 1) if f"R{int(v) % 8 + 1}" not in (f["rule"], f["trade_rule"]) else str(int(v) % 8 + 2), t)
    yield "extreme", (t.rstrip(". ") + ". It is the cheapest offer in the search.") if p > 25 else (t.rstrip(". ") + ". It is the most expensive offer in the search.") if p < 75 else None
    yield "seats_in_words (out of scope)", sub1(r"(\d+)\s+(?:free\s+|available\s+)?seats?", lambda v: WORDS[(int(v) % 4) + 1 if (int(v) % 4) + 1 != int(v) else int(v) + 1], t)
    yield "causal (out of scope)", t.rstrip(". ") + ". It ranks here because the driver is highly rated."

def corpus(name):
    if name == "rule-derived":
        return [(f["rationale"], f) for f in facts]
    d = json.load(open(os.path.join(OUT, "llm_generated.json" if name == "haiku" else "llm_generated_sonnet.json")))
    return [(x["text"], facts[x["i"]]) for x in d["items"] if x["kind"] == "llm"]

res = {}
for name in ("rule-derived", "haiku", "sonnet"):
    base = [(t, f) for t, f in corpus(name) if check(t, f)[0]]
    cat = {}
    for t, f in base:
        for k, mt in mutations(t, f):
            if not mt or mt == t: continue
            c = cat.setdefault(k, [0, 0]); c[0] += 1; c[1] += (not check(mt, f)[0])
    res[name] = {"accepted_base_texts": len(base),
                 "by_category": {k: {"mutated": n, "rejected": r, "rate": round(r / n, 4)} for k, (n, r) in cat.items()}}
    inscope = [v for k, v in cat.items() if "out of scope" not in k]
    res[name]["in_scope_total"] = {"mutated": sum(n for n, _ in inscope), "rejected": sum(r for _, r in inscope)}
json.dump(res, open(os.path.join(OUT, "llm_mutation_test.json"), "w"), indent=2)
print(json.dumps(res, indent=1))
