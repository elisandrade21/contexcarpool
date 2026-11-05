#!/usr/bin/env python3
"""Adds synthetic device context to 100-offer searches, with the reference answers of
rules R9-R12. The pickup-distance and departure parameters are illustrative: no public
dataset reports them together, so they only exercise the rules. Distances use the same
equirectangular approximation as rules_context.ru, so the reference is exact."""
import json, math, os
import numpy as np

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "out")
CITY = {"Brazil": (-8.05, -34.95), "France": (48.86, 2.35), "Italy": (41.9, 12.5),
        "Portugal": (38.76, -9.18), "Ukraine": (50.45, 30.52)}
# Recife and Lisbon are on the coast: points are redrawn until they fall inside these land boxes
# (min lat, max lat, min lon, max lon), which also truncates the distances there.
LAND = {"Brazil": (-8.16, -7.93, -35.02, -34.90), "Portugal": (38.72, 38.85, -9.30, -9.10)}
def on_land(m, lat, lon):
    b = LAND.get(m)
    return b is None or (b[0] <= lat <= b[1] and b[2] <= lon <= b[3])
rng = np.random.default_rng(20261105)
d = json.load(open(os.path.join(OUT, "mobile_searches.json")))
NOW = 29_000_000
cover = dict(R9=0, R10=0, R11=0, R12=0, R13=0); total = 0; by_market = {}
def add(s):
    global total
    while True:
        lat = CITY[s["market"]][0] + float(rng.uniform(-0.05, 0.05)); lon = CITY[s["market"]][1] + float(rng.uniform(-0.05, 0.05))
        if on_land(s["market"], lat, lon): break
    cos = round(math.cos(math.radians(lat)), 6)
    s["context"] = dict(lat=round(lat, 6), lon=round(lon, 6), cos=cos, now=NOW)
    for o in s["offers"]:
        while True:
            dist = float(rng.lognormal(math.log(2500), 1.0))          # median 2.5 km
            ang = float(rng.uniform(0, 2 * math.pi))
            o["plat"] = round(s["context"]["lat"] + dist * math.sin(ang) / 111320.0, 6)
            o["plon"] = round(s["context"]["lon"] + dist * math.cos(ang) / (111320.0 * cos), 6)
            if on_land(s["market"], o["plat"], o["plon"]): break
        o["dep"] = NOW + int(rng.integers(5, 12 * 60))                # 5 min to 12 h ahead
        dy = 111320.0 * (o["plat"] - s["context"]["lat"])
        dx = 111320.0 * cos * (o["plon"] - s["context"]["lon"])
        d2 = dx * dx + dy * dy; t = o["dep"] - NOW
        n = []
        if d2 <= 640000.0: n.append("R9")
        if d2 > 25000000.0: n.append("R10")
        if 0 <= t <= 60: n.append("R11")
        if t >= 0 and d2 > (83.33 * t) ** 2: n.append("R12")
        if t >= 0 and (d2 > 25000000.0 or d2 > (83.33 * t) ** 2) and d2 <= (416.67 * t) ** 2: n.append("R13")
        o["notes"] = n; total += 1
        m = by_market.setdefault(s["market"], dict(offers=0, R9=0, R10=0, R11=0, R12=0, R13=0)); m["offers"] += 1
        for r in n: cover[r] += 1; m[r] += 1
for s in d["check"]: add(s)
c100 = {k: round(100 * v / total, 1) for k, v in cover.items()}
n_check = total
market_pct = {k: dict(offers=v["offers"], **{r: round(100 * v[r] / v["offers"], 1) for r in cover}) for k, v in sorted(by_market.items())}
for lst in d["latency"].values():
    for s in lst: add(s)
for s in d["demo"].values(): add(s)
json.dump(d, open(os.path.join(OUT, "mobile_searches.json"), "w"))
json.dump(dict(offers=n_check, coverage_percent=c100, by_market=market_pct), open(os.path.join(OUT, "context_coverage.json"), "w"), indent=2)
print(n_check, c100); print(json.dumps(market_pct))
