// End-to-end test of the signed publication and the independent checker (Node). Needs RankService running.
// Platform-side misbehaviour (signed by the platform): promote, reweight, other_rules.
// In-transit tampering or forgery (not signed by the platform's key): edit_price, swap_order, no_signature, impostor_key.
// Usage: node signed_check.mjs <path to oxigraph/node.js> <port>
import { readFileSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { check, importKey, FILES } from "./checker/checker.mjs";
const here = dirname(fileURLToPath(import.meta.url));
const { Store } = createRequire(import.meta.url)(process.argv[2]);
const PORT = process.argv[3] || 8765;
const src = { "ridesharing.ttl": "../../ontology/ridesharing.ttl", "rules.ru": "../../ontology/rules.ru",
  "cost_percentiles.rq": "../sparql/cost_percentiles.rq", "rationale.rq": "../sparql/rationale.rq" };
const files = Object.fromEntries(FILES.map(f => [f, readFileSync(join(here, src[f]), "utf8")]));   // the registered rules
const key = await importKey(JSON.parse(readFileSync(join(here, "../out/signed/platform_key.json"), "utf8")).spki_b64);
const imp = await crypto.subtle.generateKey({ name: "ECDSA", namedCurve: "P-256" }, false, ["sign"]);
const enc = new TextEncoder(), dec = new TextDecoder();
const med = a => { const b = [...a].sort((x, y) => x - y); return b.length ? +b[Math.floor(b.length / 2)].toFixed(3) : null; };
const res = { sets: {}, platform_key: "ECDSA P-256, SHA-256, signature over the exact response bytes" };
for (const set of ["20", "100"]) {
  const out = {}; const times = { verify: [], hash: [], recompute: [], total: [] };
  for (let i = 0; i < 40; i++) {
    for (const mode of ["honest", "promote", "reweight", "other_rules"]) {
      const r = await fetch(`http://127.0.0.1:${PORT}/publish?set=${set}&i=${i}&mode=${mode}`);
      const body = new Uint8Array(await r.arrayBuffer()), sig = r.headers.get("x-signature");
      const cases = { [mode]: [body, sig] };
      if (mode === "honest") {
        const txt = dec.decode(body), j = JSON.parse(txt);
        const ed = JSON.parse(txt); ed.listings[0].price_per_km = +(ed.listings[0].price_per_km * 0.8).toFixed(4);
        const sw = JSON.parse(txt); [sw.ranked[0], sw.ranked[1]] = [sw.ranked[1], sw.ranked[0]];
        cases.edit_price = [enc.encode(JSON.stringify(ed)), sig];
        cases.swap_order = [enc.encode(JSON.stringify(sw)), sig];
        cases.no_signature = [body, ""];
        const forged = enc.encode(JSON.stringify(sw));
        cases.impostor_key = [forged, btoa(String.fromCharCode(...new Uint8Array(await crypto.subtle.sign({ name: "ECDSA", hash: "SHA-256" }, imp.privateKey, forged))))];
      }
      for (const [k, [b, s]] of Object.entries(cases)) {
        const v = await check(b, s, key, files, Store);
        const o = out[k] ??= { n: 0, verdicts: {} }; o.n++; o.verdicts[v.verdict] = (o.verdicts[v.verdict] || 0) + 1;
        if (k === "honest") for (const m of Object.keys(times)) times[m].push(v.ms[m]);
      }
    }
  }
  res.sets[set] = { searches: 40, cases: out, honest_ms_median: Object.fromEntries(Object.entries(times).map(([m, a]) => [m, med(a)])) };
}
writeFileSync(join(here, "../out/signed_check.json"), JSON.stringify(res, null, 2));
console.log(JSON.stringify(res, null, 1));
