// Semantic-web validation of the ridesharing pipeline with Apache Jena 4.10.
//
// Run from the repository root (after `python3 experiment/run_experiment.py`):
//   java -cp ".tools/apache-jena-4.10.0/lib/*" experiment/jena/Validate.java
//
// It checks, with standard tools instead of the Python re-implementation:
//   A. Jena rule inference: ontology/rules.rules run by GenericRuleReasoner must
//      infer exactly the comfort levels, trade-offs and rules of the pipeline.
//   B. SPARQL: the ranking and rationales produced by experiment/sparql/rationale.rq
//      over the inferred graph must match the pipeline's composite scores.
//   C. OWL consistency of ontology + data + inferences (OWL Mini reasoner), with a
//      negative control that must be detected as inconsistent.
//   D. SHACL: the valid ABox must conform; every injected defect must be caught.
//   E. Latency of the standard stack per search (SHACL + rules + SPARQL).
// Results are written to experiment/out/jena_validation.json.

import org.apache.jena.graph.Graph;
import org.apache.jena.query.*;
import org.apache.jena.rdf.model.*;
import org.apache.jena.reasoner.Reasoner;
import org.apache.jena.reasoner.ReasonerRegistry;
import org.apache.jena.reasoner.ValidityReport;
import org.apache.jena.reasoner.rulesys.GenericRuleReasoner;
import org.apache.jena.reasoner.rulesys.Rule;
import org.apache.jena.riot.RDFDataMgr;
import org.apache.jena.shacl.ShaclValidator;
import org.apache.jena.shacl.Shapes;
import org.apache.jena.shacl.ValidationReport;
import org.apache.jena.vocabulary.RDF;

import java.io.*;
import java.nio.file.*;
import java.util.*;
import java.util.stream.*;

public class Validate {
    static final String WM = "http://example.org/ridesharing#";
    static final String PROV = "http://www.w3.org/ns/prov#";
    static final String[] MARKETS = {"Brazil", "France", "Italy", "Portugal", "Ukraine"};

    static List<Rule> rules;
    static Model tbox;
    static Shapes shapes;
    static String rationaleQuery;
    static String costUpdate;
    static String rulesRu;
    static final String FACTS = "PREFIX prov: <http://www.w3.org/ns/prov#> PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> "
        + "SELECT ?offer ?val ?plan WHERE { ?e prov:wasDerivedFrom ?offer ; rdf:value ?val ; prov:wasGeneratedBy/prov:qualifiedAssociation/prov:hadPlan ?plan }";

