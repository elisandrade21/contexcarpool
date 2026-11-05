// Minimal stateless ranking service: POST /rank with a JSON array of the
// listings of ONE search; returns them ranked with scores, fired rules and
// rationales, plus the listings rejected by the SHACL contract.
// Run from the code root (Apache Jena 4.10, Java 11+):
//   java -cp ".tools/apache-jena-4.10.0/lib/*" experiment/service/RankService.java 8080
// Request item:  {"id":"FR-0271","market":"France","seats":4,"booking":"auto",
//                 "price_per_km":0.0361,"distance":146.8}
// To also run the context rules R9-R13, send {"context":{"lat":..,"lon":..,"cos":..,"now":..},"listings":[..]}
// with "plat", "plon" and "dep" in each listing. With a second argument (bind address) the service
// also serves experiment/mobile/web and stores phone measurements posted to /result, for the mobile tests.
import com.sun.net.httpserver.HttpServer;
import org.apache.jena.atlas.json.*;
import org.apache.jena.query.*;
import org.apache.jena.rdf.model.*;
import org.apache.jena.riot.RDFDataMgr;
import org.apache.jena.shacl.ShaclValidator;
import org.apache.jena.shacl.Shapes;
import org.apache.jena.shacl.ValidationReport;
import org.apache.jena.update.UpdateAction;
import org.apache.jena.vocabulary.RDF;
import org.apache.jena.datatypes.xsd.XSDDatatype;

import java.io.*;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.Executors;

public class RankService {
    static final String WM = "http://example.org/ridesharing#";
    static Model tbox; static Shapes shapes; static String rulesRu, rationaleQuery, contextRu, notesQuery;

    public static void main(String[] args) throws Exception {
        org.apache.jena.sys.JenaSystem.init();
        tbox = RDFDataMgr.loadModel("ontology/ridesharing.ttl");
        shapes = Shapes.parse(RDFDataMgr.loadGraph("ontology/shapes.ttl"));
        rulesRu = Files.readString(Path.of("ontology/rules.ru"));
        rationaleQuery = Files.readString(Path.of("experiment/sparql/rationale.rq"));
        contextRu = Files.readString(Path.of("ontology/rules_context.ru"));
        notesQuery = Files.readString(Path.of("experiment/sparql/cq6_context_notes.rq"));
        int port = args.length > 0 ? Integer.parseInt(args[0]) : 8080;
        String bind = args.length > 1 ? args[1] : "127.0.0.1";
        HttpServer srv = HttpServer.create(new InetSocketAddress(bind, port), 64);
        if (args.length > 1) mobileRoutes(srv);
        srv.createContext("/rank", ex -> {
            byte[] body;
            int code = 200;
            long t0 = System.nanoTime();
            try {
                if (!"POST".equals(ex.getRequestMethod())) throw new IllegalArgumentException("use POST");
                JsonValue in = JSON.parseAny(new String(ex.getRequestBody().readAllBytes(), StandardCharsets.UTF_8));
                body = (in.isArray() ? rank(in.getAsArray(), null) : rank(in.getAsObject().get("listings").getAsArray(), in.getAsObject().get("context").getAsObject()))
                        .toString().getBytes(StandardCharsets.UTF_8);
            } catch (Exception e) {
                code = 400; body = ("{\"error\":\"" + e.getMessage() + "\"}").getBytes(StandardCharsets.UTF_8);
            }
            ex.getResponseHeaders().add("Content-Type", "application/json");
            ex.getResponseHeaders().add("Server-Timing", String.format(java.util.Locale.ROOT, "rank;dur=%.1f", (System.nanoTime() - t0) / 1e6));
            ex.sendResponseHeaders(code, body.length);
            try (OutputStream os = ex.getResponseBody()) { os.write(body); }
        });
        srv.setExecutor(Executors.newFixedThreadPool(Runtime.getRuntime().availableProcessors()));
        srv.start();
        System.out.println("RankService listening on http://127.0.0.1:" + port + "/rank");
    }

