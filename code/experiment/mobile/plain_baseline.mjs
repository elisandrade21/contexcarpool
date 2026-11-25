// Baseline without the standards: the same declared rule (comfort from seats, within-search cost percentile,
// booking mode; S = 0.4 fC + 0.4 fK + 0.2 fB) in plain JavaScript, against the Oxigraph path that runs the
// published SPARQL files. Same searches as the phone test (20, 100 and 1,000 offers). Plain code gives the
// order and scores only: no rationale, no provenance, and a rule change needs a code release.
// Usage: node plain_baseline.mjs <path to oxigraph/node.js>
import { readFileSync, writeFileSync, statSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
const here = dirname(fileURLToPath(import.meta.url));
const oxPath = process.argv[2];
const ox = createRequire(import.meta.url)(oxPath);
const read = p => readFileSync(join(here, p), "utf8");
const [TBOX, COST, RULES, RAT] = ["../../ontology/ridesharing.ttl", "../sparql/cost_percentiles.rq", "../../ontology/rules.ru", "../sparql/rationale.rq"].map(read);
const data = JSON.parse(read("../out/mobile_searches.json"));
const WM = "http://example.org/ridesharing#", XSD = "http://www.w3.org/2001/XMLSchema#";

export function plainRank(offers) {
  const n = offers.length, p = offers.map(o => +o.price_per_km), sorted = [...p].sort((a, b) => a - b);
  const lower = x => { let l = 0, h = n; while (l < h) { const k = (l + h) >> 1; if (sorted[k] < x) l = k + 1; else h = k; } return l; };
  const upper = x => { let l = 0, h = n; while (l < h) { const k = (l + h) >> 1; if (sorted[k] <= x) l = k + 1; else h = k; } return l; };
  const out = offers.map((o, i) => {
    const lo = lower(p[i]), eq = upper(p[i]) - lo;
    const fK = 10 * (1 - (lo + (eq + 1) / 2) / n);
    const fC = o.seats >= 4 ? 10 : o.seats === 3 ? 7.5 : o.seats === 2 ? 5 : 2.5;
    const fB = o.booking === "auto" ? 10 : 2.5;
    return { id: o.id, S: 0.4 * fC + 0.4 * fK + 0.2 * fB };
  });
  return out.sort((a, b) => b.S - a.S || (a.id < b.id ? -1 : 1));
}
function oxRank(s) {
  const st = new ox.Store();
  st.load(TBOX, { format: "text/turtle" });
  st.load(s.offers.map(o => `<${WM}${o.id}> a <${WM}Travel> ; <${WM}hasMarket> "${s.market}" ; <${WM}hasSeatsAvailable> "${o.seats}"^^<${XSD}integer> ; <${WM}hasBookingMode> "${o.booking}" ; <${WM}hasPricePerKm> "${o.price_per_km}"^^<${XSD}decimal> .`).join("\n"), { format: "text/turtle" });
  st.update(COST); st.update(RULES);
  return st.query(RAT.replace("WHERE {", `WHERE {\n  VALUES ?market { "${s.market}" }`)).map(r => ({ id: r.get("offer").value.split("#")[1], S: +r.get("S").value }));
}
const med = a => { const b = [...a].sort((x, y) => x - y); return b[Math.floor(b.length / 2)]; };
const res = { engine: "Node " + process.version + ", laptop", repetitions: 5, sizes: {} };
for (const size of ["20", "100", "1000"]) {
  const searches = data.latency[size]; let diffS = 0, diffOrder = 0; const tp = [], to = [];
  for (const s of searches) {
    for (let r = 0; r < 5; r++) {
      let t = performance.now(); const a = plainRank(s.offers); tp.push(performance.now() - t);
      t = performance.now(); const b = oxRank(s); to.push(performance.now() - t);
      if (r === 0) {
        const m = new Map(b.map(x => [x.id, x.S]));
        diffS += a.filter(x => Math.abs(m.get(x.id) - x.S) > 1e-9).length;
        diffOrder += a.filter((x, i) => b[i].id !== x.id && Math.abs(b[i].S - x.S) > 1e-9).length;
      }
    }
  }
  res.sizes[size] = { searches: searches.length, score_differences: diffS, order_differences: diffOrder,
    plain_ms_median: +med(tp).toFixed(3), oxigraph_ms_median: +med(to).toFixed(2), ratio: +(med(to) / med(tp)).toFixed(0) };
}
const ob = dirname(oxPath);
res.bytes = { oxigraph_wasm: statSync(join(ob, "web_bg.wasm")).size, oxigraph_js: statSync(join(ob, "web.js")).size,
  rules_and_queries: [COST, RULES, RAT].reduce((a, x) => a + Buffer.byteLength(x), 0), ontology: Buffer.byteLength(TBOX),
  plain_rank_function: Buffer.byteLength(plainRank.toString()) };
writeFileSync(join(here, "../out/plain_baseline.json"), JSON.stringify(res, null, 2));
console.log(JSON.stringify(res, null, 1));
