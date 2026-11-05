// Compares, for every check search, the rationale text the server publishes (RankService, Apache Jena,
// percentile by sorting) with the one the phone's engine builds (Oxigraph, SPARQL percentile), offer by offer.
// Usage (service running locally): node rationale_check.mjs <path to oxigraph/node.js> [port]
import { readFileSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
const here = dirname(fileURLToPath(import.meta.url));
const ox = createRequire(import.meta.url)(process.argv[2]);
const port = process.argv[3] || 8765;
const read = p => readFileSync(join(here, p), "utf8");
const TBOX = read("../../ontology/ridesharing.ttl"), COST = read("../sparql/cost_percentiles.rq"),
      RULES = read("../../ontology/rules.ru"), RAT = read("../sparql/rationale.rq");
const data = JSON.parse(read("../out/mobile_searches.json"));
const WM = "http://example.org/ridesharing#", XSD = "http://www.w3.org/2001/XMLSchema#";
let offers = 0, textDiff = 0, scoreDiff = 0, orderDiff = 0, example = null;
for (const s of data.check) {
  const st = new ox.Store(); st.load(TBOX, { format: "text/turtle" });
  st.load(s.offers.map(o => `<${WM}${o.id}> a <${WM}Travel> ; <${WM}hasMarket> "${s.market}" ; <${WM}hasSeatsAvailable> "${o.seats}"^^<${XSD}integer> ; <${WM}hasBookingMode> "${o.booking}" ; <${WM}hasPricePerKm> "${o.price_per_km}"^^<${XSD}decimal> ; <${WM}hasDistance> "${o.distance}"^^<${XSD}decimal> .`).join("\n"), { format: "text/turtle" });
  st.update(COST); st.update(RULES);
  const mine = st.query(RAT.replace("WHERE {", `WHERE {\n  VALUES ?market { "${s.market}" }`));
  const body = JSON.stringify(s.offers.map(o => ({ id: o.id.slice(5), market: s.market, seats: o.seats, booking: o.booking, price_per_km: +o.price_per_km, distance: +o.distance })));
  const r = await fetch(`http://127.0.0.1:${port}/rank`, { method: "POST", headers: { "Content-Type": "application/json" }, body });
  const pub = (await r.json()).ranked;
  const why = new Map(mine.map(x => [x.get("offer").value.split("#")[1], [x.get("rationale").value, Number(x.get("S").value)]]));
  pub.forEach((p, i) => {
    offers++; const m = why.get("trip_" + p.id);
    if (!m || m[0] !== p.rationale) { textDiff++; if (!example && m) example = { phone: m[0], server: p.rationale }; }
    if (!m || Math.abs(m[1] - p.S) > 1e-9) scoreDiff++;
    if (i > 0 && p.S > pub[i - 1].S + 1e-12) orderDiff++;
  });
}
const res = { searches: data.check.length, offers, rationale_text_mismatches: textDiff, score_mismatches: scoreDiff, order_violations: orderDiff, example_mismatch: example,
              server: "RankService (Apache Jena 4.10, percentile by sorting)", phone_engine: "Oxigraph 0.5.13 (WebAssembly, SPARQL percentile)" };
writeFileSync(join(here, "../out/rationale_check.json"), JSON.stringify(res, null, 2));
console.log(JSON.stringify(res));
