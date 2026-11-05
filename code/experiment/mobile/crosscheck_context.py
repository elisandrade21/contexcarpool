#!/usr/bin/env python3
"""rdflib run of the mobile module on the same searches as crosscheck_oxigraph.mjs:
rules R1-R8, then R9-R12, CQ1 and CQ6; compares with the reference answers."""
import json, os
from rdflib import Graph, Literal, Namespace, RDF, XSD

HERE = os.path.dirname(os.path.abspath(__file__))
read = lambda p: open(os.path.join(HERE, p)).read()
WM = Namespace("http://example.org/ridesharing#"); SCH = Namespace("https://schema.org/")
data = json.load(open(os.path.join(HERE, "..", "out", "mobile_searches.json")))
tbox = Graph().parse(os.path.join(HERE, "..", "..", "ontology", "ridesharing.ttl"))
dec = lambda v: Literal(str(v), datatype=XSD.decimal)
bad = dict(score=0, rule=0, trade=0, notes=0, moved=0, cq7=0, fare=0, trips=0)
for s in data["check"]:
    g = Graph()
    for t in tbox: g.add(t)
    c = s["context"]
    g.add((WM.device, RDF.type, WM.DeviceContext)); g.add((WM.device, SCH.latitude, dec(c["lat"])))
    g.add((WM.device, SCH.longitude, dec(c["lon"]))); g.add((WM.device, WM.hasCosLatitude, dec(c["cos"])))
    g.add((WM.device, WM.hasNowMinute, Literal(c["now"], datatype=XSD.integer)))
    for o in s["offers"]:
        a = WM[o["id"]]; p = WM[o["id"] + "-pickup"]
        g.add((a, RDF.type, WM.Travel)); g.add((a, WM.hasMarket, Literal(s["market"])))
        g.add((a, WM.hasSeatsAvailable, Literal(o["seats"], datatype=XSD.integer)))
        g.add((a, WM.hasBookingMode, Literal(o["booking"]))); g.add((a, WM.hasPricePerKm, dec(o["price_per_km"])))
        g.add((a, WM.hasDepartureMinute, Literal(o["dep"], datatype=XSD.integer))); g.add((a, WM.hasPickup, p))
        g.add((p, RDF.type, WM.Place)); g.add((p, SCH.latitude, dec(o["plat"]))); g.add((p, SCH.longitude, dec(o["plon"])))
    g.update(read("../sparql/cost_percentiles.rq")); g.update(read("../../ontology/rules.ru"))
    q = read("../sparql/rationale.rq")
    before = [(str(r.offer), float(r.S)) for r in g.query(q, initBindings={"market": Literal(s["market"])})]
    g.update(read("../../ontology/rules_context.ru"))
    after = [(str(r.offer), float(r.S)) for r in g.query(q, initBindings={"market": Literal(s["market"])})]
    bad["moved"] += sum(x != y for x, y in zip(before, after))
    got = {o["id"]: [] for o in s["offers"]}
    for r in g.query(read("../sparql/cq6_context_notes.rq")):
        got[str(r.offer).rsplit("#", 1)[1]].append(str(r.rule))
    ref = {o["id"]: o for o in s["offers"]}
    bad["notes"] += sum(sorted(got[i]) != sorted(ref[i]["notes"]) for i in got)
    bad["score"] += sum(abs(S - ref[o.rsplit("#", 1)[1]]["S"]) > 1e-9 for o, S in after)
    tier = lambda o: 2 if o["dep"] < c["now"] else 1 if "R13" in o["notes"] else 2 if ("R12" in o["notes"] or "R10" in o["notes"]) else 0
    got7 = [(int(r.blocked), round(float(r.S), 9)) for r in g.query(read("../sparql/cq7_personal_view.rq"))]
    ref7 = sorted(((tier(o), round(o["S"], 9)) for o in s["offers"]), key=lambda x: (x[0], -x[1]))
    bad["cq7"] += got7 != ref7
    for o in s["offers"]:
        if "trip" not in o: continue
        for who, k in (("passenger", o["trip"]["kp"]), ("driver", o["trip"]["kd"])):
            r = WM[o["id"] + "-rec-" + who]
            g.add((r, RDF.type, WM.TripRecord)); g.add((r, WM.ofOffer, WM[o["id"]]))
            g.add((r, WM.recordedBy, Literal(who))); g.add((r, WM.hasTravelledKm, dec(k)))
        g.add((WM[o["id"]], WM.hasDistance, dec(o["distance"])))
    g.update(read("../../ontology/rules_settlement.ru"))
    got8 = {str(r.offer).rsplit("#", 1)[1]: r for r in g.query(read("../sparql/cq8_settlement.rq"))}
    for o in s["offers"]:
        if "trip" not in o: continue
        bad["trips"] += 1; r = got8.get(o["id"])
        if r is None: bad["fare"] += 1
        elif o["trip"].get("disputed"): bad["fare"] += not r.disputed.toPython()
        else: bad["fare"] += abs(float(r.fare) - o["trip"]["fare"]) > 1e-9
res = dict(engine="rdflib", searches=len(data["check"]), offers_per_search=100, score_mismatches=bad["score"],
           context_note_mismatches=bad["notes"], order_changed_by_context=bad["moved"], personal_view_mismatches=bad["cq7"], settlement_trips=bad["trips"], settlement_mismatches=bad["fare"])
json.dump(res, open(os.path.join(HERE, "..", "out", "crosscheck_context_rdflib.json"), "w"), indent=2)
print(res)
