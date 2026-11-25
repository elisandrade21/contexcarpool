#!/usr/bin/env python3
"""Builds the independent checker site (checker/site): the page, the checker module, the Oxigraph web build, the
registered rule files and the platform's registered public key. Serve it from an origin other than the platform's,
e.g. python3 -m http.server 8802 --directory checker/site. Usage: build_site.py <path to node_modules>"""
import os, shutil, sys
H = os.path.dirname(os.path.abspath(__file__)); SITE = os.path.join(H, "site"); nm = sys.argv[1]
os.makedirs(os.path.join(SITE, "files"), exist_ok=True)
for f in ["../../../ontology/ridesharing.ttl", "../../../ontology/rules.ru", "../../sparql/cost_percentiles.rq", "../../sparql/rationale.rq"]:
    shutil.copy(os.path.join(H, f), os.path.join(SITE, "files"))
for f in ["web.js", "web_bg.wasm"]: shutil.copy(os.path.join(nm, "oxigraph", f), SITE)
shutil.copy(os.path.join(H, "checker.mjs"), SITE); shutil.copy(os.path.join(H, "index.html"), SITE)
shutil.copy(os.path.join(H, "../../out/signed/platform_key.json"), SITE)
print("ok")
