#!/usr/bin/env python3
"""Engine-independence check: run the SAME W3C artefacts (SPARQL 1.1 Update
cost percentiles, SPARQL 1.1 Update rules R1-R8, SPARQL ranking/rationale
query) in Python rdflib and compare with the reference implementation.
Run after run_experiment.py:  python3 crosscheck_rdflib.py
"""
import json, os, time
import numpy as np, pandas as pd
from rdflib import Graph, Literal, Namespace, URIRef, RDF, XSD

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
WM = Namespace("http://example.org/ridesharing#")
read = lambda p: open(os.path.join(HERE, p)).read()
COST = read("sparql/cost_percentiles.rq")
RULES = read("../ontology/rules.ru")
RATIONALE = read("sparql/rationale.rq")
tbox = Graph().parse(os.path.join(HERE, "..", "ontology", "ridesharing.ttl"))

listings = pd.read_csv(os.path.join(OUT, "listings.csv"))
rng = np.random.default_rng(20260608)
n_search, size = 30, 100
mismatch_S = mismatch_rule = mismatch_trade = mismatch_order = 0
ms = []
for _ in range(n_search):
    c = rng.choice(listings.country.unique())
    sub = listings[listings.country == c].sample(size, random_state=int(rng.integers(1e9)))
    g = Graph()
    for t in tbox:
        g.add(t)
    for r in sub.itertuples(index=False):
        a = WM[f"trip_{r.trip_id}"]
        g.add((a, RDF.type, WM.Travel))
        g.add((a, WM.hasMarket, Literal(c)))
        g.add((a, WM.hasSeatsAvailable, Literal(int(r.seats_available), datatype=XSD.integer)))
        g.add((a, WM.hasBookingMode, Literal("auto" if r.booking_auto == 1 else "manual")))
        g.add((a, WM.hasPricePerKm, Literal(str(r.price_per_km), datatype=XSD.decimal)))
    t0 = time.perf_counter()
    g.update(COST); g.update(RULES)
    rows = list(g.query(RATIONALE, initBindings={"market": Literal(c)}))
    ms.append((time.perf_counter() - t0) * 1000)
    # reference: within-search scores computed by the reference implementation
    ref = sub.copy()
    ref["f_K"] = (1.0 - ref.price_per_km.rank(pct=True)) * 10.0
    ref["f_B"] = np.where(ref.booking_auto == 1, 10.0, 2.5)
    ref["S"] = 0.4 * ref.f_C + 0.4 * ref.f_K + 0.2 * ref.f_B
    rule_of = {1: "R4", 2: "R3", 3: "R2", 4: "R1"}
    def trade(a, k):                                    # expected trade-off rule
        if k >= 7.5: return "R5" if a == 1 else "R6"
        if k < 2.5: return "R7" if a == 1 else "R8"
        return None
    refd = {f"trip_{r.trip_id}": r for r in ref.itertuples(index=False)}
    prev = float("inf")
    for row in rows:
        tid = str(row.offer).rsplit("#", 1)[1]; r = refd[tid]
        s = float(row.S)
        mismatch_S += abs(s - r.S) > 1e-9
        mismatch_rule += str(row.rule) != rule_of[int(r.seats_available)]
        got = str(row.tradeRule) if row.tradeRule is not None else None
        mismatch_trade += got != trade(r.booking_auto, r.f_K)        # exact rule R5-R8 (or none)
        mismatch_order += s > prev + 1e-12; prev = s
    assert len(rows) == size
    # full order: the rdflib order must equal the reference order up to ties
    ref_sorted = ref.sort_values("S", ascending=False).S.values
    got_sorted = np.array([float(rw.S) for rw in rows])
    mismatch_order += int(np.any(np.abs(ref_sorted - got_sorted) > 1e-9))
res = dict(engine="rdflib " + __import__("rdflib").__version__, searches=n_search, offers_per_search=size,
           score_mismatches=int(mismatch_S), rule_mismatches=int(mismatch_rule),
           tradeoff_mismatches=int(mismatch_trade), order_violations=int(mismatch_order),
           median_ms_per_search=round(float(np.median(ms)), 1))
json.dump(res, open(os.path.join(OUT, "crosscheck_rdflib.json"), "w"), indent=2)
print(json.dumps(res, indent=2))
