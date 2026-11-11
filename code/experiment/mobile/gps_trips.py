#!/usr/bin/env python3
"""Real trips recorded by GPS on two phones (client tab Check, "Record a real trip").
Each phone posts one file with kind "gps_trip" to out/mobile_runs/: trip_code, role (passenger or
driver), km measured on that phone, odometer_km typed at the end (optional), fixes and discarded fixes.
This script pairs the two roles by trip code and reports, per trip:
  - the relative difference between the phones: |km_passenger - km_driver| / mean;
  - the relative difference of each phone to the car's odometer, when it was typed;
  - the fare rule outcome: R14 (settled) if the records agree within 5% of the trip, else R15 (disputed),
    with the trip taken as the odometer distance if typed, otherwise the mean of the two records.
Trips recorded on one phone only (one role) are reported apart, against the odometer: the relative
difference |km - odometer| / odometer, and the R14/R15 outcome that the same error on both phones would
give in the worst case (errors in opposite directions double the gap between the records). Writes out/gps_trips.json and prints the
sentence for Sect. 5.1 of the paper.
  python3 gps_trips.py [folder with the result files]   (default: ../out/mobile_runs)"""
import glob, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "out", "mobile_runs")
OUT = os.path.join(HERE, "..", "out", "gps_trips.json")
TOL = 0.05

runs = []
for f in sorted(glob.glob(os.path.join(SRC, "*.json"))):
    try:
        d = json.load(open(f))
    except Exception:
        continue
    if d.get("kind") == "gps_trip":
        d["file"] = os.path.basename(f)
        runs.append(d)

trips, incomplete = {}, []
for r in runs:   # the last file of each role wins (a phone may have pressed Stop twice)
    trips.setdefault(r["trip_code"].strip().upper(), {})[r["role"]] = r

rows = []
for code, t in sorted(trips.items()):
    if not {"passenger", "driver"} <= t.keys():
        incomplete.append(code)
        continue
    kp, kd = t["passenger"]["km"], t["driver"]["km"]
    odo = t["passenger"].get("odometer_km") or t["driver"].get("odometer_km")
    mean = (kp + kd) / 2
    trip = odo if odo else mean
    agree = abs(kp - kd) <= TOL * trip
    rows.append(dict(trip_code=code, km_passenger=kp, km_driver=kd, odometer_km=odo,
                     diff_between_phones_pct=round(100 * abs(kp - kd) / mean, 2) if mean else None,
                     diff_passenger_vs_odometer_pct=round(100 * abs(kp - odo) / odo, 2) if odo else None,
                     diff_driver_vs_odometer_pct=round(100 * abs(kd - odo) / odo, 2) if odo else None,
                     rule="R14" if agree else "R15",
                     fixes=[t["passenger"]["fixes"], t["driver"]["fixes"]],
                     discarded=[t["passenger"]["discarded"], t["driver"]["discarded"]],
                     minutes=max(t["passenger"]["minutes"], t["driver"]["minutes"]),
                     files=[t["passenger"]["file"], t["driver"]["file"]]))

single = []
for code in incomplete:
    r = next(iter(trips[code].values()))
    odo = r.get("odometer_km")
    if odo:
        e = abs(r["km"] - odo) / odo
        single.append(dict(trip_code=code, role=r["role"], km=r["km"], odometer_km=odo, diff_vs_odometer_pct=round(100 * e, 2),
                           worst_case_rule="R14" if 2 * e <= TOL else "R15", fixes=r["fixes"], discarded=r["discarded"],
                           minutes=r["minutes"], file=r["file"]))
res = dict(tolerance=TOL, trips=rows, incomplete_trip_codes=incomplete, single_phone_trips=single)
json.dump(res, open(OUT, "w"), indent=2)
for r in rows:
    print(r)
if incomplete:
    print("Only one phone recorded:", incomplete)
if rows:
    rng = lambda xs: f"{min(xs):.1f}" if min(xs) == max(xs) else f"{min(xs):.1f}--{max(xs):.1f}"
    lengths = [r["odometer_km"] or (r["km_passenger"] + r["km_driver"]) / 2 for r in rows]
    between = [r["diff_between_phones_pct"] for r in rows]
    odo = [x for r in rows for x in (r["diff_passenger_vs_odometer_pct"], r["diff_driver_vs_odometer_pct"]) if x is not None]
    k = sum(r["rule"] == "R14" for r in rows)
    s = (f"In {len(rows)} real trips of {rng(lengths)}\\,km, the driver's and the passenger's phones recorded distances "
         f"that differed from each other by {rng(between)}\\%")
    s += f" and from the car's odometer by {rng(odo)}\\%" if odo else ""
    s += f"; R14 settled {k} of them and R15 flagged {len(rows) - k}."
    print("\nSentence for Sect. 5.1:\n" + s)
if single:
    errs = [t["diff_vs_odometer_pct"] for t in single]
    lens = [t["odometer_km"] for t in single]
    k = sum(t["worst_case_rule"] == "R14" for t in single)
    rng1 = lambda xs: f"{min(xs):.1f}" if min(xs) == max(xs) else f"{min(xs):.1f}--{max(xs):.1f}"
    print(f"\nSentence for Sect. 5.1 (one phone):\nIn {len(single)} real trips of {rng1(lens)}\\,km recorded by GPS on one phone, "
          f"the distance differed from the car's odometer by {rng1(errs)}\\%; even if two phones erred in opposite directions, "
          f"R14 would settle {k} of them and R15 would flag {len(single) - k}.")