    public static void main(String[] args) throws Exception {
        org.apache.jena.sys.JenaSystem.init();
        tbox = RDFDataMgr.loadModel("ontology/ridesharing.ttl");
        rules = Rule.rulesFromURL("ontology/rules.rules");
        shapes = Shapes.parse(RDFDataMgr.loadGraph("ontology/shapes.ttl"));
        rationaleQuery = Files.readString(Path.of("experiment/sparql/rationale.rq"));
        costUpdate = Files.readString(Path.of("experiment/sparql/cost_percentiles.rq"));
        rulesRu = Files.readString(Path.of("ontology/rules.ru"));
        Model abox = RDFDataMgr.loadModel("experiment/out/abox_listings.ttl");
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("jena_version", org.apache.jena.Jena.VERSION);
        out.put("java_version", System.getProperty("java.version"));
        out.put("rules_loaded", rules.size());

        // ---------------- A. Jena rule inference vs pipeline -----------------
        Map<String, String[]> expected = new HashMap<>();   // trip -> {class, rule, tradeoff, S, market}
        for (String line : Files.readAllLines(Path.of("experiment/out/expected_inferences.csv")).subList(1, 5001)) {
            String[] c = line.split(",", -1);
            expected.put(c[0], new String[]{c[2], c[3], c[4], c[5], c[1]});
        }
        // Each market is one search. Reference stack (W3C only): SPARQL Update
        // CostPercentiles + SPARQL Update rules (ontology/rules.ru). The Jena
        // rules (ontology/rules.rules) must produce the same facts and plans.
        long t0 = System.nanoTime();
        Model scored = ModelFactory.createDefaultModel();
        Model ded = ModelFactory.createDefaultModel();
        Property mkt = abox.createProperty(WM + "hasMarket");
        int jenaVsSparqlDiff = 0, sortVsSparqlDiff = 0; long jenaTriples = 0;
        for (String m : MARKETS) {
            Model sub = ModelFactory.createDefaultModel();
            for (Resource x : abox.listSubjectsWithProperty(mkt, m).toList())
                sub.add(abox.listStatements(x, null, (RDFNode) null));
            Model bySort = ModelFactory.createDefaultModel().add(sub);
            costPercentiles(sub);
            sortPercentiles(bySort);
            sortVsSparqlDiff += costDiff(sub, bySort);
            Model w3c = ModelFactory.createDefaultModel().add(sub);
            org.apache.jena.update.UpdateAction.parseExecute(rulesRu, w3c);
            InfModel im = infer(sub);
            im.prepare();
            Set<String> fw = facts(w3c), fj = facts(im);
            Set<String> sym = new HashSet<>(fw); sym.addAll(fj);
            Set<String> both = new HashSet<>(fw); both.retainAll(fj);
            jenaVsSparqlDiff += sym.size() - both.size();
            jenaTriples += im.getDeductionsModel().size();
            scored.add(sub);
            ded.add(w3c.difference(sub));
        }
        double inferMs = (System.nanoTime() - t0) / 1e6;
        Model inf = ModelFactory.createDefaultModel().add(tbox).add(scored).add(ded);
        int comfortMismatch = 0, tradeMismatch = 0, ruleMismatch = 0, multiComfort = 0;
        Property hasComfort = inf.createProperty(WM + "hasComfortLevel");
        Property hasTrade = inf.createProperty(WM + "hasTradeOff");
        Map<String, String> planOf = new HashMap<>();          // trip|value -> rule
        Map<String, Integer> ruleCount = new TreeMap<>();
        for (String f : facts(inf)) {
            String[] x = f.split("\\|");
            planOf.put(x[0] + "|" + x[1], x[2]);
            ruleCount.merge(x[2], 1, Integer::sum);
        }
        for (Map.Entry<String, String[]> e : expected.entrySet()) {
            Resource t = inf.createResource(WM + "trip_" + e.getKey());
            List<RDFNode> levels = inf.listObjectsOfProperty(t, hasComfort).toList();
            List<RDFNode> trades = inf.listObjectsOfProperty(t, hasTrade).toList();
            if (levels.size() != 1) multiComfort++;
            String lvl = levels.isEmpty() ? "" : levels.get(0).asResource().getLocalName();
            String tr = trades.isEmpty() ? "" : trades.get(0).asResource().getLocalName();
            if (!lvl.equals(e.getValue()[0])) comfortMismatch++;
            if (!tr.equals(e.getValue()[2])) tradeMismatch++;
            if (!e.getValue()[1].equals(planOf.get("trip_" + e.getKey() + "|" + lvl))) ruleMismatch++;
        }
        Map<String, Object> a = new LinkedHashMap<>();
        a.put("listings", expected.size());
        a.put("rules_engine_reference", "SPARQL 1.1 Update (ontology/rules.ru)");
        a.put("inferred_triples_sparql_update", ded.size());
        a.put("inferred_triples_jena_rules", jenaTriples);
        a.put("facts_differing_sparql_vs_jena_rules", jenaVsSparqlDiff);
        a.put("cost_scores_differing_sparql_vs_sort", sortVsSparqlDiff);
        a.put("all_5000_ms", Math.round(inferMs));
        a.put("comfort_mismatches", comfortMismatch);
        a.put("tradeoff_mismatches", tradeMismatch);
        a.put("comfort_rule_mismatches", ruleMismatch);
        a.put("listings_without_exactly_one_comfort_level", multiComfort);
        a.put("facts_per_rule", ruleCount);
        out.put("A_rules", a);

        // ---------------- B. SPARQL ranking + rationales ---------------------
        double maxAbsDiff = 0; int orderViolations = 0, rows = 0;
        List<String> franceTop = new ArrayList<>();
        for (String m : MARKETS) {
            List<QuerySolution> sol = rationale(inf, m);
            double prev = Double.POSITIVE_INFINITY;
            for (QuerySolution q : sol) {
                rows++;
                String trip = q.getResource("offer").getLocalName().substring(5);
                double s = q.getLiteral("S").getDouble();
                maxAbsDiff = Math.max(maxAbsDiff, Math.abs(s - Double.parseDouble(expected.get(trip)[3])));
                if (s > prev + 1e-12) orderViolations++;
                prev = s;
                if (m.equals("France") && franceTop.size() < 3)
                    franceTop.add(trip + " S=" + String.format(Locale.ROOT, "%.2f", s) + " :: " + q.getLiteral("rationale").getString());
            }
        }
        Map<String, Object> b = new LinkedHashMap<>();
        b.put("rows", rows);
        b.put("max_abs_diff_S_vs_pipeline", maxAbsDiff);
        b.put("order_violations", orderViolations);
        b.put("france_top3", franceTop);
        b.put("cq2_france_cheap_but_approval", count(inf, "experiment/sparql/cq2_cheap_but_approval.rq", "France"));
        b.put("cq4_rule_coverage", cq4(inf));
        try (QueryExecution qe = QueryExecution.create().query(Files.readString(Path.of("experiment/sparql/cq5_contrastive.rq"))).model(inf)
                .initialBinding(new QuerySolutionMap() {{ add("a", inf.createResource(WM + "trip_FR-0271")); add("b", inf.createResource(WM + "trip_FR-0057")); }}).build()) {
            QuerySolution q5 = qe.execSelect().next();
            b.put("cq5_FR0271_vs_FR0057", Map.of("gap", round3(q5.getLiteral("gap").getDouble()),
                    "comfort", round3(q5.getLiteral("dComfort").getDouble()), "cost", round3(q5.getLiteral("dCost").getDouble()),
                    "booking", round3(q5.getLiteral("dBooking").getDouble())));
        }
        out.put("B_sparql", b);

        // ---------------- C. OWL consistency --------------------------------
        Map<String, Object> c = new LinkedHashMap<>();
        Model all = ModelFactory.createDefaultModel().add(tbox).add(scored).add(ded);
        long t1 = System.nanoTime();
        ValidityReport vr = owl(all).validate();
        c.put("consistent", vr.isValid());
        c.put("owl_reasoner", "Jena OWL Mini");
        c.put("check_ms", Math.round((System.nanoTime() - t1) / 1e6));
        // negative control 1: one offer with two different comfort levels
        Model bad1 = ModelFactory.createDefaultModel().add(tbox).add(scored).add(ded);
        Resource t = bad1.createResource(WM + "trip_FR-0271");
        bad1.add(t, bad1.createProperty(WM + "hasComfortLevel"), bad1.createResource(WM + "Uncomfortable"));
        c.put("control_two_comfort_levels_detected", !owl(bad1).validate().isValid());
        // negative control 2: an offer that is also typed as a car
        Model bad2 = ModelFactory.createDefaultModel().add(tbox).add(scored).add(ded);
        bad2.add(bad2.createResource(WM + "trip_FR-0271"), RDF.type, bad2.createResource(WM + "Car"));
        c.put("control_offer_typed_as_car_detected", !owl(bad2).validate().isValid());
        out.put("C_owl_consistency", c);

        // ---------------- D. SHACL -----------------------------------------
        Map<String, Object> d = new LinkedHashMap<>();
        ValidationReport ok = ShaclValidator.get().validate(shapes, abox.getGraph());
        d.put("valid_abox_conforms", ok.conforms());
        d.put("valid_abox_violations", ok.getEntries().size());
        Graph defective = RDFDataMgr.loadGraph("experiment/out/abox_defective.ttl");
        ValidationReport rep = ShaclValidator.get().validate(shapes, defective);
        Set<String> flagged = rep.getEntries().stream()
                .map(en -> en.focusNode().getLocalName()).collect(Collectors.toSet());
        List<String> truth = Files.readAllLines(Path.of("experiment/out/abox_defective_truth.csv")).subList(1, 251);
        Map<String, int[]> perType = new TreeMap<>();
        for (String line : truth) {
            String[] x = line.split(",");
            int[] v = perType.computeIfAbsent(x[1], k -> new int[2]);
            v[1]++;
            if (flagged.contains("trip_" + x[0])) v[0]++;
        }
        Map<String, String> pt = new TreeMap<>();
        perType.forEach((k, v) -> pt.put(k, v[0] + "/" + v[1]));
        d.put("defective_records", truth.size());
        d.put("defective_records_rejected", flagged.size());
        d.put("rejected_per_defect_type", pt);
        out.put("D_shacl", d);

        // ---------------- E. Latency per search ------------------------------
        List<Resource> fr = abox.listSubjectsWithProperty(abox.createProperty(WM + "hasMarket"), "France").toList();
        fr.sort(Comparator.comparing(Resource::getURI));
        Random rnd = new Random(20260607L);
        Map<String, Object> e = new LinkedHashMap<>();
        String[] variants = {"w3c_sparql", "jena_rules", "w3c_sort_percentile", "plain_java"};
        for (int[] cfg : new int[][]{{20, 200}, {100, 100}, {1000, 20}}) {
            int n = cfg[0], reps = cfg[1];
            Map<String, Object> per = new LinkedHashMap<>();
            for (String v : variants) {
                double[] ms = new double[reps];
                for (int r = -5; r < reps; r++) {             // 5 warm-up runs
                    Collections.shuffle(fr, rnd);
                    Model sub = ModelFactory.createDefaultModel();
                    for (Resource x : fr.subList(0, n)) sub.add(abox.listStatements(x, null, (RDFNode) null));
                    sub.add(tbox);                              // ontology loaded once by the service
                    if (v.equals("plain_java")) {               // same computation without semantic tech
                        int k = 0; int[] seats = new int[n]; boolean[] auto = new boolean[n]; double[] ppk = new double[n]; String[] ids = new String[n];
                        for (Resource x : fr.subList(0, n)) {
                            seats[k] = x.getProperty(abox.createProperty(WM + "hasSeatsAvailable")).getInt();
                            auto[k] = x.getProperty(abox.createProperty(WM + "hasBookingMode")).getString().equals("auto");
                            ppk[k] = x.getProperty(abox.createProperty(WM + "hasPricePerKm")).getDouble();
                            ids[k++] = x.getLocalName();
                        }
                        long p0 = System.nanoTime();
                        double[] sorted = ppk.clone(); Arrays.sort(sorted);
                        Integer[] idx = new Integer[n]; double[] S = new double[n]; String[] why = new String[n];
                        for (int i = 0; i < n; i++) {
                            double fc = seats[i] >= 4 ? 10 : seats[i] == 3 ? 7.5 : seats[i] == 2 ? 5 : 2.5;
                            int lo = lower(sorted, ppk[i]), hi = upper(sorted, ppk[i]);
                            double fk = 10.0 * (1.0 - (lo + (hi - lo + 1) / 2.0) / n), fb = auto[i] ? 10 : 2.5;
                            S[i] = 0.4 * fc + 0.4 * fk + 0.2 * fb; idx[i] = i;
                            why[i] = "comfort " + fc + ", cost percentile " + Math.round(100 - 10 * fk) + ", booking " + (auto[i] ? "automatic" : "manual");
                        }
                        Arrays.sort(idx, (x1, x2) -> Double.compare(S[x2], S[x1]));
                        double el = (System.nanoTime() - p0) / 1e6;
                        if (r >= 0) ms[r] = el;
                        continue;
                    }
                    long s0 = System.nanoTime();
                    ValidationReport vrep = ShaclValidator.get().validate(shapes, sub.getGraph());
                    Model g;
                    if (v.equals("jena_rules")) { costPercentiles(sub); g = infer(sub); }
                    else {
                        if (v.equals("w3c_sparql")) costPercentiles(sub); else sortPercentiles(sub);
                        org.apache.jena.update.UpdateAction.parseExecute(rulesRu, sub); g = sub;
                    }
                    List<QuerySolution> res = rationale(g, "France");
                    double el = (System.nanoTime() - s0) / 1e6;
                    if (!vrep.conforms() || res.size() != n) throw new IllegalStateException("latency run failed");
                    if (r >= 0) ms[r] = el;
                }
                Arrays.sort(ms);
                per.put(v, Map.of("median_ms", round1(ms[reps / 2]), "p95_ms", round1(ms[(int) Math.ceil(0.95 * reps) - 1])));
            }
            e.put(String.valueOf(n), per);
        }
        // OWL consistency check of one 100-offer search (offline audit, not on the query path)
        double[] owlMs = new double[20];
        for (int r = -3; r < 20; r++) {
            Collections.shuffle(fr, rnd);
            Model sub = ModelFactory.createDefaultModel();
            for (Resource x : fr.subList(0, 100)) sub.add(abox.listStatements(x, null, (RDFNode) null));
            costPercentiles(sub);
            org.apache.jena.update.UpdateAction.parseExecute(rulesRu, sub);
            Model all100 = ModelFactory.createDefaultModel().add(tbox).add(sub);
            long s0 = System.nanoTime();
            boolean okc = owl(all100).validate().isValid();
            if (!okc) throw new IllegalStateException("inconsistent search");
            if (r >= 0) owlMs[r] = (System.nanoTime() - s0) / 1e6;
        }
        Arrays.sort(owlMs);
        e.put("owl_consistency_100_offers_median_ms", round1(owlMs[10]));
        e.put("pipeline_w3c_sparql", "SHACL + SPARQL Update percentiles + SPARQL Update rules + SPARQL ranking/rationales");
        out.put("E_latency", e);

        String json = toJson(out, 0);
        Files.writeString(Path.of("experiment/out/jena_validation.json"), json);
        System.out.println(json);
    }

