#!/usr/bin/env python3
"""Can a third party detect a manipulated ranking with the W3C artifacts only?

A 'platform' publishes, for each search, the ordered offers with S, comfort
level, comfort rule, trade-off rule and booking mode. An independent AUDITOR
holds only the raw listing fields and the public W3C files (cost_percentiles.rq,
rules.ru, rationale.rq); it recomputes everything in rdflib (a different engine
from the platform) and flags the output if the order, any score or any
rationale field differs. We plant six manipulations and count detections, and
count false alarms on honest outputs.
"""
import json, os, time
import numpy as np, pandas as pd
from rdflib import Graph, Literal, Namespace, RDF, XSD

HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "out")
WM = Namespace("http://example.org/ridesharing#")
read = lambda p: open(os.path.join(HERE, p)).read()
COST, RULES, RAT = read("sparql/cost_percentiles.rq"), read("../ontology/rules.ru"), read("sparql/rationale.rq")
tbox = Graph().parse(os.path.join(HERE, "..", "ontology", "ridesharing.ttl"))
FC = {1: 2.5, 2: 5.0, 3: 7.5, 4: 10.0}
LVL = {1: "Uncomfortable", 2: "Bearable", 3: "Comfortable", 4: "VeryComfortable"}
RULE = {1: "R4", 2: "R3", 3: "R2", 4: "R1"}
L = pd.read_csv(os.path.join(OUT, "listings.csv"))
rng = np.random.default_rng(20260613)


def trade(a, k):
    if k >= 7.5: return "R5" if a == 1 else "R6"
    if k < 2.5: return "R7" if a == 1 else "R8"
    return ""


def platform(sub, w=(0.4, 0.4, 0.2)):
    """Honest platform output (reference implementation, no RDF)."""
    d = sub.copy()
    d["fK"] = (1.0 - d.price_per_km.rank(pct=True)) * 10.0
    d["fC"] = d.seats_available.map(FC); d["fB"] = np.where(d.booking_auto == 1, 10.0, 2.5)
    d["S"] = w[0] * d.fC + w[1] * d.fK + w[2] * d.fB
    d["level"] = d.seats_available.map(LVL); d["rule"] = d.seats_available.map(RULE)
    d["trade"] = [trade(a, k) for a, k in zip(d.booking_auto, d.fK)]
    return d.sort_values("S", ascending=False, kind="stable").reset_index(drop=True)


def auditor(sub, market):
    """Third-party audit with rdflib + the published W3C files."""
    g = Graph()
    for t in tbox: g.add(t)
    for r in sub.itertuples(index=False):
        a = WM[f"trip_{r.trip_id}"]
        g.add((a, RDF.type, WM.Travel)); g.add((a, WM.hasMarket, Literal(market)))
        g.add((a, WM.hasSeatsAvailable, Literal(int(r.seats_available), datatype=XSD.integer)))
        g.add((a, WM.hasBookingMode, Literal("auto" if r.booking_auto == 1 else "manual")))
        g.add((a, WM.hasPricePerKm, Literal(str(r.price_per_km), datatype=XSD.decimal)))
    g.update(COST); g.update(RULES)
    rows = g.query(RAT, initBindings={"market": Literal(market)})
    return {str(x.offer).rsplit("trip_", 1)[1]: dict(S=float(x.S), level=str(x.level).rsplit("#", 1)[1], rule=str(x.rule),
                                                       trade=str(x.tradeRule) if x.tradeRule is not None else "") for x in rows}


def flagged(pub, aud):
    """True if the published output is inconsistent with the audit."""
    for r in pub.itertuples(index=False):
        a = aud[r.trip_id]
        if abs(r.S - a["S"]) > 1e-6 or r.level != a["level"] or r.rule != a["rule"] or r.trade != a["trade"]:
            return True
    s = pub.S.values                                          # published order must follow the audited S
    audS = np.array([aud[t]["S"] for t in pub.trip_id])
    return bool(np.any(audS[:-1] < audS[1:] - 1e-9)) or bool(np.any(s[:-1] < s[1:] - 1e-9))


def flagged_order_only(pub, aud):
    """Weaker publication: only the order and rationale (no scores)."""
    audS = np.array([aud[t]["S"] for t in pub.trip_id])
    return bool(np.any(audS[:-1] < audS[1:] - 1e-9))


def manipulations(p, sub):
    out = {}
    q = platform(sub, (0.3, 0.3, 0.4)); out["weights_changed_0.3_0.3_0.4"] = q
    q = platform(sub, (0.42, 0.38, 0.20)); out["weights_shifted_by_0.02"] = q
    q = p.copy(); k = int(rng.integers(20, 60)); row = q.iloc[[k]]
    out["offer_promoted_to_top"] = pd.concat([row, q.drop(index=k)]).reset_index(drop=True)
    q = p.copy(); i = int(rng.integers(0, len(q))); q.loc[i, "level"] = "VeryComfortable" if q.loc[i, "level"] != "VeryComfortable" else "Comfortable"
    out["comfort_claim_altered"] = q
    q = p.copy(); idx = q.index[q.trade.isin(["R6", "R8"])]
    if len(idx): q.loc[idx[0], "trade"] = ""
    out["approval_requirement_hidden"] = q
    q = p.copy(); boost = rng.choice(len(q), 5, replace=False); q.loc[boost, "S"] += 0.3
    out["hidden_boost_5_offers"] = q.sort_values("S", ascending=False, kind="stable").reset_index(drop=True)
    return out


N = 200
det, det_order, honest_fp, ms = {}, {}, 0, []
for _ in range(N):
    m = rng.choice(L.country.unique()); mk = L[L.country == m]
    sub = mk.iloc[rng.choice(len(mk), 100, replace=False)]
    t0 = time.perf_counter(); aud = auditor(sub, m); ms.append((time.perf_counter() - t0) * 1000)
    p = platform(sub)
    honest_fp += flagged(p, aud)
    for name, q in manipulations(p, sub).items():
        det.setdefault(name, 0); det[name] += flagged(q, aud)
        if name.startswith("weights") or name.startswith("hidden") or name.startswith("offer"):
            det_order.setdefault(name, 0); det_order[name] += flagged_order_only(q, aud)
res = dict(searches=N, offers_per_search=100, auditor_engine="rdflib (SPARQL 1.1)",
           honest_outputs_flagged=int(honest_fp),
           detected={k: f"{v}/{N}" for k, v in det.items()},
           detected_if_only_order_published={k: f"{v}/{N}" for k, v in det_order.items()},
           auditor_median_ms=round(float(np.median(ms)), 1))
json.dump(res, open(os.path.join(OUT, "tamper_audit.json"), "w"), indent=2)
print(json.dumps(res, indent=2))
