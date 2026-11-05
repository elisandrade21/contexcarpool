#!/usr/bin/env python3
"""What recomputation cannot catch: a platform that changes the offer set of a search.
f_K is a percentile within the search, so hiding the k cheapest offers, or adding k overpriced
fake offers, lifts a chosen offer while the published scores stay exactly reproducible from
the published (manipulated) set. For 1,000 pages of 100 offers we pick a target at the middle of
the honest order (position 50) and count how many of the offers still shown it overtakes.
Writes out/omission_attack.json."""
import json, os
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "out")
FC = {1: 2.5, 2: 5.0, 3: 7.5, 4: 10.0}
L = pd.read_csv(os.path.join(OUT, "listings.csv"))
rng = np.random.default_rng(20261106)

def score(d, w=(0.4, 0.4, 0.2)):
    fK = (1.0 - d.price_per_km.rank(pct=True)) * 10.0
    return w[0] * d.seats_available.map(FC) + w[1] * fK + w[2] * np.where(d.booking_auto == 1, 10.0, 2.5)

def order(d):
    s = score(d); return list(d.assign(S=s).sort_values("S", ascending=False, kind="stable").trip_id)

res = {}
for attack in ("hide_cheapest", "add_expensive_fakes", "hide_just_cheaper", "add_fakes_just_above"):
    for k in (1, 5, 10):
        gains, top10 = [], 0
        for p in range(1000):
            m = L.country.unique()[p % L.country.nunique()]
            page = L[L.country == m].sample(100, random_state=int(rng.integers(1e9))).reset_index(drop=True)
            honest = order(page); target = honest[49]
            if attack == "hide_cheapest":
                others = page[page.trip_id != target].nsmallest(k, "price_per_km").trip_id
                shown = page[~page.trip_id.isin(others)]
            elif attack == "hide_just_cheaper":                 # the k offers priced just below the target
                tp = float(page.loc[page.trip_id == target, "price_per_km"].iloc[0])
                others = page[(page.trip_id != target) & (page.price_per_km < tp)].nlargest(k, "price_per_km").trip_id
                shown = page[~page.trip_id.isin(others)]
            else:
                tp = float(page.loc[page.trip_id == target, "price_per_km"].iloc[0])
                fake = page.sample(k, random_state=int(rng.integers(1e9))).copy()
                fake["trip_id"] = [f"fake{i}" for i in range(k)]
                fake["price_per_km"] = page.price_per_km.max() * 1.5 if attack == "add_expensive_fakes" else tp * 1.0001
                shown = pd.concat([page, fake], ignore_index=True)
            new = order(shown); real = [t for t in new if not str(t).startswith("fake")]
            before = [t for t in honest if t in set(real)]
            g = before.index(target) - real.index(target)       # offers overtaken among those still shown
            gains.append(g); top10 += real.index(target) < 10
        res[f"{attack}_k{k}"] = dict(median_positions_gained=float(np.median(gains)), p90=float(np.percentile(gains, 90)),
                                     max=int(max(gains)), share_reaching_top10=top10 / 1000)
res["note"] = "Target at position 50 of 100; the recomputation on the manipulated set reproduces every published score, so none of these is flagged."
json.dump(res, open(os.path.join(OUT, "omission_attack.json"), "w"), indent=2)
print(json.dumps(res, indent=1))