    static InfModel infer(Model data) {
        GenericRuleReasoner r = new GenericRuleReasoner(rules);
        r.setMode(GenericRuleReasoner.FORWARD_RETE);
        Model base = ModelFactory.createDefaultModel().add(tbox).add(data);
        return ModelFactory.createInfModel(r, base);
    }

    static void costPercentiles(Model m) {
        org.apache.jena.update.UpdateAction.parseExecute(costUpdate, m);
    }

    static Set<String> facts(Model m) {
        Set<String> out = new HashSet<>();
        try (QueryExecution qe = QueryExecution.create().query(FACTS).model(m).build()) {
            qe.execSelect().forEachRemaining(q -> out.add(q.getResource("offer").getLocalName() + "|"
                    + q.getResource("val").getLocalName() + "|" + q.getResource("plan").getLocalName()));
        }
        return out;
    }

    // Same within-search percentile as cost_percentiles.rq, computed by sorting (O(n log n)).
    static void sortPercentiles(Model m) {
        Property ppk = m.createProperty(WM + "hasPricePerKm"), cs = m.createProperty(WM + "hasCostScore");
        List<Statement> st = m.listStatements(null, ppk, (RDFNode) null).toList();
        int n = st.size();
        double[] v = st.stream().mapToDouble(x -> x.getDouble()).toArray();
        double[] sorted = v.clone(); Arrays.sort(sorted);
        for (int i = 0; i < n; i++) {
            int lo = lower(sorted, v[i]), hi = upper(sorted, v[i]);   // less = lo, eq = hi - lo
            double rank = lo + (hi - lo + 1) / 2.0;
            m.add(st.get(i).getSubject(), cs, m.createTypedLiteral(10.0 * (1.0 - rank / n)));
        }
    }
    static int lower(double[] a, double x) { int l = 0, h = a.length; while (l < h) { int k = (l + h) >>> 1; if (a[k] < x) l = k + 1; else h = k; } return l; }
    static int upper(double[] a, double x) { int l = 0, h = a.length; while (l < h) { int k = (l + h) >>> 1; if (a[k] <= x) l = k + 1; else h = k; } return l; }

