// M5 and M6: runs the JS checker on every text file given, compares with the Python verdicts, and times it.
// Usage: node agree.mjs <texts.json> <python_verdicts.json>
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { check } from "./checker.mjs";
const here = dirname(fileURLToPath(import.meta.url));
const F = JSON.parse(readFileSync(join(here, "../out/llm_facts.json"), "utf8"));
const T = JSON.parse(readFileSync(process.argv[2], "utf8")), P = JSON.parse(readFileSync(process.argv[3], "utf8"));
let agree = 0; const t0 = performance.now();
const js = T.map(x => check(x.text, F[x.i])[0]);
const ms = performance.now() - t0;
js.forEach((v, k) => { if (v === P[k]) agree++; });
console.log(JSON.stringify({ texts: T.length, agree, disagree: T.length - agree, ms_per_100_texts: +(ms / T.length * 100).toFixed(3) }));
