// Jena run of the mobile module: rules R1-R8, then R9-R12, CQ1 and CQ6 on the same searches
// as crosscheck_oxigraph.mjs; plus SHACL and OWL consistency of ontology + data + inferences.
// Run from the code root (Apache Jena 4.10, Java 11+):
//   java -cp ".tools/apache-jena-4.10.0/lib/*" experiment/mobile/ContextCheck.java
import org.apache.jena.atlas.json.*;
import org.apache.jena.query.*;
import org.apache.jena.rdf.model.*;
import org.apache.jena.reasoner.ReasonerRegistry;
import org.apache.jena.riot.Lang;
import org.apache.jena.riot.RDFDataMgr;
import org.apache.jena.shacl.ShaclValidator;
import org.apache.jena.shacl.Shapes;
import org.apache.jena.update.UpdateAction;
import java.io.StringReader;
import java.nio.file.*;
import java.util.*;

public class ContextCheck {
    static final String WM = "http://example.org/ridesharing#", XSD = "http://www.w3.org/2001/XMLSchema#", SCH = "https://schema.org/";
    static String dec(JsonValue v) { return "\"" + v.toString() + "\"^^<" + XSD + "decimal>"; }
    static String str(JsonObject o, String k) { return o.get(k).getAsString().value(); }
    public static void main(String[] a) throws Exception {
        org.apache.jena.sys.JenaSystem.init();
        JsonArray check = JSON.read("experiment/out/mobile_searches.json").get("check").getAsArray();
        Model tbox = RDFDataMgr.loadModel("ontology/ridesharing.ttl");
        Shapes shapes = Shapes.parse(RDFDataMgr.loadGraph("ontology/shapes.ttl"));
        String cost = Files.readString(Path.of("experiment/sparql/cost_percentiles.rq")), rules = Files.readString(Path.of("ontology/rules.ru")),
               ctx = Files.readString(Path.of("ontology/rules_context.ru")), notes = Files.readString(Path.of("experiment/sparql/cq6_context_notes.rq")),
               rat = Files.readString(Path.of("experiment/sparql/rationale.rq")),
               settle = Files.readString(Path.of("ontology/rules_settlement.ru")), cq8 = Files.readString(Path.of("experiment/sparql/cq8_settlement.rq")),
               cq7 = Files.readString(Path.of("experiment/sparql/cq7_personal_view.rq"));
        int noteBad = 0, moved = 0, scoreBad = 0, shaclBad = 0, owlBad = 0, idx = 0, trips = 0, fareBad = 0, cq7Bad = 0;
        for (JsonValue sv : check) {
            JsonObject s = sv.getAsObject(), c = s.get("context").getAsObject();
            String market = str(s, "market");
            StringBuilder t = new StringBuilder("<" + WM + "device> a <" + WM + "DeviceContext> ; <" + SCH + "latitude> " + dec(c.get("lat")) + " ; <" + SCH + "longitude> " + dec(c.get("lon")) + " ; <" + WM + "hasCosLatitude> " + dec(c.get("cos")) + " ; <" + WM + "hasNowMinute> \"" + c.get("now") + "\"^^<" + XSD + "integer> .\n");
            Map<String, JsonObject> ref = new HashMap<>();
            for (JsonValue ov : s.get("offers").getAsArray()) {
                JsonObject o = ov.getAsObject(); String id = str(o, "id"); ref.put(id, o);
                t.append("<" + WM + id + "> a <" + WM + "Travel> ; <" + WM + "hasMarket> \"" + market + "\" ; <" + WM + "hasSeatsAvailable> \"" + o.get("seats") + "\"^^<" + XSD + "integer> ; <" + WM + "hasBookingMode> \"" + str(o, "booking") + "\" ; <" + WM + "hasPricePerKm> \"" + str(o, "price_per_km") + "\"^^<" + XSD + "decimal> ; <" + WM + "hasDistance> \"" + str(o, "distance") + "\"^^<" + XSD + "decimal> ; <" + WM + "hasDepartureMinute> \"" + o.get("dep") + "\"^^<" + XSD + "integer> ; <" + WM + "hasPickup> <" + WM + id + "-pickup> .\n<" + WM + id + "-pickup> a <" + WM + "Place> ; <" + SCH + "latitude> " + dec(o.get("plat")) + " ; <" + SCH + "longitude> " + dec(o.get("plon")) + " .\n");
            }
            Model m = ModelFactory.createDefaultModel();
            m.read(new StringReader(t.toString()), null, "TURTLE");
            m.add(tbox);
            UpdateAction.parseExecute(cost, m); UpdateAction.parseExecute(rules, m);
            QuerySolutionMap init = new QuerySolutionMap(); init.add("market", m.createLiteral(market));
            List<String> before = order(m, rat, init);
            UpdateAction.parseExecute(ctx, m);
            List<String> after = order(m, rat, init);
            for (int i = 0; i < before.size(); i++) moved += before.get(i).equals(after.get(i)) ? 0 : 1;
            for (String row : after) { String[] p = row.split(" "); scoreBad += Math.abs(Double.parseDouble(p[1]) - ref.get(p[0]).get("S").getAsNumber().value().doubleValue()) > 1e-9 ? 1 : 0; }
            Map<String, List<String>> got = new HashMap<>();
            for (String id : ref.keySet()) got.put(id, new ArrayList<>());
            try (QueryExecution qe = QueryExecution.create().query(notes).model(m).build()) {
                qe.execSelect().forEachRemaining(q -> got.get(q.getResource("offer").getLocalName()).add(q.getLiteral("rule").getString()));
            }
            for (String id : ref.keySet()) {
                List<String> exp = new ArrayList<>(); ref.get(id).get("notes").getAsArray().forEach(v -> exp.add(v.getAsString().value()));
                Collections.sort(exp); Collections.sort(got.get(id)); noteBad += exp.equals(got.get(id)) ? 0 : 1;
            }
            long now = c.get("now").getAsNumber().value().longValue();
            List<String> exp7 = new ArrayList<>(), got7 = new ArrayList<>();
            for (JsonObject o : ref.values()) {
                List<String> nn = new ArrayList<>(); o.get("notes").getAsArray().forEach(v -> nn.add(v.getAsString().value()));
                long dep = o.get("dep").getAsNumber().value().longValue();
                int tier = dep < now ? 2 : nn.contains("R13") ? 1 : (nn.contains("R12") || nn.contains("R10")) ? 2 : 0;
                exp7.add(tier + ":" + String.format(java.util.Locale.ROOT, "%.9f", o.get("S").getAsNumber().value().doubleValue()));
            }
            exp7.sort((x, y) -> { String[] p = x.split(":"), q = y.split(":"); int tc = Integer.compare(Integer.parseInt(p[0]), Integer.parseInt(q[0])); return tc != 0 ? tc : Double.compare(Double.parseDouble(q[1]), Double.parseDouble(p[1])); });
            try (QueryExecution qe = QueryExecution.create().query(cq7).model(m).build()) {
                qe.execSelect().forEachRemaining(q -> got7.add(q.getLiteral("blocked").getInt() + ":" + String.format(java.util.Locale.ROOT, "%.9f", q.getLiteral("S").getDouble())));
            }
            cq7Bad += exp7.equals(got7) ? 0 : 1;
            StringBuilder rec = new StringBuilder();
            for (JsonObject o : ref.values()) if (o.hasKey("trip")) {
                JsonObject tr = o.get("trip").getAsObject(); String id = str(o, "id");
                rec.append("<" + WM + id + "-rec-p> a <" + WM + "TripRecord> ; <" + WM + "ofOffer> <" + WM + id + "> ; <" + WM + "recordedBy> \"passenger\" ; <" + WM + "hasTravelledKm> " + dec(tr.get("kp")) + " .\n");
                rec.append("<" + WM + id + "-rec-d> a <" + WM + "TripRecord> ; <" + WM + "ofOffer> <" + WM + id + "> ; <" + WM + "recordedBy> \"driver\" ; <" + WM + "hasTravelledKm> " + dec(tr.get("kd")) + " .\n");
            }
            m.read(new StringReader(rec.toString()), null, "TURTLE");
            UpdateAction.parseExecute(settle, m);
            Map<String, QuerySolution> got8 = new HashMap<>();
            try (QueryExecution qe = QueryExecution.create().query(cq8).model(m).build()) {
                qe.execSelect().forEachRemaining(q -> got8.put(q.getResource("offer").getLocalName(), q));
            }
            for (JsonObject o : ref.values()) if (o.hasKey("trip")) {
                trips++; JsonObject tr = o.get("trip").getAsObject(); QuerySolution q = got8.get(str(o, "id"));
                if (q == null) { fareBad++; continue; }
                if (tr.hasKey("disputed")) fareBad += q.getLiteral("disputed").getBoolean() ? 0 : 1;
                else fareBad += Math.abs(q.getLiteral("fare").getDouble() - tr.get("fare").getAsNumber().value().doubleValue()) > 1e-9 ? 1 : 0;
            }
            if (idx < 3) {       // OWL Mini is slow: three searches are enough to catch a conflict
                if (!ModelFactory.createInfModel(ReasonerRegistry.getOWLMiniReasoner(), m).validate().isValid()) owlBad++;
            }
            var rep = ShaclValidator.get().validate(shapes, m.getGraph());
            if (!rep.conforms()) { shaclBad++; if (shaclBad == 1) rep.getEntries().stream().limit(3).forEach(e -> System.out.println(e.focusNode() + " " + e.message())); }
            idx++;
        }
        JsonObject out = new JsonObject();
        out.put("engine", "Apache Jena 4.10"); out.put("searches", idx); out.put("score_mismatches", scoreBad); out.put("context_note_mismatches", noteBad);
        out.put("order_changed_by_context", moved); out.put("shacl_failures", shaclBad); out.put("personal_view_mismatches", cq7Bad); out.put("settlement_trips", trips); out.put("settlement_mismatches", fareBad); out.put("owl_inconsistent_of_3", owlBad);
        Files.writeString(Path.of("experiment/out/crosscheck_context_jena.json"), out.toString());
        System.out.println(out);
    }
    static List<String> order(Model m, String q, QuerySolutionMap init) {
        List<String> l = new ArrayList<>();
        try (QueryExecution qe = QueryExecution.create().query(q).model(m).initialBinding(init).build()) {
            qe.execSelect().forEachRemaining(r -> l.add(r.getResource("offer").getLocalName() + " " + r.getLiteral("S").getDouble()));
        }
        return l;
    }
}