    static int costDiff(Model a, Model b) {
        Property cs = a.createProperty(WM + "hasCostScore");
        int d = 0;
        for (Statement st : a.listStatements(null, cs, (RDFNode) null).toList()) {
            double y = b.getProperty(st.getSubject(), cs).getDouble();
            if (Math.abs(st.getDouble() - y) > 1e-9) d++;
        }
        return d;
    }

    static InfModel owl(Model m) {
        Reasoner r = ReasonerRegistry.getOWLMiniReasoner();
        return ModelFactory.createInfModel(r, m);
    }

    static List<QuerySolution> rationale(Model m, String market) {
        QuerySolutionMap init = new QuerySolutionMap();
        init.add("market", m.createLiteral(market));
        try (QueryExecution qe = QueryExecution.create().query(rationaleQuery).model(m).initialBinding(init).build()) {
            List<QuerySolution> l = new ArrayList<>();
            qe.execSelect().forEachRemaining(l::add);
            return l;
        }
    }

    static int count(Model m, String file, String market) throws IOException {
        QuerySolutionMap init = new QuerySolutionMap();
        init.add("market", m.createLiteral(market));
        try (QueryExecution qe = QueryExecution.create().query(Files.readString(Path.of(file))).model(m).initialBinding(init).build()) {
            int n = 0;
            ResultSet rs = qe.execSelect();
            while (rs.hasNext()) { rs.next(); n++; }
            return n;
        }
    }

