#!/usr/bin/env python3
"""Fare rule R14-R15 on real smartphone GNSS (Google Smartphone Decimeter Challenge 2022, train set).
Implements PROTOCOLO_2026-11-17.md exactly. Writes resultado_gsdc.json."""
import os, glob, json, itertools, math
import numpy as np, pandas as pd

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "train")
SEED = 20261117
LENGTHS_KM = (2, 5, 10)
TOLS = (0.03, 0.05, 0.10)
R = 6371.0088

def ecef_to_latlon(x, y, z):
    a, e2 = 6378137.0, 6.69437999014e-3
    b = a * math.sqrt(1 - e2); ep2 = (a * a - b * b) / (b * b)
    p = np.hypot(x, y); th = np.arctan2(z * a, p * b)
    lat = np.arctan2(z + ep2 * b * np.sin(th) ** 3, p - e2 * a * np.cos(th) ** 3)
    return np.degrees(lat), np.degrees(np.arctan2(y, x))

def hav(lat1, lon1, lat2, lon2):
    r = math.pi / 180
    dl, dn = (lat2 - lat1) * r, (lon2 - lon1) * r
    x = np.sin(dl / 2) ** 2 + np.cos(lat1 * r) * np.cos(lat2 * r) * np.sin(dn / 2) ** 2
    return 2 * R * np.arcsin(np.sqrt(x))  # km

def phone_track(path):
    d = pd.read_csv(path, usecols=["utcTimeMillis", "WlsPositionXEcefMeters", "WlsPositionYEcefMeters", "WlsPositionZEcefMeters"])
    d = d.dropna().drop_duplicates("utcTimeMillis").sort_values("utcTimeMillis")
    d = d[(d.WlsPositionXEcefMeters != 0)]
    lat, lon = ecef_to_latlon(d.WlsPositionXEcefMeters.values, d.WlsPositionYEcefMeters.values, d.WlsPositionZEcefMeters.values)
    return d.utcTimeMillis.values.astype(np.int64), lat, lon

def client_distance(t, lat, lon, t0, t1):
    """Same filter as the client (index.html): drop jumps > 55 m/s; only add steps > 5 m."""
    m = (t >= t0) & (t <= t1)
    t, lat, lon = t[m], lat[m], lon[m]
    if len(t) < 2: return None
    km = 0.0; lt, la, lo = t[0], lat[0], lon[0]
    for i in range(1, len(t)):
        dkm = hav(la, lo, lat[i], lon[i]); dt = (t[i] - lt) / 1000
        if dt <= 0 or dkm * 1000 / dt > 55: continue
        if dkm * 1000 < 5: continue
        km += dkm; lt, la, lo = t[i], lat[i], lon[i]
    return km

def reference(path):
    g = pd.read_csv(path, usecols=["LatitudeDegrees", "LongitudeDegrees", "UnixTimeMillis"]).dropna().sort_values("UnixTimeMillis")
    t = g.UnixTimeMillis.values.astype(np.int64); la = g.LatitudeDegrees.values; lo = g.LongitudeDegrees.values
    cum = np.concatenate([[0], np.cumsum(hav(la[:-1], lo[:-1], la[1:], lo[1:]))])
    return t, cum

