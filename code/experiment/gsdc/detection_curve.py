"""Fare rule on real GNSS logs: detection as a function of how much the driver's record is inflated,
and of where the passenger got off (full-trip claims). Reads segmentos_gsdc.csv written by analisar.py
(one row per honest trip and phone pair: booked distance D, phone distances da and db, travelled fraction f).
A claim is disputed when |claim - other phone| > tol * D (R15). Usage: python3 detection_curve.py [csv]"""
import json, os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
df = pd.read_csv(sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "segmentos_gsdc.csv"))
TOLS = (0.03, 0.05, 0.10)
INFL = (0.01, 0.02, 0.03, 0.05, 0.075, 0.10, 0.15, 0.20, 0.30, 0.50)
out = dict(n=len(df), drives=int(df.drive.nunique()), inflation={}, dropoff={})
for tol in TOLS:
    row = {}
    for x in INFL:   # driver's phone (db) inflated by x, passenger's phone (da) honest; both orders pooled
        a = ((df.db * (1 + x) - df.da).abs() > tol * df.D).mean()
        b = ((df.da * (1 + x) - df.db).abs() > tol * df.D).mean()
        row[f"{x:.3f}"] = round(float((a + b) / 2), 4)
    row["false_dispute"] = round(float(((df.da - df.db).abs() > tol * df.D).mean()), 4)
    out["inflation"][f"{tol:.2f}"] = row
bins = [0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
df["fbin"] = pd.cut(df.f, bins, include_lowest=True)
for tol in TOLS:   # driver claims the booked distance D; passenger's phone recorded the travelled part
    g = df.groupby("fbin", observed=True).apply(lambda s: float(((s.D - s.da).abs() > tol * s.D).mean()), include_groups=False)
    out["dropoff"][f"{tol:.2f}"] = {f"{iv.left:.1f}-{iv.right:.1f}": round(v, 4) for iv, v in g.items()}
json.dump(out, open(os.path.join(HERE, "detection_curve.json"), "w"), indent=2)
print(json.dumps(out, indent=1))
