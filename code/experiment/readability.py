"""Readability of the rationales (no human participants): Flesch Reading Ease and Flesch-Kincaid grade
(textstat 0.7.10) for the 600 rule-derived rationales and the 600 texts of each language model.
Writes out/readability.json."""
import json, os, statistics as st, textstat
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "out")
F = json.load(open(os.path.join(OUT, "llm_facts.json")))
def model(name):
    G = json.load(open(os.path.join(OUT, name)))
    return [x["text"] for x in G["items"] if x["kind"] == "llm" and x["text"]]
sets = {"rule": [f["rationale"] for f in F], "haiku": model("llm_generated.json"), "sonnet": model("llm_generated_sonnet.json")}
def q(v):
    v = sorted(v); return [round(st.median(v), 1), round(v[len(v) // 4], 1), round(v[3 * len(v) // 4], 1)]
res = {}
for k, T in sets.items():
    res[k] = dict(n=len(T), flesch_reading_ease_median_q1_q3=q([textstat.flesch_reading_ease(t) for t in T]),
                  fk_grade_median_q1_q3=q([textstat.flesch_kincaid_grade(t) for t in T]),
                  words_median_q1_q3=q([textstat.lexicon_count(t) for t in T]))
json.dump(dict(tool="textstat 0.7.10", note="Flesch Reading Ease: higher is easier (60-70 plain English); FK grade = US school grade",
               results=res), open(os.path.join(OUT, "readability.json"), "w"), indent=1)
for k, v in res.items(): print(k, v)
print("example:", sets["rule"][0])
