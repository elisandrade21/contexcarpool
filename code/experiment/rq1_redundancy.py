#!/usr/bin/env python3
"""RQ1 revisited: does each criterion carry information the others do not?

Low correlation between S and each single criterion does NOT prove that
(counterexample below). We test two things per criterion i:
  (a) redundancy  - out-of-sample R^2 of f_i predicted from the other two
                    criteria by gradient boosting (5-fold cross-validation), so
                    that NON-LINEAR dependence (e.g. booking = f(comfort)) is
                    detected; 1 - R^2 = share of f_i the others cannot explain;
  (b) ablation    - Kendall tau_b between S and S_{-i}, the composite without
                    criterion i (weights renormalised): if tau >= 0.9 the
                    criterion barely changes the ranking.
RQ1 is refuted for criterion i if R^2 >= 0.9 (redundant) or tau(S, S_-i) >= 0.9
(negligible). Run after run_experiment.py.
"""
import json, os
import numpy as np, pandas as pd
from scipy.stats import kendalltau, spearmanr

HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "out")
W = {"f_C": 0.4, "f_K": 0.4, "f_B": 0.2}
FC = {1: 2.5, 2: 5.0, 3: 7.5, 4: 10.0}


def fk(ppk):
    return (1.0 - pd.Series(ppk).rank(pct=True).values) * 10.0


from sklearn.ensemble import GradientBoostingRegressor
from sklearn.model_selection import cross_val_predict, KFold


def r2(y, X):
    """Out-of-sample (5-fold) R^2 of a non-linear predictor of y from X."""
    if y.var() == 0:
        return 1.0
    m = GradientBoostingRegressor(n_estimators=150, max_depth=3, random_state=0)
    pred = cross_val_predict(m, X, y, cv=KFold(5, shuffle=True, random_state=0))
    return float(max(0.0, 1 - ((y - pred) ** 2).mean() / y.var()))


def analyse(df, with_r2=True):
    S = sum(W[c] * df[c] for c in W)
    out = {}
    for c in W:
        others = [o for o in W if o != c]
        Sm = sum(W[o] * df[o] for o in others) / sum(W[o] for o in others)
        out[c] = dict(rho_single=round(float(spearmanr(S, df[c]).statistic), 3),
                      r2_from_others=round(r2(df[c].values, df[others].values), 3) if with_r2 else None,
                      tau_without=round(float(kendalltau(S, Sm).statistic), 3))
    out["refuted"] = any((v["r2_from_others"] or 0) >= 0.9 or v["tau_without"] >= 0.9 for k, v in out.items() if k in W)
    out["old_test_refuted"] = any(v["rho_single"] >= 0.9 for k, v in out.items() if k in W)
    return out


L = pd.read_csv(os.path.join(OUT, "listings.csv"))
res = {"markets": {c: analyse(L[L.country == c]) for c in L.country.unique()}}

# Counterexample: booking fully determined by comfort (auto iff d >= 3)
rng = np.random.default_rng(7)
n = 1000
d = rng.choice([1, 2, 3, 4], n, p=[0.22, 0.36, 0.32, 0.10])
ce = pd.DataFrame(dict(f_C=[FC[x] for x in d], f_K=fk(rng.lognormal(np.log(0.07), 0.28, n)),
                       f_B=np.where(d >= 3, 10.0, 2.5)))
res["counterexample_booking_redundant"] = analyse(ce)

# Realistic pages: 1,000 pages of 20 offers per size
prng = np.random.default_rng(20260610)
pages = {}
for size in (20, 100):
    acc = {c: dict(r2=[], tau=[]) for c in W}
    for _ in range(1000):
        mk = L[L.country == prng.choice(L.country.unique())]
        sub = mk.iloc[prng.choice(len(mk), size, replace=False)].copy()
        sub["f_K"] = fk(sub.price_per_km.values)
        a = analyse(sub, with_r2=False)
        for c in W:
            acc[c]["tau"].append(a[c]["tau_without"])
    pages[str(size)] = {c: dict(tau_without_mean=round(float(np.nanmean(v["tau"])), 3),
                                share_tau_without_ge_0_9=round(float(np.mean(np.array(v["tau"]) >= 0.9)), 3))
                        for c, v in acc.items()}
res["pages"] = pages
json.dump(res, open(os.path.join(OUT, "rq1_redundancy.json"), "w"), indent=2)
print(json.dumps(res, indent=1))

# Correlated seats/price (Gaussian copula, France parameters), as in the paper
from scipy.stats import norm
cum = np.cumsum([0.22, 0.36, 0.32, 0.10])
crng = np.random.default_rng(20260611)
cop = {}
for rcor in (-0.9, -0.6, 0.6, 0.9):
    z = crng.multivariate_normal([0, 0], [[1, rcor], [rcor, 1]], size=1000)
    dd = np.clip(1 + np.searchsorted(cum, norm.cdf(z[:, 0]), side="right"), 1, 4)
    df = pd.DataFrame(dict(f_C=[FC[x] for x in dd], f_K=fk(np.exp(np.log(0.071) + 0.28 * z[:, 1])),
                           f_B=np.where(crng.random(1000) < 0.58, 10.0, 2.5)))
    a = analyse(df)
    cop[str(rcor)] = {c: (a[c]["r2_from_others"], a[c]["tau_without"]) for c in W} | {"refuted": a["refuted"]}
res["copula_r2_tau_without"] = cop
json.dump(res, open(os.path.join(OUT, "rq1_redundancy.json"), "w"), indent=2)
print("COPULA", json.dumps(cop))
