// Facts of 600 offers (stratified sample of the 6,600 check offers), computed by the phone engine (Oxigraph).
// Usage: node facts.mjs <path to oxigraph/node.js>   -> out/llm_facts.json
import { readFileSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
const here = dirname(fileURLToPath(import.meta.url));
const ox = createRequire(import.meta.url)(process.argv[2]);
const read = p => readFileSync(join(here, p), "utf8");
const TBOX = read("../../ontology/ridesharing.ttl"), COST = read("../sparql/cost_percentiles.rq"),
      RULES = read("../../ontology/rules.ru"), RAT = read("../sparql/rationale.rq");
const data = JSON.parse(read("../out/mobile_searches.json"));
const WM = "http://example.org/ridesharing#", XSD = "http://www.w3.org/2001/XMLSchema#";
let seed = 20261123; const rnd = () => (seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648;
const out = [];
data.check.forEach((s, si) => {
  const st = new ox.Store(); st.load(TBOX, { format: "text/turtle" });
  st.load(s.offers.map(o => `<${WM}${o.id}> a <${WM}Travel> ; <${WM}hasMarket> "${s.market}" ; <${WM}hasSeatsAvailable> "${o.seats}"^^<${XSD}integer> ; <${WM}hasBookingMode> "${o.booking}" ; <${WM}hasPricePerKm> "${o.price_per_km}"^^<${XSD}decimal> ; <${WM}hasDistance> "${o.distance}"^^<${XSD}decimal> .`).join("\n"), { format: "text/turtle" });
  st.update(COST); st.update(RULES);
  const rows = st.query(RAT.replace("WHERE {", `WHERE {\n  VALUES ?market { "${s.market}" }`));
  const byId = new Map(s.offers.map(o => [o.id, o]));
  const k = si < 60 ? 7 : 6;                       // 60*7 + 30*6 = 600
  const idx = [...rows.keys()].sort(() => rnd() - 0.5).slice(0, k).sort((a, b) => a - b);
  for (const i of idx) {
    const r = rows[i], id = r.get("offer").value.split("#")[1], o = byId.get(id), fK = Number(r.get("fK").value);
    out.push({ search: si, id, position: i + 1, offers_in_search: rows.length, S: Number(r.get("S").value),
      fC: Number(r.get("fC").value), fK, fB: Number(r.get("fB").value),
      level: r.get("level").value.split("#")[1], rule: r.get("rule").value,
      percentile: Math.round(100 - 10 * fK + 1e-6), booking: r.get("mode").value,
      seats: Number(o.seats), price_per_km: Number(o.price_per_km),
      trade_off: r.get("tradeLabel") ? r.get("tradeLabel").value : null, trade_rule: r.get("tradeRule") ? r.get("tradeRule").value : null,
      rationale: r.get("rationale").value });
  }
});
writeFileSync(join(here, "../out/llm_facts.json"), JSON.stringify(out, null, 1));
console.log(out.length, "offers;", new Set(out.map(x => x.search)).size, "searches");
