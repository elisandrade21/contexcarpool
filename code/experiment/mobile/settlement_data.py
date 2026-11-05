#!/usr/bin/env python3
"""Adds simulated trip records to the check searches: for 30% of the offers the passenger gets off early
(after 50-100% of the trip); each phone records the distance with 1% noise, and in 5% of those trips the
driver's phone records the full trip (a dispute). Writes the reference fares of rules R14-R15."""
import json, os
import numpy as np
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "out")
rng = np.random.default_rng(20261107)
path = os.path.join(OUT, "mobile_searches.json"); d = json.load(open(path))
n = fares = disputes = 0; saved = []
for s in d["check"]:
    for o in s["offers"]:
        o.pop("trip", None)
        if rng.random() >= 0.30: continue
        D = float(o["distance"]); true = D * float(rng.uniform(0.5, 1.0))
        kp = round(true * (1 + float(rng.normal(0, 0.01))), 3)
        kd = round(D if rng.random() < 0.05 else true * (1 + float(rng.normal(0, 0.01))), 3)
        ref = {"kp": kp, "kd": kd}
        if abs(kp - kd) <= 0.05 * D:
            k = (kp + kd) / 2.0
            ref["fare"] = round(float(o["price_per_km"]) * min(k, D) * 100) / 100
            fares += 1; saved.append(1 - ref["fare"] / (float(o["price_per_km"]) * D))
        else:
            ref["disputed"] = True; disputes += 1
        o["trip"] = ref; n += 1
json.dump(d, open(path, "w"))
res = dict(trips=n, settled=fares, disputed=disputes, mean_saving_percent=round(100 * float(np.mean(saved)), 1))
json.dump(res, open(os.path.join(OUT, "settlement_coverage.json"), "w"), indent=2); print(res)
