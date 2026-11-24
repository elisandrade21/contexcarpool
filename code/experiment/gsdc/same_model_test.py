"""Same-model vs different-model phone pairs: per-drive false-dispute rate at the 5% tolerance,
paired Wilcoxon signed-rank test over the drives that have both kinds of pair.
Input: segmentos_gsdc.csv written by analisar.py (one row per honest trip). Usage: python3 same_model_test.py [csv]"""
import json, os, sys
import pandas as pd
from scipy.stats import wilcoxon
HERE = os.path.dirname(os.path.abspath(__file__))
csv = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "segmentos_gsdc.csv")
d = pd.read_csv(csv); d["false_dispute"] = d.reldiff > 0.05
per_drive = d.groupby(["drive", "same_model"]).false_dispute.mean().unstack()
both = per_drive.dropna()
w = wilcoxon(both[True], both[False])  # exact two-sided test for n < 50 without ties
out = {"tolerance": 0.05, "drives": int(len(per_drive)), "drives_with_both_kinds": int(len(both)),
       "pooled_rate_same_model": float(d[d.same_model].false_dispute.mean()),
       "pooled_rate_different_model": float(d[~d.same_model].false_dispute.mean()),
       "wilcoxon_statistic": float(w.statistic), "wilcoxon_p": float(w.pvalue)}
json.dump(out, open(os.path.join(HERE, "same_model_test.json"), "w"), indent=2)
print(json.dumps(out, indent=2))