    static JsonObject rank(JsonArray req, JsonObject ctx) {
        Model m = ModelFactory.createDefaultModel();
        Property seats = m.createProperty(WM + "hasSeatsAvailable"), mode = m.createProperty(WM + "hasBookingMode"),
                 ppk = m.createProperty(WM + "hasPricePerKm"), dist = m.createProperty(WM + "hasDistance"),
                 mkt = m.createProperty(WM + "hasMarket");
        String market = null;
        Set<String> markets = new HashSet<>();
        for (JsonValue v : req) {
            JsonObject o = v.getAsObject();
            if (o.hasKey("market")) markets.add(o.get("market").getAsString().value());
        }
        if (markets.size() > 1)                                     // a search is restricted to one market
            throw new IllegalArgumentException("a search must contain listings of one market, got " + markets);
        for (JsonValue v : req) {                                   // ValidateAndProject: JSON -> RDF
            JsonObject o = v.getAsObject();
            Resource a = m.createResource(WM + "trip_" + o.get("id").getAsString().value());
            a.addProperty(RDF.type, m.createResource(WM + "Travel"));
            if (o.hasKey("market")) { market = o.get("market").getAsString().value(); a.addProperty(mkt, market); }
            if (o.hasKey("seats")) a.addLiteral(seats, m.createTypedLiteral(o.get("seats").getAsNumber().value().toString(), XSDDatatype.XSDinteger));
            if (o.hasKey("booking")) a.addProperty(mode, o.get("booking").getAsString().value());
            if (o.hasKey("price_per_km")) a.addLiteral(ppk, m.createTypedLiteral(o.get("price_per_km").getAsNumber().value().toString(), XSDDatatype.XSDdecimal));
            if (o.hasKey("distance")) a.addLiteral(dist, m.createTypedLiteral(o.get("distance").getAsNumber().value().toString(), XSDDatatype.XSDdecimal));
        }
        if (ctx != null) addContext(m, req, ctx);
        JsonArray rejected = new JsonArray();                       // SHACL contract
        ValidationReport rep = ShaclValidator.get().validate(shapes, m.getGraph());
        Set<String> bad = new HashSet<>();
        rep.getEntries().forEach(en -> {
            String id = en.focusNode().getLocalName();
            if (bad.add(id)) { JsonObject r = new JsonObject(); r.put("id", id.substring(5)); r.put("violation", en.message()); rejected.add(r); }
        });
        for (String id : bad) m.removeAll(m.createResource(WM + id), null, null);
        sortPercentiles(m);                                         // CostPercentiles, O(n log n)
        m.add(tbox);
        UpdateAction.parseExecute(rulesRu, m);                      // rules R1-R8 (SPARQL 1.1 Update)
        Map<String, JsonArray> notes = new HashMap<>();
        if (ctx != null) {                                          // rules R9-R13 (rationale only)
            UpdateAction.parseExecute(contextRu, m);
            try (QueryExecution qe = QueryExecution.create().query(notesQuery).model(m).build()) {
                qe.execSelect().forEachRemaining(q -> {
                    JsonObject n = new JsonObject();
                    n.put("rule", q.getLiteral("rule").getString()); n.put("label", q.getLiteral("label").getString());
                    notes.computeIfAbsent(q.getResource("offer").getLocalName().substring(5), k -> new JsonArray()).add(n);
                });
            }
        }
        JsonArray ranked = new JsonArray();
        QuerySolutionMap init = new QuerySolutionMap();
        init.add("market", m.createLiteral(market == null ? "" : market));
        try (QueryExecution qe = QueryExecution.create().query(rationaleQuery).model(m).initialBinding(init).build()) {
            qe.execSelect().forEachRemaining(q -> {
                JsonObject r = new JsonObject();
                r.put("id", q.getResource("offer").getLocalName().substring(5));
                r.put("S", JsonNumber.value(q.getLiteral("S").getDouble()));
                r.put("f_C", JsonNumber.value(q.getLiteral("fC").getDouble()));
                r.put("f_K", JsonNumber.value(q.getLiteral("fK").getDouble()));
                r.put("f_B", JsonNumber.value(q.getLiteral("fB").getDouble()));
                r.put("comfort_rule", q.getLiteral("rule").getString());
                if (q.contains("tradeRule")) r.put("tradeoff_rule", q.getLiteral("tradeRule").getString());
                r.put("rationale", q.getLiteral("rationale").getString());
                if (ctx != null) r.put("notes", notes.getOrDefault(r.getString("id"), new JsonArray()));
                ranked.add(r);
            });
        }
        JsonObject out = new JsonObject();
        out.put("ranked", ranked); out.put("rejected", rejected);
        return out;
    }

