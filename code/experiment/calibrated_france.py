#!/usr/bin/env python3
"""Scenario calibrated from PUBLISHED statistics of real BlaBlaCar listings (France).

  price per km : log-normal, median 0.0625 EUR/km, sigma 0.20 (within-route)
                 -> Farajallah, Hammond & Penard (2019), Table A1 (948,789 listings, 2013-14)
  distance     : log-normal, median 356.6 km, sigma 0.474
                 -> Lambin & Palikot (2026), Table 1 (557,031 listings, 2017-19; mean 398.9, sd 200.0)
  auto booking : 42% of listings  -> Lambin & Palikot (2026), Table 1
  booking-price: automatic booking about 1.8% cheaper (log coefficient -0.018)
                 -> Blayac, Bougette & Duberga (2026), Table 11 (same sign in Farajallah et al. 2019)
  seats offered: NOT published -> same assumption as the base generator (France)
Runs RQ1 (redundancy, ablation, single-criterion rho) and RQ2 (weights, data changes).
"""
import json, os
from itertools import product
import numpy as np, pandas as pd
from scipy.stats import kendalltau, spearmanr
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.model_selection import cross_val_predict, KFold

HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "out")
rng = np.random.default_rng(20260614)
FC = {1: 2.5, 2: 5.0, 3: 7.5, 4: 10.0}
N = 5000
dist = np.clip(rng.lognormal(np.log(356.6), 0.474, N), 30, 1500)
auto = (rng.random(N) < 0.42).astype(int)
ppk = rng.lognormal(np.log(0.0625), 0.20, N) * np.exp(-0.018 * auto)
seats = rng.choice([1, 2, 3, 4], N, p=[0.22, 0.36, 0.32, 0.10])
L = pd.DataFrame(dict(seats_available=seats, booking_auto=auto, price_per_km=ppk, distance_km=dist))


def scored(d, w=(0.4, 0.4, 0.2)):
    d = d.copy()
    d["f_C"] = d.seats_available.map(FC)
    d["f_K"] = (1.0 - d.price_per_km.rank(pct=True)) * 10.0
    d["f_B"] = np.where(d.booking_auto == 1, 10.0, 2.5)
    d["S"] = w[0] * d.f_C + w[1] * d.f_K + w[2] * d.f_B
    return d


def r2(y, X):
    m = GradientBoostingRegressor(n_estimators=150, max_depth=3, random_state=0)
    pred = cross_val_predict(m, X, y, cv=KFold(5, shuffle=True, random_state=0))
    return max(0.0, 1 - ((y - pred) ** 2).mean() / y.var())


C = ["f_C", "f_K", "f_B"]; Wd = dict(zip(C, (0.4, 0.4, 0.2)))
mk = scored(L.iloc[:1000])                                   # one 'market' search of 1,000
res = {"calibration": "Farajallah et al. 2019; Lambin & Palikot 2026; Blayac et al. 2026 (seats: assumption)",
       "check": dict(ppk_median=round(float(np.median(L.price_per_km)), 4), dist_mean=round(float(L.distance_km.mean()), 1),
                     auto_rate=round(float(L.booking_auto.mean()), 3))}
rq1 = {}
for c in C:
    o = [x for x in C if x != c]
    Sm = sum(Wd[x] * mk[x] for x in o) / sum(Wd[x] for x in o)
    rq1[c] = dict(rho_single=round(float(spearmanr(mk.S, mk[c]).statistic), 3),
                  r2_from_others=round(float(r2(mk[c].values, mk[o].values)), 3),
                  tau_without=round(float(kendalltau(mk.S, Sm).statistic), 3))
res["rq1_market"] = rq1
# RQ2 weights (+-0.1) on the market and on 500 pages of 100
grid = [-0.1, 0.0, 0.1]; WG = []
for a, b, c in product(grid, repeat=3):
    w = np.array([0.4 + a, 0.4 + b, 0.2 + c])
    if (w <= 0).any(): continue
    w = w / w.sum()
    if abs(w[0] - 0.4) < 1e-9 and abs(w[1] - 0.4) < 1e-9: continue
    WG.append(w)
def wstab(d, k=10):
    base = d.S.values; topb = set(np.argsort(-base, kind="stable")[:k]); t, o = [], []
    for w in WG:
        s2 = w[0] * d.f_C.values + w[1] * d.f_K.values + w[2] * d.f_B.values
        t.append(kendalltau(base, s2).statistic); o.append(len(topb & set(np.argsort(-s2, kind="stable")[:k])) / k)
    return np.mean(t), np.mean(o)
tm, om = wstab(mk)
pg = [wstab(scored(L.iloc[rng.choice(N, 100, replace=False)])) for _ in range(500)]
res["rq2_weights"] = dict(market_tau=round(float(tm), 3), market_top10=round(float(om), 3),
                          pages100_tau=round(float(np.mean([p[0] for p in pg])), 3), pages100_top10=round(float(np.mean([p[1] for p in pg])), 3))
# RQ2 data changes (price noise) on pages of 100
def dstab(sigma, k=10):
    t, o = [], []
    for _ in range(500):
        d = L.iloc[rng.choice(N, 100, replace=False)].copy()
        s0 = scored(d).S.values
        d["price_per_km"] = d.price_per_km.values * rng.lognormal(0, sigma, 100)
        s1 = scored(d).S.values
        t.append(kendalltau(s0, s1).statistic)
        o.append(len(set(np.argsort(-s0, kind="stable")[:k]) & set(np.argsort(-s1, kind="stable")[:k])) / k)
    return round(float(np.mean(t)), 3), round(float(np.mean(o)), 3)
res["rq2_price_noise_pages100"] = {f"sigma_{s}": dstab(s / 100) for s in (5, 10, 20)}
json.dump(res, open(os.path.join(OUT, "calibrated_france.json"), "w"), indent=2)
print(json.dumps(res, indent=1))
