#!/usr/bin/env python3
"""Copies the published SPARQL and ontology files, the Oxigraph web build and the sample
searches next to the page, so that the phone runs the same files as the other engines.
Usage: build_web.py <path to node_modules>"""
import json, os, shutil, sys
HERE = os.path.dirname(os.path.abspath(__file__)); WEB = os.path.join(HERE, "web"); nm = sys.argv[1]
os.makedirs(os.path.join(WEB, "files"), exist_ok=True)
for src in ["../../ontology/ridesharing.ttl", "../../ontology/rules.ru", "../../ontology/rules_context.ru",
            "../sparql/cost_percentiles.rq", "../sparql/rationale.rq", "../sparql/cq6_context_notes.rq", "../sparql/cq7_personal_view.rq",
            "../../ontology/rules_settlement.ru", "../sparql/cq8_settlement.rq"]:
    shutil.copy(os.path.join(HERE, src), os.path.join(WEB, "files"))
for f in ["web.js", "web_bg.wasm"]:
    shutil.copy(os.path.join(nm, "oxigraph", f), os.path.join(WEB, f))
for f in ["leaflet.js", "leaflet.css"]:
    shutil.copy(os.path.join(nm, "leaflet", "dist", f), os.path.join(WEB, f))
d = json.load(open(os.path.join(HERE, "..", "out", "mobile_searches.json")))
json.dump(dict(demo=d["demo"]), open(os.path.join(WEB, "searches.json"), "w"))
json.dump({k: d["latency"][k] for k in ("20", "100")}, open(os.path.join(WEB, "bench.json"), "w"))   # loaded only by the speed test
print("ok")
