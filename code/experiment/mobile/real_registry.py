#!/usr/bin/env python3
"""Semi-real scenario from the French carpool registry (Registre de Preuve de Covoiturage,
data.gouv.fr, Licence Ouverte): REAL departure point, departure time and distance of completed
short-distance trips in the Lyon and Paris metropolitan areas, used as if they were open offers.
Each search matches a real passenger trip: the offers start and end within 5 km of that trip's origin and
destination and leave within 12 hours; the passenger stands at the real origin. Result pages of 20 offers.
Price per km and booking mode are modelled from the published statistics of calibrated_france.py;
seats are the same assumption as the base generator. Appends searches and reference answers to
out/mobile_searches.json. The sample comes from the first days of 2026-10.csv:
  python3 real_registry.py <path to the csv>   (only needed to rebuild the sample)"""
import json, math, os, sys
import numpy as np, pandas as pd

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "out")
SAMPLE = os.path.join(OUT, "registry_sample.csv.gz")
GROUPS = {"Paris": "Métropole du Grand Paris", "Lyon": "Métropole de Lyon"}
if len(sys.argv) > 1:
    raw = pd.read_csv(sys.argv[1], sep=";", dtype=str, on_bad_lines="skip").iloc[:-1]      # last row is cut
    raw = raw[raw.journey_start_towngroup.isin(GROUPS.values())].drop_duplicates("trip_id")
    raw[["trip_id", "journey_start_datetime", "journey_start_lat", "journey_start_lon", "journey_end_lat",
         "journey_end_lon", "journey_distance", "journey_start_towngroup"]].to_csv(SAMPLE, index=False)
R = pd.read_csv(SAMPLE, dtype={"trip_id": str})
R["minute"] = (pd.to_datetime(R.journey_start_datetime, utc=True).astype("int64") // 10**9 // 60
               if str(pd.to_datetime(R.journey_start_datetime, utc=True).dtype).endswith("ns, UTC]")
               else pd.to_datetime(R.journey_start_datetime, utc=True).map(lambda t: int(t.timestamp()) // 60))
rng = np.random.default_rng(20261106)
FC = {1: 2.5, 2: 5.0, 3: 7.5, 4: 10.0}
RULE = {1: "R4", 2: "R3", 3: "R2", 4: "R1"}

def km(a1, o1, a2, o2):
    return 111.32 * np.sqrt((a2 - a1) ** 2 + (np.cos(np.radians(a1)) * (o2 - o1)) ** 2)

def search(city, now=None):
    pool = R[(R.journey_start_towngroup == GROUPS[city])]
    me = pool.sample(1, random_state=int(rng.integers(1e9))).iloc[0]
    lat, lon = float(me.journey_start_lat), float(me.journey_start_lon)
    cos = round(math.cos(math.radians(lat)), 6)
    now = int(me.minute) - 60 if now is None else now
    od = (km(lat, lon, pool.journey_start_lat, pool.journey_start_lon) <= 5) & \
         (km(float(me.journey_end_lat), float(me.journey_end_lon), pool.journey_end_lat, pool.journey_end_lon) <= 5)
    cand = pool[od & (pool.minute >= now + 5) & (pool.minute <= now + 720) & (pool.trip_id != me.trip_id)]
    return lat, lon, cos, cand, now

def pack(city, n, now=None):
    lat, lon, cos, cand, now = search(city, now)
    if len(cand) < n: return None
    sub = cand.sample(n, random_state=int(rng.integers(1e9))).reset_index(drop=True)
    auto = (rng.random(n) < 0.42).astype(int)
    ppk = np.round(rng.lognormal(math.log(0.0625), 0.20, n) * np.exp(-0.018 * auto), 4)
    seats = rng.choice([1, 2, 3, 4], n, p=[0.22, 0.36, 0.32, 0.10])
    fK = (1.0 - pd.Series(ppk).rank(pct=True).values) * 10.0
    S = 0.4 * np.array([FC[s] for s in seats]) + 0.4 * fK + 0.2 * np.where(auto == 1, 10.0, 2.5)
    offers = []
    for i, r in enumerate(sub.itertuples(index=False)):
        plat, plon, dep = float(r.journey_start_lat), float(r.journey_start_lon), int(r.minute)
        dy = 111320.0 * (plat - lat); dx = 111320.0 * cos * (plon - lon); d2 = dx * dx + dy * dy; t = dep - now
        notes = []
        if d2 <= 640000.0: notes.append("R9")
        if d2 > 25000000.0: notes.append("R10")
        if 0 <= t <= 60: notes.append("R11")
        if t >= 0 and d2 > (83.33 * t) ** 2: notes.append("R12")
        if t >= 0 and (d2 > 25000000.0 or d2 > (83.33 * t) ** 2) and d2 <= (416.67 * t) ** 2: notes.append("R13")
        k = fK[i]
        trade = ("R5" if auto[i] else "R6") if k >= 7.5 else (("R7" if auto[i] else "R8") if k < 2.5 else None)
        offers.append(dict(id=f"trip_{city[:2].upper()}R-{i:04d}", seats=int(seats[i]), booking="auto" if auto[i] else "manual",
                           price_per_km=str(ppk[i]), distance=str(round(float(r.journey_distance) / 1000, 3)),
                           S=float(S[i]), rule=RULE[int(seats[i])], trade=trade, plat=plat, plon=plon, dep=dep, notes=notes))
    return dict(market="France", currency="EUR", source="registry", city=city,
                context=dict(lat=lat, lon=lon, cos=cos, now=now), offers=offers)

path = os.path.join(OUT, "mobile_searches.json")
d = json.load(open(path))
d["check"] = [s for s in d["check"] if s.get("source") != "registry"]
new = []; lo, hi = int(R.minute.min()), int(R.minute.max()) - 720
tries = 0
for city in GROUPS:
    got = 0
    while got < 15:
        tries += 1
        s = pack(city, 20)
        if s: new.append(s); got += 1
d["check"] += new
# Demo: one matched search per city.
for city in GROUPS:
    s = None
    while s is None: s = pack(city, 20)
    d["demo"]["real_" + city.lower()] = s
json.dump(d, open(path, "w"))
tot = sum(len(s["offers"]) for s in new)
cov = {r: round(100 * sum(r in o["notes"] for s in new for o in s["offers"]) / tot, 1) for r in ("R9", "R10", "R11", "R12", "R13")}
km = [float(o["distance"]) for s in new for o in s["offers"]]
json.dump(dict(searches=len(new), offers=tot, trips_in_sample=len(R), sampled_passenger_trips=tries, match_radius_km=5, coverage_percent=cov, median_distance_km=round(float(np.median(km)), 1)),
          open(os.path.join(OUT, "real_registry_coverage.json"), "w"), indent=2)
print(len(new), tot, cov, "km", round(float(np.median(km)), 1), "sample", len(R), "check", len(d["check"]))
