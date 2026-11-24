#!/usr/bin/env bash
# Regenerates every number of the paper that does not come from a phone, and compares the results with the
# committed ones. Usage:  ./reproduce.sh            (Python 3.10+, Java 11+, Node 18+, curl, npm)
#                         ./reproduce.sh --gsdc DIR  (also the GNSS fare analysis; DIR = Kaggle GSDC 2022 train folder,
#                                                     which cannot be redistributed: see code/experiment/gsdc/README.md)
# Phone measurements (out/mobile_runs*, Table 4) and the language-model calls (they cost money) are not re-run:
# their raw files are in the repository and the checks on them are re-run.
set -euo pipefail
cd "$(dirname "$0")/code"
GSDC=""; [ "${1:-}" = "--gsdc" ] && GSDC="$2"
JENA=apache-jena-4.10.0
URL=https://archive.apache.org/dist/jena/binaries/$JENA.tar.gz
OX_VERSION=0.5.13
PORT=8765

step() { printf '\n== %s\n' "$*"; }

step "Dependencies"
python3 -m pip install -q -r requirements.txt
mkdir -p .tools
if [ ! -d .tools/$JENA ]; then
  curl -fsSL -o .tools/jena.tgz "$URL"
  curl -fsSL -o .tools/jena.tgz.sha512 "$URL.sha512"
  want=$(awk '{print $1}' .tools/jena.tgz.sha512); got=$(shasum -a 512 .tools/jena.tgz | awk '{print $1}')
  [ "$want" = "$got" ] || { echo "Jena checksum mismatch"; exit 1; }
  tar xzf .tools/jena.tgz -C .tools && rm .tools/jena.tgz .tools/jena.tgz.sha512
fi
[ -d .tools/node_modules/oxigraph ] || npm install --silent --prefix .tools oxigraph@$OX_VERSION
CP=".tools/$JENA/lib/*"
OX="$PWD/.tools/node_modules/oxigraph/node.js"

BEFORE=$(mktemp -d); cp experiment/out/*.json "$BEFORE/"

step "Benchmark, reference and Jena (RQ1-RQ3)"
python3 experiment/run_experiment.py
java -cp "$CP" experiment/jena/Validate.java
python3 experiment/crosscheck_rdflib.py
python3 experiment/rq1_redundancy.py
python3 experiment/data_stability.py
python3 experiment/tamper_audit.py
python3 experiment/omission_attack.py
python3 experiment/baselines.py
python3 experiment/calibrated_france.py

step "Mobile client: context and fare rules, registry searches, phone engine (Oxigraph)"
python3 experiment/mobile/export_searches.py
python3 experiment/mobile/context_data.py
python3 experiment/mobile/real_registry.py
python3 experiment/mobile/settlement_data.py
python3 experiment/mobile/settlement_sensitivity.py
node experiment/mobile/cq7check.mjs "$OX"
node experiment/mobile/crosscheck_oxigraph.mjs "$OX"
python3 experiment/mobile/crosscheck_context.py
java -cp "$CP" experiment/mobile/ContextCheck.java

step "HTTP service: rationale check and load test"
java -cp "$CP" experiment/service/RankService.java $PORT 127.0.0.1 > /tmp/contexcarpool_service.log 2>&1 &
SVC=$!; trap 'kill $SVC 2>/dev/null || true' EXIT
for _ in $(seq 60); do curl -s -o /dev/null "http://127.0.0.1:$PORT/" && break; sleep 1; done
node experiment/mobile/rationale_check.mjs "$OX" $PORT
python3 experiment/load_test.py $PORT

step "Language-model rationales: checker on the stored model texts (no API call)"
node experiment/llm/facts.mjs "$OX"
python3 experiment/llm/controls.py
python3 experiment/llm/evaluate.py > /dev/null
python3 experiment/llm/evaluate_sonnet.py > /dev/null
python3 experiment/readability.py > /dev/null

if [ -n "$GSDC" ]; then
  step "GNSS fare analysis (Google Smartphone Decimeter Challenge 2022)"
  BEFORE_G=$(mktemp -d); cp experiment/gsdc/*.json "$BEFORE_G/"
  mkdir -p experiment/gsdc/data && ln -sfn "$(cd "$GSDC" && pwd)" experiment/gsdc/data/train
  python3 experiment/gsdc/analisar.py
  python3 experiment/compare_outputs.py "$BEFORE_G" experiment/gsdc
fi

step "Comparison with the committed results"
python3 experiment/compare_outputs.py "$BEFORE" experiment/out
