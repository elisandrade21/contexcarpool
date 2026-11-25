// Independent checker: runs unchanged in Node and in a browser page served from an origin other than the platform's.
// 1) verifies the platform's ECDSA P-256 signature over the exact bytes received, with a key obtained independently;
// 2) compares the SHA-256 of the rule files it obtained independently with the hashes the platform declared;
// 3) re-executes the rules on the signed listings with Oxigraph and compares scores, order and rationales.
const WM = "http://example.org/ridesharing#", XSD = "http://www.w3.org/2001/XMLSchema#";
const enc = new TextEncoder();
const b64 = s => Uint8Array.from(atob(s), c => c.charCodeAt(0));
const hex = buf => [...new Uint8Array(buf)].map(x => x.toString(16).padStart(2, "0")).join("");
export const FILES = ["ridesharing.ttl", "rules.ru", "cost_percentiles.rq", "rationale.rq"];

export async function importKey(spkiB64) {
  return crypto.subtle.importKey("spki", b64(spkiB64), { name: "ECDSA", namedCurve: "P-256" }, false, ["verify"]);
}
export async function check(bodyBytes, sigB64, key, files, Store) {
  const t = [performance.now()];
  let sigOk = false;
  try { sigOk = !!sigB64 && await crypto.subtle.verify({ name: "ECDSA", hash: "SHA-256" }, key, b64(sigB64), bodyBytes); } catch { sigOk = false; }
  t.push(performance.now());
  if (!sigOk) return { verdict: "rejected: bad or missing signature", sig_ok: false, ms: { verify: t[1] - t[0] } };
  const pub = JSON.parse(new TextDecoder().decode(bodyBytes));
  let rulesOk = true;
  for (const f of FILES) if (hex(await crypto.subtle.digest("SHA-256", enc.encode(files[f]))) !== pub.rules_sha256[f]) rulesOk = false;
  t.push(performance.now());
  if (!rulesOk) return { verdict: "rejected: declared rules differ from the registered rules", sig_ok: true, rules_ok: false, ms: { verify: t[1] - t[0], hash: t[2] - t[1] } };
  const st = new Store();
  st.load(files["ridesharing.ttl"], { format: "text/turtle" });
  st.load(pub.listings.map(o => `<${WM}trip_${o.id}> a <${WM}Travel> ; <${WM}hasMarket> "${o.market}" ; <${WM}hasSeatsAvailable> "${o.seats}"^^<${XSD}integer> ; <${WM}hasBookingMode> "${o.booking}" ; <${WM}hasPricePerKm> "${o.price_per_km}"^^<${XSD}decimal> .`).join("\n"), { format: "text/turtle" });
  st.update(files["cost_percentiles.rq"]); st.update(files["rules.ru"]);
  const rows = st.query(files["rationale.rq"].replace("WHERE {", `WHERE {\n  VALUES ?market { "${pub.market}" }`));
  t.push(performance.now());
  const mine = new Map(rows.map(r => [r.get("offer").value.split("#")[1].slice(5), [Number(r.get("S").value), r.get("rationale").value]]));
  const p = pub.ranked;
  const scores = p.filter(r => !mine.has(r.id) || Math.abs(mine.get(r.id)[0] - r.S) > 1e-9).length;
  const why = p.filter(r => mine.has(r.id) && mine.get(r.id)[1] !== r.rationale).length;
  let order = 0; for (let i = 1; i < p.length; i++) if (mine.get(p[i].id)?.[0] > mine.get(p[i - 1].id)?.[0] + 1e-9) order++;
  const missing = p.length !== mine.size;
  t.push(performance.now());
  const bad = scores || why || order || missing;
  return { verdict: bad ? "non-conformant (signed evidence)" : "conformant", sig_ok: true, rules_ok: true, scores, order, rationales: why, missing,
           ms: { verify: t[1] - t[0], hash: t[2] - t[1], recompute: t[3] - t[2], compare: t[4] - t[3], total: t[4] - t[0] } };
}