    static void addContext(Model m, JsonArray req, JsonObject c) {
        String sch = "https://schema.org/";
        Property lat = m.createProperty(sch + "latitude"), lon = m.createProperty(sch + "longitude");
        Resource d = m.createResource(WM + "device");
        d.addProperty(RDF.type, m.createResource(WM + "DeviceContext"));
        d.addLiteral(lat, dec(m, c.get("lat"))); d.addLiteral(lon, dec(m, c.get("lon")));
        d.addLiteral(m.createProperty(WM + "hasCosLatitude"), dec(m, c.get("cos")));
        d.addLiteral(m.createProperty(WM + "hasNowMinute"), m.createTypedLiteral(c.get("now").getAsNumber().value().toString(), XSDDatatype.XSDinteger));
        for (JsonValue v : req) {
            JsonObject o = v.getAsObject();
            String id = o.get("id").getAsString().value();
            Resource p = m.createResource(WM + "trip_" + id + "-pickup");
            p.addProperty(RDF.type, m.createResource(WM + "Place"));
            p.addLiteral(lat, dec(m, o.get("plat"))); p.addLiteral(lon, dec(m, o.get("plon")));
            m.createResource(WM + "trip_" + id).addProperty(m.createProperty(WM + "hasPickup"), p)
             .addLiteral(m.createProperty(WM + "hasDepartureMinute"), m.createTypedLiteral(o.get("dep").getAsNumber().value().toString(), XSDDatatype.XSDinteger));
        }
    }
    static Literal dec(Model m, JsonValue v) { return m.createTypedLiteral(v.getAsNumber().value().toString(), XSDDatatype.XSDdecimal); }

    // Mobile tests only: the page, its files, and a drop box for the phone's measurements.
    static void mobileRoutes(HttpServer srv) throws IOException {
        Path web = Path.of("experiment/mobile/web").toAbsolutePath().normalize();
        Path runs = Path.of("experiment/out/mobile_runs"); Files.createDirectories(runs);
        Map<String, String> mime = Map.of("html", "text/html", "js", "text/javascript", "wasm", "application/wasm", "json", "application/json", "css", "text/css");
        srv.createContext("/", ex -> {
            String rel = ex.getRequestURI().getPath().equals("/") ? "index.html" : ex.getRequestURI().getPath().substring(1);
            Path f = web.resolve(rel).normalize();
            boolean ok = f.startsWith(web) && Files.isRegularFile(f);
            byte[] body = ok ? Files.readAllBytes(f) : new byte[0];
            String ext = rel.substring(rel.lastIndexOf('.') + 1);
            ex.getResponseHeaders().add("Content-Type", mime.getOrDefault(ext, "text/plain"));
            ex.getResponseHeaders().add("Cache-Control", (ext.equals("wasm") || rel.equals("web.js") || rel.startsWith("leaflet")) ? "max-age=86400" : "no-cache");   // rules and data always revalidated
            ex.sendResponseHeaders(ok ? 200 : 404, ok ? body.length : -1);
            try (OutputStream os = ex.getResponseBody()) { os.write(body); }
        });
        srv.createContext("/result", ex -> {
            byte[] in = ex.getRequestBody().readNBytes(262144);
            int code = "POST".equals(ex.getRequestMethod()) && in.length > 0 ? 204 : 400;
            if (code == 204) { JSON.parseAny(new String(in, StandardCharsets.UTF_8)); Files.write(runs.resolve(System.currentTimeMillis() + ".json"), in); }
            ex.sendResponseHeaders(code, -1); ex.close();
        });
        srv.createContext("/echo", ex -> { ex.getRequestBody().readAllBytes(); ex.sendResponseHeaders(204, -1); ex.close(); });
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

}
