#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Reproducible synthetic benchmark for the AINA-2027 paper
"Contextual Assistance for Users of Ridesharing Services".

WHY SYNTHETIC: real carpooling listings with the required schema (available
seats, booking modality, multi-country price/km) are not openly available
(BlaBlaCar's public API is license-gated, Search V2 deprecated). To make the
evaluation *reproducible* we generate a seeded synthetic dataset whose
parameters are plausible, illustrative assumptions (not estimates from
marketplace data), and run the SAME ontology-backed
pipeline described in the paper over it. Everything below is deterministic
(fixed seed) so any number in the paper can be regenerated with one command:

    python3 run_experiment.py

Outputs (in ./out): listings.csv, per_listing_scores.csv, results.json,
table2_descriptive.tex and the ABox/expected-inference files used by the Jena check.
"""

import json
import os
from collections import defaultdict

import numpy as np
import pandas as pd
from rdflib import Graph, Namespace, Literal, RDF, URIRef
from rdflib.namespace import XSD

SEED = 20260604
OUT = os.path.join(os.path.dirname(__file__), "out")
os.makedirs(OUT, exist_ok=True)

# --------------------------------------------------------------------------
# 1. Country calibration (synthetic but plausible; values are benchmark
#    parameters, NOT empirical measurements). Country-relative cost handles
#    mixed currencies, which is itself a justification for the design.
# --------------------------------------------------------------------------
N_PER_COUNTRY = 1000
COUNTRIES = {
    #               cur    dist_med  dist_sig  ppk_base ppk_sig  seats p(d=1..4)            auto_rate
    "Brazil":   dict(cur="BRL", dmed=470, dsig=0.45, ppk=0.34, psig=0.30, seats=[0.16, 0.30, 0.39, 0.15], auto=0.65),
    "France":   dict(cur="EUR", dmed=300, dsig=0.40, ppk=0.071, psig=0.28, seats=[0.22, 0.36, 0.32, 0.10], auto=0.58),
    "Italy":    dict(cur="EUR", dmed=285, dsig=0.42, ppk=0.078, psig=0.30, seats=[0.24, 0.36, 0.30, 0.10], auto=0.74),
    "Portugal": dict(cur="EUR", dmed=312, dsig=0.40, ppk=0.070, psig=0.27, seats=[0.18, 0.33, 0.34, 0.15], auto=0.61),
    "Ukraine":  dict(cur="UAH", dmed=410, dsig=0.44, ppk=2.10, psig=0.32, seats=[0.10, 0.24, 0.40, 0.26], auto=0.48),
}

rng = np.random.default_rng(SEED)


def gen_listings():
    rows = []
    for country, p in COUNTRIES.items():
        n = N_PER_COUNTRY
        # distance: lognormal around the country median
        dist = rng.lognormal(mean=np.log(p["dmed"]), sigma=p["dsig"], size=n)
        dist = np.clip(dist, 30, 2500)
        # price per km: lognormal around country base (within-country spread)
        ppk = rng.lognormal(mean=np.log(p["ppk"]), sigma=p["psig"], size=n)
        price = ppk * dist
        # available passenger seats offered by the driver: 1..4 (FIX: "available
        # seats", not "rear seats" -> d>=4 is now reachable for a 5-seat car).
        seats = rng.choice([1, 2, 3, 4], size=n, p=p["seats"])
        # booking modality: 1 = automatic acceptance, 0 = manual approval
        auto = (rng.random(n) < p["auto"]).astype(int)
        for i in range(n):
            rows.append(dict(
                trip_id=f"{country[:2].upper()}-{i:04d}",
                country=country, currency=p["cur"],
                distance_km=round(float(dist[i]), 1),
                price=round(float(price[i]), 2),
                price_per_km=round(float(ppk[i]), 4),
                seats_available=int(seats[i]),
                booking_auto=int(auto[i]),
            ))
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# 2. Ontology layer (rdflib): build Travel individuals and MATERIALIZE the
#    comfort class via Jena-style forward-chaining rules (Table 1). This is the
#    genuine "OWL context model + reasoning rules" step, done in code.
# --------------------------------------------------------------------------
WM = Namespace("http://example.org/ridesharing#")

COMFORT_RULES = [  # (rule id, predicate on available seats d, class, numeric f_C)
    ("R1", lambda d: d >= 4, "VeryComfortable", 10.0),
    ("R2", lambda d: d == 3, "Comfortable",      7.5),
    ("R3", lambda d: d == 2, "Bearable",         5.0),
    ("R4", lambda d: d <= 1, "Uncomfortable",    2.5),
]


def materialize_comfort(df):
    """Build an RDF graph and forward-chain the comfort rules over it."""
    g = Graph()
    g.bind("wm", WM)
    onto = os.path.join(os.path.dirname(__file__), "..", "ontology", "ridesharing.ttl")
    if os.path.exists(onto):
        g.parse(onto, format="turtle")        # load the OWL context model (TBox)
    for _, r in df.iterrows():
        t = URIRef(WM[f"trip_{r.trip_id}"])
        g.add((t, RDF.type, WM.Travel))
        g.add((t, WM.hasSeatsAvailable, Literal(int(r.seats_available), datatype=XSD.integer)))
    # forward chaining: for each Travel, fire exactly one comfort rule
    fired = {}
    for t, _, lit in g.triples((None, WM.hasSeatsAvailable, None)):
        d = int(lit)
        for rid, cond, cls, fc in COMFORT_RULES:
            if cond(d):
                g.add((t, WM.hasComfortLevel, WM[cls]))   # materialized assertion
                fired[str(t).rsplit("trip_", 1)[1]] = (rid, cls, fc)
                break
    comfort = df["trip_id"].map(lambda x: fired[x])
    df = df.copy()
    df["comfort_rule"] = comfort.map(lambda c: c[0])
    df["comfort_class"] = comfort.map(lambda c: c[1])
    df["f_C"] = comfort.map(lambda c: c[2])
    return df, g


# --------------------------------------------------------------------------
# 3. Scoring layer: cost (country-relative), booking, composite.
# --------------------------------------------------------------------------
def add_scores(df):
    df = df.copy()
    # Cost: WITHIN-COUNTRY percentile of (lower price/km is better) -> [0,10].
    # By construction the per-country mean is ~5.0: cost is a fair *within-market*
    # signal and does NOT confound cross-country comparison (this is the point of
    # country-relative normalization, and it transparently handles mixed
    # currencies BRL/EUR/UAH).
    def cost_score(s):
        # rank ascending price/km; cheapest -> rank near 0 -> highest score
        r = s.rank(pct=True)          # in (0,1], higher = more expensive
        return (1.0 - r) * 10.0
    df["f_K"] = df.groupby("country")["price_per_km"].transform(cost_score)
    # Booking: automatic acceptance reduces coordination friction.
    df["f_B"] = np.where(df["booking_auto"] == 1, 10.0, 2.5)
    return df


def composite(df, wC=0.4, wK=0.4, wB=0.2):
    return wC * df["f_C"] + wK * df["f_K"] + wB * df["f_B"]


# --------------------------------------------------------------------------
# 4. Run pipeline
# --------------------------------------------------------------------------
listings = gen_listings()
listings, graph = materialize_comfort(listings)
listings = add_scores(listings)
listings["S"] = composite(listings)
listings.to_csv(os.path.join(OUT, "listings.csv"), index=False)
listings[["trip_id", "country", "f_C", "f_K", "f_B", "S",
          "comfort_class", "comfort_rule"]].to_csv(
    os.path.join(OUT, "per_listing_scores.csv"), index=False)

results = {"seed": SEED, "n_per_country": N_PER_COUNTRY,
           "n_total": int(len(listings)), "countries": list(COUNTRIES)}

# ---- Table 2: descriptive statistics --------------------------------------
desc = []
for c in COUNTRIES:
    sub = listings[listings.country == c]
    desc.append(dict(country=c, trips=int(len(sub)),
                     median_dist=round(float(sub.distance_km.median()), 0),
                     median_price=round(float(sub.price.median()), 1),
                     currency=COUNTRIES[c]["cur"],
                     auto_pct=round(float(sub.booking_auto.mean() * 100), 1)))
results["table2"] = desc

# ---- Table 3: per-dimension means + composite (exact arithmetic) ----------
dim = []
for c in COUNTRIES:
    sub = listings[listings.country == c]
    # Round dimension means to 2 dp, THEN compute the composite from the rounded
    # values so the printed table is internally self-consistent (a reviewer
    # recomputing S from the columns gets exactly the printed S).
    fCr = round(float(sub.f_C.mean()), 2)
    fKr = round(float(sub.f_K.mean()), 2)
    fBr = round(float(sub.f_B.mean()), 2)
    S = round(0.4 * fCr + 0.4 * fKr + 0.2 * fBr, 2)
    dim.append(dict(country=c, f_C=fCr, f_K=fKr, f_B=fBr, S=S,
                    S_meanofcol=round(float(sub.S.mean()), 2)))
dim.sort(key=lambda x: -x["S"])
results["per_market_means_not_compared"] = dim

# ---- Figure 3: composite normalized to best = 100% ------------------------
best = max(d["S"] for d in dim)
fig3 = [dict(country=d["country"], S=d["S"],
             pct=round(d["S"] / best * 100, 1)) for d in dim]
# (cross-market comparison removed from the paper: means only reflect the generator)

# ---- Sensitivity analysis: perturb weights by +/-0.1 (renormalize) --------
from itertools import product
from scipy.stats import kendalltau

base_rank = {}
for c in COUNTRIES:
    sub = listings[listings.country == c].copy()
    base_rank[c] = sub.set_index("trip_id")["S"].rank(ascending=False)

perturb = []
grid = [-0.1, 0.0, 0.1]
taus, top10 = [], []
for dC, dK, dB in product(grid, repeat=3):
    w = np.array([0.4 + dC, 0.4 + dK, 0.2 + dB])
    if (w <= 0).any():
        continue
    w = w / w.sum()
    if abs(w[0] - 0.4) < 1e-9 and abs(w[1] - 0.4) < 1e-9:
        continue  # skip the base config
    for c in COUNTRIES:
        sub = listings[listings.country == c].copy()
        s2 = w[0] * sub.f_C + w[1] * sub.f_K + w[2] * sub.f_B
        r2 = s2.rank(ascending=False).values
        r1 = base_rank[c].loc[sub.trip_id].values
        tau = kendalltau(r1, r2).statistic
        taus.append(tau)
        # top-10 overlap within this country/search
        top_base = set(base_rank[c].sort_values().index[:10])
        sub2 = sub.assign(s2=s2.values)
        top_new = set(sub2.sort_values("s2", ascending=False).trip_id[:10])
        top10.append(len(top_base & top_new) / 10.0)
results["sensitivity"] = dict(
    n_perturbations=len(set([p for p in product(grid, repeat=3)])) - 1,
    mean_kendall_tau=round(float(np.mean(taus)), 3),
    min_kendall_tau=round(float(np.min(taus)), 3),
    mean_top10_overlap=round(float(np.mean(top10)), 3),
    min_top10_overlap=round(float(np.min(top10)), 3),
)

# ---- Baseline contrast: composite vs single-dimension rankings ------------
from scipy.stats import spearmanr
sp = {}
for c in COUNTRIES:
    sub = listings[listings.country == c]
    sp[c] = dict(
        vs_cost_only=round(float(spearmanr(sub.S, sub.f_K).statistic), 3),
        vs_comfort_only=round(float(spearmanr(sub.S, sub.f_C).statistic), 3),
    )
results["baseline_spearman"] = sp
# Decomposition insight: which country leads each dimension
_unused_leaders = dict(
    comfort=max(dim, key=lambda d: d["f_C"])["country"],
    booking=max(dim, key=lambda d: d["f_B"])["country"],
    composite=max(dim, key=lambda d: d["S"])["country"],
    cost_note="country-relative; per-country mean ~5.0 by construction (no cross-country leader by design)",
)

# ---- Qualitative example: top-3 offers in one search (France) -------------
ex = listings[listings.country == "France"].sort_values("S", ascending=False).head(3)
results["example_france_top3"] = [
    dict(trip_id=r.trip_id, S=round(r.S, 2), comfort=r.comfort_class,
         f_K=round(r.f_K, 1), f_B=round(r.f_B, 1),
         seats=int(r.seats_available), auto=int(r.booking_auto),
         price_per_km=r.price_per_km)
    for _, r in ex.iterrows()
]

# --------------------------------------------------------------------------
# 5. Emit LaTeX fragments + pgfplots data
# --------------------------------------------------------------------------
with open(os.path.join(OUT, "table2_descriptive.tex"), "w") as f:
    for d in results["table2"]:
        f.write(f"{d['country']} & {d['trips']} & {int(d['median_dist'])} & "
                f"{d['median_price']:.0f} ({d['currency']}) & {d['auto_pct']:.0f} \\\\\n")

with open(os.path.join(OUT, "results.json"), "w") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)

# --------------------------------------------------------------------------
# 6. Console summary
# --------------------------------------------------------------------------
print(f"N = {results['n_total']} listings ({N_PER_COUNTRY}/country), seed={SEED}")
print("\nTable 2 (descriptive):")
print(pd.DataFrame(results["table2"]).to_string(index=False))
print("\nSensitivity (weights +/-0.1):", results["sensitivity"])
print("\nBaseline Spearman (composite vs single dim):")
print(pd.DataFrame(results["baseline_spearman"]).T.to_string())
print("\nExample France top-3:")
for e in results["example_france_top3"]:
    print(" ", e)
print("\nWrote outputs to", OUT)


# ==========================================================================
# 7. AINA-2027 extensions (reviewer-driven). Everything below runs AFTER the
#    original pipeline and never touches the global `rng`, so all numbers
#    above are unchanged. Separate seeds are used where randomness is needed.
# ==========================================================================
import time
import platform

ext = {}

# ---- 7a. Booking-only contrast (completes the single-dimension baselines) --
for c in COUNTRIES:
    sub = listings[listings.country == c]
    results["baseline_spearman"][c]["vs_booking_only"] = round(
        float(spearmanr(sub.S, sub.f_B).statistic), 3)

# ---- 7b. Trade-off rules R5-R7 (cost vs booking convenience) --------------
TRADEOFF_RULES = [  # (rule id, predicate on (auto, f_K), class)
    ("R5", lambda a, k: a == 1 and k >= 7.5, "InstantBargain"),
    ("R6", lambda a, k: a == 0 and k >= 7.5, "ApprovalBargain"),
    ("R7", lambda a, k: a == 1 and k < 2.5, "ConveniencePremium"),
    ("R8", lambda a, k: a == 0 and k < 2.5, "ApprovalPremium"),
]
PHRASE = {
    "InstantBargain": "it is among the cheapest quarter of the search and books instantly",
    "ApprovalBargain": "it is among the cheapest quarter of the search but requires driver approval",
    "ConveniencePremium": "it books instantly but is among the most expensive quarter of the search",
    "ApprovalPremium": "it requires driver approval and is among the most expensive quarter of the search",
}


PROV = Namespace("http://www.w3.org/ns/prov#")


def record_firing(g, t, rid, cls):
    """Qualified PROV-O record of one rule firing; node IRIs follow ontology/rules.ru."""
    f, q, e = (URIRef(f"{t}-{rid}-{x}") for x in ("firing", "association", "fact"))
    for c in (WM.RuleFiring, PROV.Activity):
        g.add((f, RDF.type, c))
    g.add((f, PROV.used, t)); g.add((f, PROV.qualifiedAssociation, q))
    g.add((q, RDF.type, PROV.Association)); g.add((q, PROV.agent, WM.Reasoner)); g.add((q, PROV.hadPlan, WM[rid]))
    for c in (WM.InferredFact, PROV.Entity):
        g.add((e, RDF.type, c))
    g.add((e, PROV.wasGeneratedBy, f)); g.add((e, PROV.wasDerivedFrom, t)); g.add((e, RDF.value, WM[cls]))


def rank_search(df, wC=0.4, wK=0.4, wB=0.2, check_trace=False):
    """End-to-end ClassifyTrips for one search result set: OWL individuals,
    forward chaining of R1-R7, scoring, ranking and textual rationales."""
    g = Graph()
    df = df.copy()
    # CostPercentiles over the listing set of the search
    r = df["price_per_km"].rank(pct=True)
    df["f_K"] = (1.0 - r) * 10.0
    df["f_B"] = np.where(df["booking_auto"] == 1, 10.0, 2.5)
    rows = []
    for rec in df.itertuples(index=False):
        t = URIRef(WM[f"trip_{rec.trip_id}"])
        g.add((t, RDF.type, WM.Travel))
        g.add((t, WM.hasSeatsAvailable, Literal(int(rec.seats_available), datatype=XSD.integer)))
        mode = "auto" if rec.booking_auto == 1 else "manual"
        g.add((t, WM.hasBookingMode, Literal(mode)))
        g.add((t, WM.hasCostScore, Literal(float(rec.f_K), datatype=XSD.decimal)))
    # forward chaining (single pass suffices: rule bodies use only asserted facts)
    for t in g.subjects(RDF.type, WM.Travel):
        d = int(g.value(t, WM.hasSeatsAvailable))
        a = 1 if str(g.value(t, WM.hasBookingMode)) == "auto" else 0
        k = float(g.value(t, WM.hasCostScore))
        for rid, cond, cls, fc in COMFORT_RULES:
            if cond(d):
                g.add((t, WM.hasComfortLevel, WM[cls]))
                record_firing(g, t, rid, cls)
                break
        for rid, cond, cls in TRADEOFF_RULES:
            if cond(a, k):
                g.add((t, WM.hasTradeOff, WM[cls]))
                record_firing(g, t, rid, cls)
                break
    FC = {cls: fc for _, _, cls, fc in COMFORT_RULES}
    for rec in df.itertuples(index=False):
        t = URIRef(WM[f"trip_{rec.trip_id}"])
        cls = str(g.value(t, WM.hasComfortLevel)).rsplit("#", 1)[1]
        fact = next(e for e in g.subjects(PROV.wasDerivedFrom, t)
                    if (e, RDF.value, WM[cls]) in g)
        assoc = g.value(g.value(fact, PROV.wasGeneratedBy), PROV.qualifiedAssociation)
        rid = str(g.value(assoc, PROV.hadPlan)).rsplit("#", 1)[1]
        f_C = FC[cls]
        S = wC * f_C + wK * rec.f_K + wB * rec.f_B
        to = g.value(t, WM.hasTradeOff)
        to = str(to).rsplit("#", 1)[1] if to is not None else None
        rows.append((rec.trip_id, S, f_C, rec.f_K, rec.f_B, cls, rid, to))
    out = pd.DataFrame(rows, columns=["trip_id", "S", "f_C", "f_K", "f_B",
                                      "comfort_class", "comfort_rule", "tradeoff"])
    out = out.sort_values("S", ascending=False).reset_index(drop=True)
    expl = []
    for k_, rec in enumerate(out.itertuples(index=False), start=1):
        pct = int(round(100 - rec.f_K * 10))  # position in the price/km distribution
        txt = (f"ranked {k_} because rule {rec.comfort_rule} inferred {rec.comfort_class} "
               f"from the available seats, the price per km lies at percentile {pct} "
               f"of the search, and booking is "
               f"{'automatic' if rec.f_B == 10.0 else 'manual'}")
        if isinstance(rec.tradeoff, str):
            txt += f"; {PHRASE[rec.tradeoff]}"
        expl.append(txt)
        if check_trace:  # every clause must be backed by a triple in the graph
            t = URIRef(WM[f"trip_{rec.trip_id}"])
            assert (t, WM.hasComfortLevel, WM[rec.comfort_class]) in g
            f = URIRef(f"{t}-{rec.comfort_rule}-firing")
            e = URIRef(f"{t}-{rec.comfort_rule}-fact")
            assert (f, PROV.used, t) in g and (e, PROV.wasGeneratedBy, f) in g
            assert (e, RDF.value, WM[rec.comfort_class]) in g
            q = g.value(f, PROV.qualifiedAssociation)
            assert (q, PROV.hadPlan, WM[rec.comfort_rule]) in g
            assert abs(float(g.value(t, WM.hasCostScore)) - rec.f_K) < 1e-9
            if isinstance(rec.tradeoff, str):
                assert (t, WM.hasTradeOff, WM[rec.tradeoff]) in g
    out["rationale"] = expl
    return out


# Equivalence + trace check on the full benchmark (market-level searches)
trace_ok, tradeoff_counts, n_checked = True, defaultdict(int), 0
for c in COUNTRIES:
    sub = listings[listings.country == c]
    ranked = rank_search(sub, check_trace=True)
    n_checked += len(ranked)
    ref = sub.set_index("trip_id")["S"]
    assert np.allclose(ranked.set_index("trip_id")["S"].loc[ref.index].values, ref.values)
    for v in ranked["tradeoff"]:
        tradeoff_counts[v if isinstance(v, str) else "none"] += 1
ext["trace_check"] = dict(listings_checked=n_checked, all_clauses_backed_by_triples=trace_ok,
                          scores_match_batch_pipeline=True)
ext["tradeoff_coverage_pct"] = {k: round(100 * v / n_checked, 1) for k, v in sorted(tradeoff_counts.items())}
ex_fr = rank_search(listings[listings.country == "France"])
ext["example_france_rationales"] = ex_fr.head(3)["rationale"].tolist()
ap = ex_fr[ex_fr.tradeoff == "ApprovalBargain"].head(1)
ext["example_approval_bargain"] = ap[["trip_id", "S", "rationale"]].to_dict("records")

# ---- 7c. Latency / throughput per search ----------------------------------
lat_rng = np.random.default_rng(SEED + 1)
fr = listings[listings.country == "France"]
latency = {}
for n, reps in [(20, 200), (100, 100), (1000, 20)]:
    times = []
    for _ in range(reps):
        idx = lat_rng.choice(len(fr), size=n, replace=False)
        sub = fr.iloc[idx]
        t0 = time.perf_counter()
        rank_search(sub)
        times.append((time.perf_counter() - t0) * 1000.0)
    times = np.array(times)
    latency[str(n)] = dict(reps=reps, median_ms=round(float(np.median(times)), 1),
                           p95_ms=round(float(np.percentile(times, 95)), 1),
                           listings_per_s=int(n / (np.median(times) / 1000.0)))
ext["latency_python_reference_not_reported"] = latency
ext["platform"] = dict(python=platform.python_version(), machine=platform.machine(),
                       processor=platform.processor())

# ---- 7d. Robustness to calibration drift ----------------------------------
# The 2020 calibration may not reflect today's market. We re-draw the whole
# benchmark from K perturbed generators and check whether the two empirical
# findings (non-redundancy, weight stability) survive.
K_DRIFT = 20
drift_rng = np.random.default_rng(SEED + 2)


def gen_perturbed(r):
    rows = []
    for country, p in COUNTRIES.items():
        n = N_PER_COUNTRY
        dmed = p["dmed"] * r.uniform(0.8, 1.2)
        psig = p["psig"] * r.uniform(0.7, 1.3)
        seats_p = r.dirichlet(np.array(p["seats"]) * 20)
        auto_p = float(np.clip(p["auto"] + r.uniform(-0.15, 0.15), 0.05, 0.95))
        dist = np.clip(r.lognormal(np.log(dmed), p["dsig"], n), 30, 2500)
        ppk = r.lognormal(np.log(p["ppk"]), psig, n)
        seats = r.choice([1, 2, 3, 4], size=n, p=seats_p)
        auto = (r.random(n) < auto_p).astype(int)
        for i in range(n):
            rows.append(dict(trip_id=f"{country[:2].upper()}-{i:04d}", country=country,
                             price_per_km=float(ppk[i]), seats_available=int(seats[i]),
                             booking_auto=int(auto[i])))
    df = pd.DataFrame(rows)
    fc = {1: 2.5, 2: 5.0, 3: 7.5, 4: 10.0}
    df["f_C"] = df.seats_available.map(fc)
    return add_scores(df)


drift = dict(sp_cost=[], sp_comfort=[], sp_booking=[], tau_mean=[], tau_min=[], top10_mean=[])
for _ in range(K_DRIFT):
    df = gen_perturbed(drift_rng)
    df["S"] = composite(df)
    taus_k, top_k = [], []
    for c in COUNTRIES:
        sub = df[df.country == c].set_index("trip_id")
        drift["sp_cost"].append(spearmanr(sub.S, sub.f_K).statistic)
        drift["sp_comfort"].append(spearmanr(sub.S, sub.f_C).statistic)
        drift["sp_booking"].append(spearmanr(sub.S, sub.f_B).statistic)
        r1 = sub.S.rank(ascending=False)
        top_base = set(r1.sort_values().index[:10])
        for dC, dK, dB in product(grid, repeat=3):
            w = np.array([0.4 + dC, 0.4 + dK, 0.2 + dB])
            if (w <= 0).any():
                continue
            w = w / w.sum()
            if abs(w[0] - 0.4) < 1e-9 and abs(w[1] - 0.4) < 1e-9:
                continue
            s2 = w[0] * sub.f_C + w[1] * sub.f_K + w[2] * sub.f_B
            taus_k.append(kendalltau(r1.values, s2.rank(ascending=False).values).statistic)
            top_k.append(len(top_base & set(s2.sort_values(ascending=False).index[:10])) / 10)
    drift["tau_mean"].append(np.mean(taus_k))
    drift["tau_min"].append(np.min(taus_k))
    drift["top10_mean"].append(np.mean(top_k))
ext["calibration_drift"] = dict(
    n_generators=K_DRIFT,
    spearman_vs_cost=[round(float(np.min(drift["sp_cost"])), 2), round(float(np.max(drift["sp_cost"])), 2)],
    spearman_vs_comfort=[round(float(np.min(drift["sp_comfort"])), 2), round(float(np.max(drift["sp_comfort"])), 2)],
    spearman_vs_booking=[round(float(np.min(drift["sp_booking"])), 2), round(float(np.max(drift["sp_booking"])), 2)],
    mean_tau_range=[round(float(np.min(drift["tau_mean"])), 3), round(float(np.max(drift["tau_mean"])), 3)],
    worst_tau=round(float(np.min(drift["tau_min"])), 3),
    top10_mean_range=[round(float(np.min(drift["top10_mean"])), 3), round(float(np.max(drift["top10_mean"])), 3)],
)

results["aina2027_extensions"] = ext
with open(os.path.join(OUT, "results.json"), "w") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)
print("\n=== AINA-2027 extensions ===")
print(json.dumps(ext, indent=2, ensure_ascii=False))
print("Booking-only Spearman:", {c: results["baseline_spearman"][c]["vs_booking_only"] for c in COUNTRIES})


# ---- 7e. Export ABox for the Jena validation (experiment/jena/Validate.java) ----
# Market-level searches: f_K is the within-market percentile (as in Table 3).
def abox_lines(rows, drop=None, override=None):
    lines = []
    for r in rows:
        t = f"wm:trip_{r['trip_id']}"
        fields = {
            "hasMarket": f'"{r["country"]}"',
            "hasSeatsAvailable": f'"{int(r["seats_available"])}"^^xsd:integer',
            "hasBookingMode": '"auto"' if r["booking_auto"] == 1 else '"manual"',
            "hasPricePerKm": f'"{r["price_per_km"]}"^^xsd:decimal',
            "hasDistance": f'"{r["distance_km"]}"^^xsd:decimal',
        }
        if override:
            fields.update(override.get(r["trip_id"], {}))
        if drop and r["trip_id"] in drop:
            fields.pop(drop[r["trip_id"]], None)
        body = " ;\n    ".join(f"wm:{k} {v}" for k, v in fields.items())
        lines.append(f"{t} a wm:Travel ;\n    {body} .")
    return lines


HDR = ("@prefix wm: <http://example.org/ridesharing#> .\n"
       "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n\n")
recs = listings.to_dict("records")
with open(os.path.join(OUT, "abox_listings.ttl"), "w") as f:
    f.write(HDR + "\n".join(abox_lines(recs)) + "\n")

# Defective copies: 5 defect types x 50 listings, each with exactly one defect.
def_rng = np.random.default_rng(SEED + 3)
picked = def_rng.choice(len(recs), size=250, replace=False)
defects = ["missing_seats", "seats_out_of_range", "bad_booking_mode",
           "negative_price", "missing_market"]
drop, override, truth, drows = {}, {}, [], []
for j, i in enumerate(picked):
    r = dict(recs[i]); r["trip_id"] = "BAD-" + r["trip_id"]; kind = defects[j % 5]
    if kind == "missing_seats":
        drop[r["trip_id"]] = "hasSeatsAvailable"
    elif kind == "seats_out_of_range":
        override[r["trip_id"]] = {"hasSeatsAvailable": '"0"^^xsd:integer'}
    elif kind == "bad_booking_mode":
        override[r["trip_id"]] = {"hasBookingMode": '"instant"'}
    elif kind == "negative_price":
        override[r["trip_id"]] = {"hasPricePerKm": f'"-{r["price_per_km"]}"^^xsd:decimal'}
    else:
        drop[r["trip_id"]] = "hasMarket"
    truth.append(dict(trip_id=r["trip_id"], defect=kind)); drows.append(r)
with open(os.path.join(OUT, "abox_defective.ttl"), "w") as f:
    f.write(HDR + "\n".join(abox_lines(drows, drop, override)) + "\n")
pd.DataFrame(truth).to_csv(os.path.join(OUT, "abox_defective_truth.csv"), index=False)

# Expected inferences and composite score per offer (compared against Jena).
exp_rows = []
for c in COUNTRIES:
    rk = rank_search(listings[listings.country == c])
    for rec in rk.itertuples(index=False):
        exp_rows.append(dict(trip_id=rec.trip_id, market=c, comfort_class=rec.comfort_class,
                             comfort_rule=rec.comfort_rule,
                             tradeoff=rec.tradeoff if isinstance(rec.tradeoff, str) else "",
                             S=rec.S))
pd.DataFrame(exp_rows).to_csv(os.path.join(OUT, "expected_inferences.csv"), index=False)
print("Wrote ABox exports (abox_listings.ttl, abox_defective.ttl) and expected_inferences.csv")


# ---- 7f. Realistic search sizes and correlated attributes (RQ1/RQ2 that can fail)
from scipy.stats import norm

ext2 = {}
srch_rng = np.random.default_rng(SEED + 4)


def score_search(sub, w=(0.4, 0.4, 0.2)):
    """f_K as within-SEARCH percentile (the paper's definition), then S."""
    sub = sub.copy()
    sub["f_K"] = (1.0 - sub["price_per_km"].rank(pct=True)) * 10.0
    sub["f_B"] = np.where(sub["booking_auto"] == 1, 10.0, 2.5)
    sub["S"] = w[0] * sub.f_C + w[1] * sub.f_K + w[2] * sub.f_B
    return sub


WGRID = []
for dC, dK, dB in product(grid, repeat=3):
    w = np.array([0.4 + dC, 0.4 + dK, 0.2 + dB])
    if (w <= 0).any():
        continue
    w = w / w.sum()
    if abs(w[0] - 0.4) < 1e-9 and abs(w[1] - 0.4) < 1e-9:
        continue
    WGRID.append(w)

for n, reps, k in [(20, 200, 3), (100, 200, 10)]:
    rho = dict(cost=[], comfort=[], booking=[]); taus, tops, worst_top = [], [], 1.0
    for c in COUNTRIES:
        mk = listings[listings.country == c]
        for _ in range(reps):
            sub = score_search(mk.iloc[srch_rng.choice(len(mk), n, replace=False)])
            rho["cost"].append(spearmanr(sub.S, sub.f_K).statistic)
            rho["comfort"].append(spearmanr(sub.S, sub.f_C).statistic)
            rho["booking"].append(spearmanr(sub.S, sub.f_B).statistic)
            base = sub.S.rank(ascending=False)
            topb = set(sub.S.sort_values(ascending=False).index[:k])
            for w in WGRID:
                s2 = w[0] * sub.f_C + w[1] * sub.f_K + w[2] * sub.f_B
                taus.append(kendalltau(base.values, s2.rank(ascending=False).values).statistic)
                ov = len(topb & set(s2.sort_values(ascending=False).index[:k])) / k
                tops.append(ov); worst_top = min(worst_top, ov)
    ext2[f"search_{n}"] = dict(
        searches=reps * len(COUNTRIES), top_k=k,
        spearman_mean={kk: round(float(np.nanmean(v)), 2) for kk, v in rho.items()},
        spearman_p95={kk: round(float(np.nanpercentile(v, 95)), 2) for kk, v in rho.items()},
        share_searches_rho_ge_0_9={kk: round(float(np.mean(np.array(v) >= 0.9)), 3) for kk, v in rho.items()},
        tau_mean=round(float(np.nanmean(taus)), 3), tau_p5=round(float(np.nanpercentile(taus, 5)), 3),
        topk_overlap_mean=round(float(np.mean(tops)), 3), topk_overlap_worst=round(worst_top, 2))

# Correlated comfort/cost: Gaussian copula between available seats d and price/km.
# corr(d, ppk) < 0: more free seats AND cheaper (criteria aligned) -> composite
# should collapse onto a single criterion; corr > 0: crowded cars are cheaper
# (criteria in conflict).
cor_rng = np.random.default_rng(SEED + 5)
p = COUNTRIES["France"]
cum = np.cumsum(p["seats"])
sweep = []
for r in [-0.9, -0.6, -0.3, 0.0, 0.3, 0.6, 0.9]:
    vals = dict(cost=[], comfort=[], booking=[])
    for _ in range(20):
        z = cor_rng.multivariate_normal([0, 0], [[1, r], [r, 1]], size=1000)
        d = 1 + np.searchsorted(cum, norm.cdf(z[:, 0]), side="right")
        d = np.clip(d, 1, 4)
        ppk = np.exp(np.log(p["ppk"]) + p["psig"] * z[:, 1])
        df = pd.DataFrame(dict(seats_available=d, price_per_km=ppk,
                               booking_auto=(cor_rng.random(1000) < p["auto"]).astype(int)))
        df["f_C"] = df.seats_available.map({1: 2.5, 2: 5.0, 3: 7.5, 4: 10.0})
        df = score_search(df)
        vals["cost"].append(spearmanr(df.S, df.f_K).statistic)
        vals["comfort"].append(spearmanr(df.S, df.f_C).statistic)
        vals["booking"].append(spearmanr(df.S, df.f_B).statistic)
    sweep.append(dict(corr_seats_price=r, **{f"rho_{kk}": round(float(np.mean(v)), 2) for kk, v in vals.items()}))
ext2["correlation_sweep_france"] = sweep

results["aina2027_extensions_2"] = ext2
with open(os.path.join(OUT, "results.json"), "w") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)
print("\n=== Realistic searches & correlation sweep ===")
print(json.dumps(ext2, indent=2))


# ---- 7g. Reviewer items: global weight analysis, learned ranker + post-hoc
#          explanation, ontology metrics ------------------------------------
ext3 = {}

# (a) Weights over the WHOLE simplex (not only +/-0.1): 1,000 weight triples
#     drawn uniformly (Dirichlet(1,1,1)); tau and top-10 overlap vs baseline.
mc_rng = np.random.default_rng(SEED + 6)
W = mc_rng.dirichlet([1, 1, 1], size=1000)
mc_tau, mc_top, mc_w = [], [], []
for c in COUNTRIES:
    sub = listings[listings.country == c]
    base = sub.S.rank(ascending=False).values
    topb = set(sub.S.sort_values(ascending=False).index[:10])
    for w in W:
        s2 = w[0] * sub.f_C + w[1] * sub.f_K + w[2] * sub.f_B
        mc_tau.append(kendalltau(base, s2.rank(ascending=False).values).statistic)
        mc_top.append(len(topb & set(s2.sort_values(ascending=False).index[:10])) / 10)
        mc_w.append(w)
mc_tau, mc_top, mc_w = np.array(mc_tau), np.array(mc_top), np.array(mc_w)
dist = np.abs(mc_w - np.array([0.4, 0.4, 0.2])).sum(axis=1) / 2   # total-variation distance
ext3["weights_global"] = dict(
    n_triples=len(W), n_markets=len(COUNTRIES),
    tau_mean=round(float(mc_tau.mean()), 3),
    share_tau_ge_0_7=round(float((mc_tau >= 0.7).mean()), 3),
    share_tau_ge_0_7_within_tv_0_2=round(float((mc_tau[dist <= 0.2] >= 0.7).mean()), 3),
    share_tau_ge_0_7_beyond_tv_0_4=round(float((mc_tau[dist > 0.4] >= 0.7).mean()), 3),
    top10_mean=round(float(mc_top.mean()), 3),
    tau_when_any_weight_gt_0_6=round(float(mc_tau[(mc_w > 0.6).any(axis=1)].mean()), 3),
)

# (b) Learned ranker baseline + post-hoc explanation. Without preference
#     labels we distil S into a gradient-boosted model trained on the raw
#     listing fields (what a black-box ranker would see), rank with it, and
#     explain it with TreeSHAP; then compare with the exact decomposition of S.
import warnings
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.model_selection import train_test_split
import shap
warnings.filterwarnings("ignore")
fr = listings[listings.country == "France"].reset_index(drop=True)
X = fr[["seats_available", "price_per_km", "booking_auto"]].values
y = fr["S"].values
Xtr, Xte, ytr, yte, itr, ite = train_test_split(X, y, np.arange(len(fr)), test_size=0.3, random_state=0)
gbm = GradientBoostingRegressor(n_estimators=300, max_depth=3, learning_rate=0.05, random_state=0).fit(Xtr, ytr)
pred = gbm.predict(Xte)
sv = shap.TreeExplainer(gbm).shap_values(Xte)                      # post-hoc attributions
te = fr.iloc[ite]
exact = np.column_stack([0.4 * (te.f_C - fr.f_C.mean()),           # exact contributions of S
                         0.4 * (te.f_K - fr.f_K.mean()),
                         0.2 * (te.f_B - fr.f_B.mean())])
top_post, top_exact = np.abs(sv).argmax(1), np.abs(exact).argmax(1)
sign_flip = (np.sign(sv) != np.sign(exact)) & (np.abs(exact) > 0.25)
order_post = np.argsort(-np.abs(sv), axis=1); order_exact = np.argsort(-np.abs(exact), axis=1)
ext3["learned_ranker"] = dict(
    model="GradientBoostingRegressor (300 trees, depth 3) on raw fields (seats, price/km, booking)",
    test_offers=int(len(yte)),
    kendall_tau_vs_S=round(float(kendalltau(yte, pred).statistic), 3),
    top10_overlap_vs_S=round(len(set(np.argsort(-yte)[:10]) & set(np.argsort(-pred)[:10])) / 10, 2),
    shap_top_criterion_differs_pct=round(float((top_post != top_exact).mean() * 100), 1),
    shap_full_order_differs_pct=round(float((order_post != order_exact).any(axis=1).mean() * 100), 1),
    shap_sign_contradicts_exact_pct=round(float(sign_flip.any(axis=1).mean() * 100), 1),
)

# (c) Ontology metrics (TBox only)
from rdflib import OWL, RDFS
tb = Graph(); tb.parse(os.path.join(os.path.dirname(__file__), "..", "ontology", "ridesharing.ttl"))
local = lambda u: str(u).startswith("http://example.org/ridesharing#")
ext3["ontology_metrics"] = dict(
    triples=len(tb),
    classes=sum(1 for c in tb.subjects(RDF.type, OWL.Class) if local(c)),
    object_properties=sum(1 for c in tb.subjects(RDF.type, OWL.ObjectProperty) if local(c)),
    datatype_properties=sum(1 for c in tb.subjects(RDF.type, OWL.DatatypeProperty) if local(c)),
    named_individuals=sum(1 for c in tb.subjects(RDF.type, OWL.NamedIndividual) if local(c)),
    subclass_axioms=sum(1 for _ in tb.triples((None, RDFS.subClassOf, None))),
    disjointness_axioms=sum(1 for _ in tb.triples((None, OWL.disjointWith, None))),
    functional_properties=sum(1 for _ in tb.subjects(RDF.type, OWL.FunctionalProperty)),
    schema_org_alignments=sum(1 for _, _, o in tb.triples((None, RDFS.subClassOf, None)) if str(o).startswith("https://schema.org/")),
    prov_alignments=sum(1 for _, _, o in tb.triples((None, RDFS.subClassOf, None)) if str(o).startswith("http://www.w3.org/ns/prov#")),
)
results["aina2027_extensions_3"] = ext3
with open(os.path.join(OUT, "results.json"), "w") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)
print("\n=== Reviewer items (7g) ===")
print(json.dumps(ext3, indent=2))


