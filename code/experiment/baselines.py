#!/usr/bin/env python3
"""Simple baselines: how close is the ranking by S to ranking by price alone or by price per km alone?
Mean Kendall tau_b and top-10 overlap per market (whole markets of 1,000 offers)."""
import json, os
import numpy as np, pandas as pd
from scipy.stats import kendalltau
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "out")
L = pd.read_csv(os.path.join(OUT, "listings.csv")); res = {}
for name, key in (("price", "price"), ("price_per_km", "price_per_km")):
    taus, tops = [], []
    for c, sub in L.groupby("country"):
        taus.append(kendalltau(sub.S, -sub[key]).statistic)
        tops.append(len(set(sub.nlargest(10, "S").index) & set(sub.nsmallest(10, key).index)) / 10)
    res[name] = dict(mean_tau=round(float(np.mean(taus)), 3), mean_top10_overlap=round(float(np.mean(tops)), 3))
json.dump(res, open(os.path.join(OUT, "baselines.json"), "w"), indent=2); print(res)
