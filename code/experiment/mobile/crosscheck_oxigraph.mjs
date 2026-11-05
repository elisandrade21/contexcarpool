// Third-engine check: runs the SAME SPARQL files (cost percentiles, rules R1-R8, CQ1)
// in Oxigraph (WebAssembly build, Node) and compares with the reference answers.
// Usage: node crosscheck_oxigraph.mjs <path to oxigraph/node.js>
import { readFileSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const ox = createRequire(import.meta.url)(process.argv[2]);
const read = p => readFileSync(join(here, p), "utf8");
const COST = read("../sparql/cost_percentiles.rq");
const RULES = read("../../ontology/rules.ru");
const RATIONALE = read("../sparql/rationale.rq");
const CONTEXT = read("../../ontology/rules_context.ru");
const NOTES = read("../sparql/cq6_context_notes.rq");
const SETTLE = read("../../ontology/rules_settlement.ru");
const CQ8 = read("../sparql/cq8_settlement.rq");
const TBOX = read("../../ontology/ridesharing.ttl");
const data = JSON.parse(read("../out/mobile_searches.json"));
const WM = "http://example.org/ridesharing#";
const XSD = "http://www.w3.org/2001/XMLSchema#";
const SCH = "https://schema.org/";

function triples(s) {
  return s.offers.map(o => {
    const a = `<${WM}${o.id}>`;
    return `${a} a <${WM}Travel> ; <${WM}hasMarket> "${s.market}" ; ` +
      `<${WM}hasSeatsAvailable> "${o.seats}"^^<${XSD}integer> ; <${WM}hasBookingMode> "${o.booking}" ; ` +
      `<${WM}hasPricePerKm> "${o.price_per_km}"^^<${XSD}decimal> ; <${WM}hasDistance> "${o.distance}"^^<${XSD}decimal> .`;
  }).join("\n") + "\n" + contextTriples(s);
}
function contextTriples(s) {
  if (!s.context) return "";
  const c = s.context, dec = v => `"${v}"^^<${XSD}decimal>`;
  return `<${WM}device> a <${WM}DeviceContext> ; <${SCH}latitude> ${dec(c.lat)} ; <${SCH}longitude> ${dec(c.lon)} ; ` +
    `<${WM}hasCosLatitude> ${dec(c.cos)} ; <${WM}hasNowMinute> "${c.now}"^^<${XSD}integer> .\n` +
    s.offers.map(o => `<${WM}${o.id}> <${WM}hasDepartureMinute> "${o.dep}"^^<${XSD}integer> ; <${WM}hasPickup> <${WM}${o.id}-pickup> .\n` +
      `<${WM}${o.id}-pickup> a <${WM}Place> ; <${SCH}latitude> ${dec(o.plat)} ; <${SCH}longitude> ${dec(o.plon)} .`).join("\n");
}
function run(s) {
  const st = new ox.Store();
  st.load(TBOX, { format: "text/turtle" });
  st.load(triples(s), { format: "text/turtle" });
  const q = RATIONALE.replace("WHERE {", `WHERE {\n  VALUES ?market { "${s.market}" }`);
  const t0 = performance.now();
  st.update(COST);
  const t1 = performance.now();
  st.update(RULES);
  const t2 = performance.now();
  const rows = st.query(q);
  const t3 = performance.now();
  st.update(CONTEXT);
  const notes = st.query(NOTES);
  const t4 = performance.now();
  const after = st.query(q);
  return { rows, notes, after, cost: t1 - t0, rules: t2 - t1, rank: t3 - t2, context: t4 - t3, total: t4 - t0 };
}
const med = a => { const b = [...a].sort((x, y) => x - y); return b[Math.floor(b.length / 2)]; };

let score = 0, rule = 0, trade = 0, order = 0, count = 0, note = 0, moved = 0, fare = 0, trips = 0;
function settle(s) {
  const st = new ox.Store();
  st.load(TBOX, { format: "text/turtle" }); st.load(triples(s), { format: "text/turtle" });
  let t = "";
  for (const o of s.offers) if (o.trip) {
    for (const [who, k] of [["passenger", o.trip.kp], ["driver", o.trip.kd]])
      t += `<${WM}${o.id}-rec-${who}> a <${WM}TripRecord> ; <${WM}ofOffer> <${WM}${o.id}> ; <${WM}recordedBy> "${who}" ; <${WM}hasTravelledKm> "${k}"^^<${XSD}decimal> .\n`;
  }
  st.load(t, { format: "text/turtle" }); st.update(SETTLE);
  return st.query(CQ8);
}
for (const s of data.check) {
  const { rows, notes, after } = run(s);
  const got8 = new Map(settle(s).map(r => [r.get("offer").value.split("#")[1], r]));
  for (const o of s.offers) if (o.trip) {
    trips++; const r = got8.get(o.id);
    if (!r) { fare++; continue; }
    if (o.trip.disputed) fare += r.get("disputed").value !== "true";
    else fare += Math.abs(Number(r.get("fare").value) - o.trip.fare) > 1e-9;
  }
  const got = new Map(s.offers.map(o => [o.id, []]));
  for (const n of notes) got.get(n.get("offer").value.split("#")[1]).push(n.get("rule").value);
  for (const o of s.offers) note += [...got.get(o.id)].sort().join() !== [...o.notes].sort().join();
  rows.forEach((r, i) => { moved += r.get("offer").value !== after[i].get("offer").value || r.get("S").value !== after[i].get("S").value; });
  const ref = new Map(s.offers.map(o => [o.id, o]));
  count += rows.length !== s.offers.length;
  const refS = s.offers.map(o => o.S).sort((a, b) => b - a);
  let prev = Infinity;
  rows.forEach((r, i) => {
    const o = ref.get(r.get("offer").value.split("#")[1]);
    const S = Number(r.get("S").value);
    score += Math.abs(S - o.S) > 1e-9;
    rule += r.get("rule").value !== o.rule;
    trade += (r.get("tradeRule")?.value ?? null) !== o.trade;
    order += S > prev + 1e-12 || Math.abs(S - refS[i]) > 1e-9;
    prev = S;
  });
}
const lat = {};
for (const [n, list] of Object.entries(data.latency)) {
  for (const s of list.slice(0, 2)) run(s);          // warm-up
  const rs = [];
  const reps = n === "1000" ? 3 : 30;
  for (let i = 0; i < reps; i++) rs.push(run(list[i % list.length]));
  lat[n] = Object.fromEntries(["cost", "rules", "rank", "context", "total"].map(k => [k + "_ms", +med(rs.map(r => r[k])).toFixed(1)]));
}
const res = { engine: "Oxigraph 0.5.13 (WebAssembly, Node " + process.version + ")", searches: data.check.length, offers_per_search: 100,
  row_count_mismatches: count, score_mismatches: score, rule_mismatches: rule, tradeoff_mismatches: trade, order_violations: order, context_note_mismatches: note, order_changed_by_context: moved, settlement_trips: trips, settlement_mismatches: fare, latency: lat };
writeFileSync(join(here, "../out/crosscheck_oxigraph.json"), JSON.stringify(res, null, 2));
console.log(JSON.stringify(res, null, 2));
