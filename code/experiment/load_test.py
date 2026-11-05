#!/usr/bin/env python3
"""HTTP load test of experiment/service/RankService.java (must be running).
Sends 100-offer searches (France) with 1, 4 and 8 concurrent clients and checks
that the returned order matches the reference composite score.
Usage: python3 load_test.py [port]"""
import json, os, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
import numpy as np, pandas as pd

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
URL = f"http://127.0.0.1:{PORT}/rank"
L = pd.read_csv(os.path.join(os.path.dirname(__file__), "out", "listings.csv"))
fr = L[L.country == "France"]
rng = np.random.default_rng(20260609)

def payload(n=100):
    sub = fr.sample(n, random_state=int(rng.integers(1e9)))
    return sub, json.dumps([dict(id=r.trip_id, market="France", seats=int(r.seats_available),
                                 booking="auto" if r.booking_auto == 1 else "manual",
                                 price_per_km=float(r.price_per_km), distance=float(r.distance_km))
                            for r in sub.itertuples(index=False)]).encode()

def call(body):
    t0 = time.perf_counter()
    req = urllib.request.Request(URL, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        out = json.loads(r.read())
    return (time.perf_counter() - t0) * 1000, out

# correctness on 20 requests
bad = 0
for _ in range(20):
    sub, body = payload()
    _, out = call(body)
    ref = sub.assign(fK=(1 - sub.price_per_km.rank(pct=True)) * 10)
    ref = ref.assign(S=0.4 * ref.f_C + 0.4 * ref.fK + 0.2 * np.where(ref.booking_auto == 1, 10, 2.5))
    refS = dict(zip(ref.trip_id, ref.S))
    got = [(o["id"], o["S"]) for o in out["ranked"]]
    bad += any(abs(s - refS[i]) > 1e-9 for i, s in got) or len(got) != 100 \
        or any(got[k][1] < got[k + 1][1] - 1e-12 for k in range(len(got) - 1))
for _ in range(10):                                   # warm-up
    call(payload()[1])
res = dict(service="RankService (JDK HttpServer + Apache Jena 4.10), localhost",
           offers_per_request=100, correctness_requests=20, requests_with_wrong_order_or_score=int(bad))
for conc in (1, 4, 8):
    bodies = [payload()[1] for _ in range(300)]
    t0 = time.perf_counter()
    with ThreadPoolExecutor(conc) as ex:
        lat = [ms for ms, _ in ex.map(call, bodies)]
    wall = time.perf_counter() - t0
    res[f"concurrency_{conc}"] = dict(requests=300, median_ms=round(float(np.median(lat)), 1),
                                      p95_ms=round(float(np.percentile(lat, 95)), 1),
                                      throughput_req_s=round(300 / wall, 1))
json.dump(res, open(os.path.join(os.path.dirname(__file__), "out", "service_load.json"), "w"), indent=2)
print(json.dumps(res, indent=2))
