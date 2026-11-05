#!/usr/bin/env python3
"""Export benchmark searches with the reference answers, so that an engine outside
Python (Oxigraph in Node or in a phone browser) can run the same SPARQL files on them.
The 30 searches of 100 offers use the same seed as crosscheck_rdflib.py."""
import json, os
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "out")
L = pd.read_csv(os.path.join(OUT, "listings.csv"))

def pack(sub, market):
    ref = sub.copy()
    ref["f_K"] = (1.0 - ref.price_per_km.rank(pct=True)) * 10.0
    ref["f_B"] = np.where(ref.booking_auto == 1, 10.0, 2.5)
    ref["S"] = 0.4 * ref.f_C + 0.4 * ref.f_K + 0.2 * ref.f_B
    rule_of = {1: "R4", 2: "R3", 3: "R2", 4: "R1"}
    def trade(a, k):
        if k >= 7.5: return "R5" if a == 1 else "R6"
        if k < 2.5: return "R7" if a == 1 else "R8"
        return None
    return dict(market=market, currency=str(ref.currency.iloc[0]), offers=[
        dict(id=f"trip_{r.trip_id}", seats=int(r.seats_available),
             booking="auto" if r.booking_auto == 1 else "manual", price_per_km=str(r.price_per_km), distance=str(r.distance_km),
             S=float(r.S), rule=rule_of[int(r.seats_available)], trade=trade(r.booking_auto, r.f_K))
        for r in ref.itertuples(index=False)])

rng = np.random.default_rng(20260608)                 # same stream as crosscheck_rdflib.py
check = []
for _ in range(30):
    c = str(rng.choice(L.country.unique()))
    check.append(pack(L[L.country == c].sample(100, random_state=int(rng.integers(1e9))), c))
fr = L[L.country == "France"]
latency = {str(n): [pack(fr.sample(n, random_state=1000 + i), "France") for i in range(3 if n == 1000 else 40)]
           for n in (20, 100, 1000)}
# Balanced part: six more searches per market, so that every location is tested equally.
for c in sorted(L.country.unique()):
    for i in range(6):
        check.append(pack(L[L.country == c].sample(100, random_state=7000 + i), str(c)))
demo = {str(c): pack(L[L.country == c].sample(20, random_state=11), str(c)) for c in sorted(L.country.unique())}
json.dump(dict(check=check, latency=latency, demo=demo), open(os.path.join(OUT, "mobile_searches.json"), "w"))
print("ok", len(check))