# ---- 7h. Weights from established MCDM weighting methods (reviewer R2) ----
# (i) surrogate weights from the ordinal judgement comfort = cost > booking
#     (rank-sum and rank-order centroid, Barron & Barrett 1996; ties averaged);
# (ii) objective weights from the data (entropy; CRITIC, Diakoulaki et al. 1995).
def entropy_weights(M):
    P = M / M.sum(axis=0)
    P = np.where(P > 0, P, 1e-12)
    e = -(P * np.log(P)).sum(axis=0) / np.log(len(M))
    d = 1 - e
    return d / d.sum()


def critic_weights(M):
    Z = (M - M.min(axis=0)) / (M.max(axis=0) - M.min(axis=0))
    sd = Z.std(axis=0, ddof=1)
    R = np.corrcoef(Z, rowvar=False)
    c = sd * (1 - R).sum(axis=0)
    return c / c.sum()


roc3 = np.array([(1 + 1/2 + 1/3) / 3, (1/2 + 1/3) / 3, (1/3) / 3])
schemes = {"rank_sum": np.array([2.5, 2.5, 1.0]) / 6.0,
           "rank_order_centroid": np.array([(roc3[0] + roc3[1]) / 2, (roc3[0] + roc3[1]) / 2, roc3[2]])}
wcmp = {k: dict(weights=[round(float(x), 3) for x in v], tau=[], top10=[]) for k, v in schemes.items()}
wcmp["entropy"] = dict(weights=[], tau=[], top10=[]); wcmp["critic"] = dict(weights=[], tau=[], top10=[])
for c in COUNTRIES:
    sub = listings[listings.country == c]
    M = sub[["f_C", "f_K", "f_B"]].values
    base = sub.S.rank(ascending=False).values
    topb = set(sub.S.sort_values(ascending=False).index[:10])
    local = dict(schemes, entropy=entropy_weights(M), critic=critic_weights(M))
    for k, w in local.items():
        s2 = M @ w
        s2 = pd.Series(s2, index=sub.index)
        wcmp[k]["tau"].append(kendalltau(base, s2.rank(ascending=False).values).statistic)
        wcmp[k]["top10"].append(len(topb & set(s2.sort_values(ascending=False).index[:10])) / 10)
        if k in ("entropy", "critic"):
            wcmp[k]["weights"].append([round(float(x), 3) for x in w])
for k in wcmp:
    wcmp[k]["tau_mean"] = round(float(np.mean(wcmp[k].pop("tau"))), 3)
    wcmp[k]["top10_mean"] = round(float(np.mean(wcmp[k].pop("top10"))), 3)
results["aina2027_weight_methods"] = wcmp
with open(os.path.join(OUT, "results.json"), "w") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)
print("\n=== Weighting methods (7h) ===")
print(json.dumps(wcmp, indent=2))
