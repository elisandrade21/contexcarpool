#!/usr/bin/env python3
"""Sensitivity of the settlement rule (R14-R15) to GPS error and tolerance, using the rule's reference
logic (identical to the SPARQL rules, checked on 1,977 trips in three engines). For each setting,
10,000 honest trips (both phones record the true distance with relative noise sigma plus an absolute
error of standard deviation abs_km, which weighs more on short trips) give
the false-dispute rate, and 10,000 trips in which the driver's phone claims the full trip give the
detection rate of overcharging, as a function of how early the passenger got off."""
import json, os
import numpy as np
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "out")
rng = np.random.default_rng(20261108)
N = 10000
res = []
# D: 300 km (long-distance carpool) and 7.6 km (median of the matched registry offers);
# rho: correlation between the two phones' relative errors (they travel in the same car).
for D in (300.0, 7.6):
 for a in (0.0, 0.05, 0.2):
  for rho in (0.0, 0.5):
    for sigma in (0.005, 0.01, 0.02, 0.03, 0.05):
      for tol in (0.02, 0.05, 0.10):
        frac = rng.uniform(0.5, 1.0, N); true = D * frac
        z1 = rng.normal(0, 1, N); z2 = rho * z1 + np.sqrt(1 - rho ** 2) * rng.normal(0, 1, N)
        kp = true * (1 + sigma * z1) + a * rng.normal(0, 1, N); kd = true * (1 + sigma * z2) + a * rng.normal(0, 1, N)
        false_disp = float(np.mean(np.abs(kp - kd) > tol * D))
        kd2 = np.full(N, D)                                  # driver claims the full trip
        detected = np.abs(kp - kd2) > tol * D
        overcharge = ~detected & (frac < 1)
        bias = float(np.max(np.abs((kp + kd) / 2 - true) / D))
        res.append(dict(trip_km=D, abs_error_sd_km=a, error_correlation=rho, gps_sigma=sigma, tolerance=tol, false_dispute_rate=round(false_disp, 4),
                        overcharge_detection_rate=round(float(np.mean(detected)), 4),
                        undetected_mean_extra_percent=round(100 * float(np.mean(((kp + kd2) / 2 - true)[overcharge] / D)), 2) if overcharge.any() else 0.0,
                        max_one_sided_shift_percent=round(100 * tol / 2, 2)))
json.dump(res, open(os.path.join(OUT, "settlement_sensitivity.json"), "w"), indent=1)
for r in res: print(r)
