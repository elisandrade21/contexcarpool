"""M2 (rule-derived rationales must pass) and M3 (one scripted error each must fail). Writes out/llm_controls.json
and out/llm_texts_controls.json (texts for the JS checker)."""
import json, os, re, random
from checker import check
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "..", "out")
F = json.load(open(os.path.join(OUT, "llm_facts.json")))
SWAP = {"very comfortable": "bearable", "comfortable": "uncomfortable", "bearable": "very comfortable", "uncomfortable": "comfortable"}
rng = random.Random(20261123)

def inject(f, k):
    t = f["rationale"]; kind = ["percentile", "position", "level", "booking"][k % 4]
    if kind == "percentile":
        p = f["percentile"]; q = p + 7 if p <= 90 else p - 7
        return kind, t.replace(f"percentile {p} ", f"percentile {q} ")
    if kind == "position":
        q = f["position"] + 2
        return kind, t + f"; it is ranked {q} of {f['offers_in_search']}"
    if kind == "level":
        for a, b in [("inferred very comfortable", "inferred bearable"), ("inferred uncomfortable", "inferred comfortable"),
                     ("inferred comfortable", "inferred uncomfortable"), ("inferred bearable", "inferred very comfortable")]:
            if a in t: return kind, t.replace(a, b, 1)
    # booking flip
    if "booking is automatic" in t: return kind, t.replace("booking is automatic", "booking needs driver approval")
    return kind, t.replace("booking is manual", "booking is automatic")

m2 = [check(f["rationale"], f) for f in F]
inj = [inject(f, i) for i, f in enumerate(F)]
m3 = [check(t, f) for (k, t), f in zip(inj, F)]
res = dict(M2_rule_rationales_pass=sum(ok for ok, _ in m2), M2_total=len(F),
           M3_injected_fail=sum(not ok for ok, _ in m3), M3_total=len(F),
           M2_failures=[(F[i]["id"], r) for i, (ok, r) in enumerate(m2) if not ok][:5],
           M3_missed=[(F[i]["id"], inj[i][0]) for i, (ok, r) in enumerate(m3) if ok][:5])
json.dump(res, open(os.path.join(OUT, "llm_controls.json"), "w"), indent=1)
json.dump([dict(kind="rule", i=i, text=f["rationale"]) for i, f in enumerate(F)] +
          [dict(kind="injected_" + k, i=i, text=t) for i, (k, t) in enumerate(inj)],
          open(os.path.join(OUT, "llm_texts_controls.json"), "w"))
print(json.dumps(res, indent=1))