    static Map<String, Object> cq4(Model m) throws IOException {
        Map<String, Object> r = new TreeMap<>();
        try (QueryExecution qe = QueryExecution.create().query(Files.readString(Path.of("experiment/sparql/cq4_rule_coverage.rq"))).model(m).build()) {
            qe.execSelect().forEachRemaining(q -> r.put(q.getResource("rule").getLocalName(), q.getLiteral("n").getInt()));
        }
        return r;
    }

    static double round1(double x) { return Math.round(x * 10) / 10.0; }
    static double round3(double x) { return Math.round(x * 1000) / 1000.0; }

    @SuppressWarnings("unchecked")
    static String toJson(Object o, int ind) {
        String pad = "  ".repeat(ind + 1), end = "  ".repeat(ind);
        if (o instanceof Map) {
            Map<String, Object> m = (Map<String, Object>) o;
            return m.entrySet().stream().map(e -> pad + "\"" + e.getKey() + "\": " + toJson(e.getValue(), ind + 1))
                    .collect(Collectors.joining(",\n", "{\n", "\n" + end + "}"));
        }
        if (o instanceof List) {
            List<Object> l = (List<Object>) o;
            return l.stream().map(x -> pad + toJson(x, ind + 1)).collect(Collectors.joining(",\n", "[\n", "\n" + end + "]"));
        }
        if (o instanceof String) return "\"" + ((String) o).replace("\\", "\\\\").replace("\"", "\\\"") + "\"";
        return String.valueOf(o);
    }
}
