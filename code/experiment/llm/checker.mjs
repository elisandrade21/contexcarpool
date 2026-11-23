// Phone-side checker (JavaScript), written separately from checker.py. Same rules (PROTOCOL_2026-11-23.md).
const LEVELS = [["very comfortable", "VeryComfortable"], ["uncomfortable", "Uncomfortable"],
                ["comfortable", "Comfortable"], ["bearable", "Bearable"]];
const WEIGHTS = [0.4, 0.2, 40, 20];
const round = (x, d) => { const p = 10 ** d; return Math.round(Number((x * p).toPrecision(12))) / p; };   // half-up
const ROLES = [   // same order as checker.py
  [/\b(\d+(?:\.\d+)?)(?:st|nd|rd|th)?\s+(?:price\s+)?percentile/gi, "percentile"],
  [/percentile(?: rank)?(?: of)?\s+(\d+(?:\.\d+)?)/gi, "percentile"],
  [/\b\d+(?:st|nd|rd|th)\s+(?:of|out of)\s+(\d+)(?![\d.])/gi, "offers_in_search"],
  [/(?:ranked|ranks|rank|position|place|placed)\s*#?\d+\s+(?:of|out of)\s+(\d+)(?![\d.])/gi, "offers_in_search"],
  [/(?:of|out of)\s+(\d+)\s+(?:offers|options|results|trips|rides)/gi, "offers_in_search"],
  [/(\d+)\s+(?:offers|options|results)\b/gi, "offers_in_search"],
  [/(?:ranked|ranks|rank|position|place|placed)\s*(?:#|no\.?\s*)?(\d+)(?![\d.])/gi, "position"],
  [/\b(\d+)(?:st|nd|rd|th)\b/gi, "position"],
  [/(?:score|\bS)\s*(?:of|=|is|:)?\s*(\d+(?:\.\d+)?)/gi, "S"],
  [/(\d+)\s+(?:free\s+|available\s+|empty\s+|open\s+)?seats?/gi, "seats"],
  [/(\d+(?:\.\d+)?)\s*(?:€|eur|euros?|r\$|\$|brl|uah)?\s*(?:per|\/)\s*km/gi, "price_per_km"],
  [/(?:€|r\$|\$)\s*(\d+(?:\.\d+)?)/gi, "price_per_km"],
];

const LEGEND = /\(?\s*(?:where|with)?\s*(?:percentile\s+)?1\s*(?:=|is|means|being)\s*(?:the\s+)?cheapest\s*\)?/gi;
const STRIP = [/trip_[A-Z]+-\d+/gi, /\bout of 10\b/gi, /\bnot\s+(?:among\s+)?(?:the\s+)?(?:cheapest|most expensive)\b/gi];
export function check(text, f) {
  text = text.replace(LEGEND, " ");   // echo of the legend given in the prompt, not a claim
  for (const p of STRIP) text = text.replace(p, " ");   // offer ids, the 0-10 scale, negated extremes
  const low = text.toLowerCase(), why = [];
  const okRules = new Set([f.rule, f.trade_rule].filter(Boolean));
  for (const m of text.matchAll(/\bR(\d{1,2})\b/g)) if (!okRules.has("R" + m[1])) why.push("rule R" + m[1]);
  let body = text.replace(/\bR\d{1,2}\b/g, " ");
  for (const [re, key] of ROLES) {
    for (const m of [...body.matchAll(re)]) {
      const tok = m[1], d = tok.includes(".") ? tok.split(".")[1].length : 0;
      const vals = key === "S" ? [f.S, f.fC, f.fK, f.fB] : [f[key]];   // "score" may name a factor score
      if (vals.every(v => round(Number(tok), d) !== round(v, d))) why.push(key + " " + tok);
      const s = m.index + m[0].lastIndexOf(tok); body = body.slice(0, s) + " ".repeat(tok.length) + body.slice(s + tok.length);
    }
  }
  const facts = [f.position, f.offers_in_search, f.S, f.fC, f.fK, f.fB, f.percentile, f.seats, f.price_per_km, ...WEIGHTS];
  for (const m of body.matchAll(/(?<![\w.])\d+(?:,\d{3})*(?:\.\d+)?/g)) {
    const t = m[0].replace(/,/g, ""), d = t.includes(".") ? t.split(".")[1].length : 0, x = Number(t);
    if (!facts.some(a => round(a, d) === round(x, d))) why.push("number " + m[0]);
  }
  let rest = low;
  for (const [phrase, lab] of LEVELS) {
    const re = new RegExp("\\b" + phrase + "\\b", "g");
    if (re.test(rest)) { if (lab !== f.level) why.push("level " + phrase); rest = rest.replace(re, " "); }
  }
  if (/\b(automatic|instant|instantly)\b/.test(low) && f.booking !== "auto") why.push("booking automatic");
  if (/\b(manual|approval|approve)\b/.test(low) && f.booking !== "manual") why.push("booking manual");
  if (/\bcheapest\b/.test(low) && f.percentile > 25) why.push("cheapest");
  if (/\b(most expensive|priciest)\b/.test(low) && f.percentile < 75) why.push("most expensive");
  return [why.length === 0, why];
}
