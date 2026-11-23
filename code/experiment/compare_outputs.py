"""Compares every JSON result in experiment/out with a saved copy taken before the run.
Usage: python3 compare_outputs.py <dir before> <dir after>
Timing fields (ms, time, latency, throughput, ...) are machine-dependent and are listed but not compared.
Exit code 1 if any non-timing value differs."""
import json, os, re, sys

TIMING = re.compile(r"(^|_)(ms|s|sec|seconds|time|times|latency|throughput|rps|qps|duration|elapsed|per_s|"
                    r"wall|cpu|load|p50|p95|p99|median_ms|mean_ms)($|_)|_ms$|ms_|time", re.I)

def walk(a, b, path, diffs, skipped):
    key = path.rsplit("/", 1)[-1]
    if TIMING.search(key):
        skipped.add(path); return
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b: diffs.append(f"{path}/{k}: key only in {'after' if k in b else 'before'}")
            else: walk(a[k], b[k], f"{path}/{k}", diffs, skipped)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b): diffs.append(f"{path}: length {len(a)} -> {len(b)}"); return
        for i, (x, y) in enumerate(zip(a, b)): walk(x, y, f"{path}[{i}]", diffs, skipped)
    elif isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        if abs(a - b) > 1e-9 * max(1.0, abs(a), abs(b)): diffs.append(f"{path}: {a} -> {b}")
    elif a != b:
        diffs.append(f"{path}: {str(a)[:60]!r} -> {str(b)[:60]!r}")

before, after = sys.argv[1], sys.argv[2]
bad = 0
for name in sorted(os.listdir(after)):
    if not name.endswith(".json") or not os.path.exists(os.path.join(before, name)): continue
    a = json.load(open(os.path.join(before, name))); b = json.load(open(os.path.join(after, name)))
    diffs, skipped = [], set()
    walk(a, b, name, diffs, skipped)
    status = "same" if not diffs else f"{len(diffs)} DIFFERENCES"
    print(f"{name:42s} {status}" + (f"  ({len(skipped)} timing fields not compared)" if skipped else ""))
    for d in diffs[:5]: print("    ", d)
    bad += bool(diffs)
print(f"\n{bad} file(s) with non-timing differences." if bad else "\nAll non-timing values reproduced exactly.")
sys.exit(1 if bad else 0)
