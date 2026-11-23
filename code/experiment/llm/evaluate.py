"""M1, M4, M6 on the model outputs; merges M2/M3 controls. Writes out/llm_result.json."""
import json, os, math, subprocess, collections
from checker import check
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "..", "out")
F = json.load(open(os.path.join(OUT, "llm_facts.json"))); G = json.load(open(os.path.join(OUT, "llm_generated.json")))
C = json.load(open(os.path.join(OUT, "llm_controls.json")))
items = [x for x in G["items"] if x["text"]]
py = [check(x["text"], F[x["i"]]) for x in items]
json.dump([dict(i=x["i"], text=x["text"], kind=x["kind"]) for x in items], open(os.path.join(OUT, "llm_texts_model.json"), "w"))
json.dump([ok for ok, _ in py], open(os.path.join(OUT, "llm_py_model.json"), "w"))
js = json.loads(subprocess.run(["node", "agree.mjs", os.path.join(OUT, "llm_texts_model.json"), os.path.join(OUT, "llm_py_model.json")],
                               cwd=HERE, capture_output=True, text=True).stdout)
def wilson(k, n, z=1.96):
    p = k / n; d = 1 + z * z / n; c = p + z * z / (2 * n); h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return [round((c - h) / d, 4), round((c + h) / d, 4)]
m1 = [(x, r) for x, r in zip(items, py) if x["kind"] == "llm"]; m4 = [(x, r) for x, r in zip(items, py) if x["kind"] == "llm_subtle"]
k1 = sum(not r[0] for _, r in m1); k4 = sum(not r[0] for _, r in m4)
reasons = collections.Counter(w.split()[0] for _, r in m1 for w in r[1])
res = dict(model=G["model"], M1_texts=len(m1), M1_failed=k1, M1_failed_share=round(k1 / len(m1), 4), M1_ci95=wilson(k1, len(m1)),
           M1_reasons=dict(reasons), M2=f"{C['M2_rule_rationales_pass']}/{C['M2_total']} pass", M3=f"{C['M3_injected_fail']}/{C['M3_total']} fail",
           M4_texts=len(m4), M4_flagged=k4, M5_ms_per_100=js["ms_per_100_texts"], M6_agreement=f"{js['agree']}/{js['texts']}",
           examples_failed=[dict(text=x["text"], why=r[1]) for x, r in m1 if not r[0]][:4],
           examples_subtle_missed=[dict(text=x["text"], fact=F[x["i"]]["rationale"]) for x, r in m4 if r[0]][:4])
json.dump(res, open(os.path.join(OUT, "llm_result.json"), "w"), indent=1)
print(json.dumps(res, indent=1))