rng = np.random.default_rng(SEED)
rows = []
drives = sorted(os.listdir(BASE))
for dr in drives:
    phones = sorted(p for p in os.listdir(os.path.join(BASE, dr)) if os.path.exists(os.path.join(BASE, dr, p, "device_gnss.csv")) and os.path.exists(os.path.join(BASE, dr, p, "ground_truth.csv")))
    if len(phones) < 2: continue
    rt, rcum = reference(os.path.join(BASE, dr, phones[0], "ground_truth.csv"))
    tracks = {p: phone_track(os.path.join(BASE, dr, p, "device_gnss.csv")) for p in phones}
    for L in LENGTHS_KM:
        n = int(rcum[-1] // L)
        for k in range(n):
            s0, s1 = k * L, (k + 1) * L
            f = rng.uniform(0.5, 1.0)
            t0 = int(np.interp(s0, rcum, rt)); tdrop = int(np.interp(s0 + f * L, rcum, rt))
            dref = f * L
            dist = {}
            for p in phones:
                tt = tracks[p][0]
                if len(tt) == 0 or tt[0] > t0 + 5000 or tt[-1] < tdrop - 5000: continue
                v = client_distance(*tracks[p], t0, tdrop)
                if v is not None: dist[p] = v
            for a, b in itertools.combinations(sorted(dist), 2):
                rows.append(dict(drive=dr, L=L, k=k, f=f, D=L, dref=dref, pa=a, pb=b, da=dist[a], db=dist[b],
                                 same_model=a == b or a.rstrip("XL") == b.rstrip("XL")))

df = pd.DataFrame(rows)
df["reldiff"] = (df.da - df.db).abs() / ((df.da + df.db) / 2)
df["err_a"] = (df.da - df.dref).abs() / df.dref

def boot(sub, fn, B=1000):
    ds = sub.drive.unique(); g = {d: sub[sub.drive == d] for d in ds}; vals = []
    r = np.random.default_rng(SEED)
    for _ in range(B):
        pick = r.choice(ds, len(ds)); s = pd.concat([g[d] for d in pick]); vals.append(fn(s))
    return [round(float(np.percentile(vals, 2.5)), 4), round(float(np.percentile(vals, 97.5)), 4)]

out = dict(drives=int(df.drive.nunique()), pairs=int(len(df[["drive", "pa", "pb"]].drop_duplicates())), segments={}, by_length={})
for L, s in df.groupby("L"):
    rec = dict(n=len(s), drives=int(s.drive.nunique()),
               reldiff_median=round(float(s.reldiff.median()), 4), reldiff_p95=round(float(s.reldiff.quantile(.95)), 4), reldiff_max=round(float(s.reldiff.max()), 4),
               err_vs_ref_median=round(float(s.err_a.median()), 4), err_vs_ref_p95=round(float(s.err_a.quantile(.95)), 4))
    for tol in TOLS:
        fd = lambda x, tol=tol: float(((x.da - x.db).abs() > tol * x.D).mean())
        det = lambda x, tol=tol: float(((x.D - x.da).abs() > tol * x.D).mean())   # driver claims the full trip
        rec[f"false_dispute_{int(tol*100)}"] = round(fd(s), 4)
        rec[f"detection_{int(tol*100)}"] = round(det(s), 4)
        if tol == 0.05:
            rec["false_dispute_5_ci95"] = boot(s, fd); rec["detection_5_ci95"] = boot(s, det)
    for sm, ss in s.groupby("same_model"):
        rec["false_dispute_5_" + ("same_model" if sm else "different_model")] = round(float(((ss.da - ss.db).abs() > .05 * ss.D).mean()), 4)
    out["by_length"][str(L)] = rec

fails = any(out["by_length"][k]["false_dispute_5"] > 0.05 for k in out["by_length"])
out["naive_rule_fails"] = bool(fails)
if fails:   # pre-registered correction: tolerance = max(5% of D, X metres), X chosen on half A, reported on half B
    ds = np.array(sorted(df.drive.unique())); r = np.random.default_rng(SEED); r.shuffle(ds)
    A, Bset = set(ds[: len(ds) // 2]), set(ds[len(ds) // 2:])
    a, b = df[df.drive.isin(A)], df[df.drive.isin(Bset)]
    chosen = None
    for X in (50, 100, 200, 300):
        tolkm = np.maximum(0.05 * a.D, X / 1000)
        if all(((g.da - g.db).abs() > np.maximum(0.05 * g.D, X / 1000)).mean() <= 0.05 for _, g in a.groupby("L")):
            chosen = X; break
    corr = dict(chosen_X_m=chosen, half_A_drives=len(A), half_B_drives=len(Bset), by_length={})
    if chosen:
        for L, g in b.groupby("L"):
            thr = np.maximum(0.05 * g.D, chosen / 1000)
            corr["by_length"][str(L)] = dict(n=len(g), false_dispute=round(float(((g.da - g.db).abs() > thr).mean()), 4),
                                            detection=round(float(((g.D - g.da).abs() > thr).mean()), 4))
    out["correction"] = corr
df.to_csv(os.path.join(os.path.dirname(BASE), "..", "segmentos_gsdc.csv"), index=False)
json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "resultado_gsdc.json"), "w"), indent=2)
print(json.dumps(out, indent=1))
