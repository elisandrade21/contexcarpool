#!/usr/bin/env python3
"""Ranking stability when the DATA of the same offers change (not the weights).
For whole markets and for 1,000 result pages of 100 offers, perturb the
listing attributes and compare the ranking with the unperturbed one:
  price noise    : price/km x lognormal(0, sigma), sigma = 5%, 10%, 20%
  booking flips  : 5% / 10% of offers switch automatic <-> manual
  seat changes   : 10% of offers gain or lose one seat (kept in [1,4])
  combined       : 10% price noise + 5% booking flips + 10% seat changes
Metric: Kendall tau_b and top-10 overlap vs the unperturbed ranking (same
thresholds as RQ2: mean tau >= 0.7 and mean top-k overlap >= 80%).
"""
import json, os
import numpy as np, pandas as pd
from scipy.stats import kendalltau

HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "out")
FC = {1: 2.5, 2: 5.0, 3: 7.5, 4: 10.0}
L = pd.read_csv(os.path.join(OUT, "listings.csv"))
rng = np.random.default_rng(20260612)


def score(seats, ppk, auto):
    fk = (1.0 - pd.Series(ppk).rank(pct=True).values) * 10.0
    return 0.4 * np.vectorize(FC.get)(seats) + 0.4 * fk + 0.2 * np.where(auto == 1, 10.0, 2.5)


def perturb(df, kind):
    seats, ppk, auto = df.seats_available.values.copy(), df.price_per_km.values.copy(), df.booking_auto.values.copy()
    n = len(df)
    if kind.startswith("price"):
        ppk = ppk * rng.lognormal(0, float(kind.split("_")[1]) / 100, n)
    elif kind.startswith("booking"):
        f = rng.random(n) < float(kind.split("_")[1]) / 100; auto[f] = 1 - auto[f]
    elif kind == "seats_10":
        f = rng.random(n) < 0.10; seats[f] = np.clip(seats[f] + rng.choice([-1, 1], f.sum()), 1, 4)
    elif kind == "combined":
        ppk = ppk * rng.lognormal(0, 0.10, n)
        f = rng.random(n) < 0.05; auto[f] = 1 - auto[f]
        g = rng.random(n) < 0.10; seats[g] = np.clip(seats[g] + rng.choice([-1, 1], g.sum()), 1, 4)
    return score(seats, ppk, auto)


def compare(df, kind, k=10):
    s0 = score(df.seats_available.values, df.price_per_km.values, df.booking_auto.values)
    s1 = perturb(df, kind)
    top0, top1 = set(np.argsort(-s0, kind="stable")[:k]), set(np.argsort(-s1, kind="stable")[:k])
    return kendalltau(s0, s1).statistic, len(top0 & top1) / k


KINDS = ["price_5", "price_10", "price_20", "booking_5", "booking_10", "seats_10", "combined"]
res = {}
for kind in KINDS:
    mk = [compare(L[L.country == c], kind) for c in L.country.unique() for _ in range(20)]
    pg = []
    for _ in range(1000):
        m = L[L.country == rng.choice(L.country.unique())]
        pg.append(compare(m.iloc[rng.choice(len(m), 100, replace=False)], kind))
    mk, pg = np.array(mk), np.array(pg)
    res[kind] = dict(markets_tau=round(float(mk[:, 0].mean()), 3), markets_top10=round(float(mk[:, 1].mean()), 3),
                     pages100_tau=round(float(pg[:, 0].mean()), 3), pages100_top10=round(float(pg[:, 1].mean()), 3),
                     pages100_top10_p5=round(float(np.percentile(pg[:, 1], 5)), 2))
json.dump(res, open(os.path.join(OUT, "data_stability.json"), "w"), indent=2)
print(json.dumps(res, indent=1))
