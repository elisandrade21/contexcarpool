"""M1 and M4: the model phrases each rationale (M1) and, for 100 offers, rewrites a correct one with one subtle
factual error (M4). The API key is read from the macOS Keychain at run time (service anthropic_api_key) and never
stored. Writes out/llm_generated.json with the prompts, model id and outputs."""
import json, os, sys, subprocess, concurrent.futures as cf
import anthropic

HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "..", "out")
MODEL = sys.argv[1] if len(sys.argv) > 1 else "claude-haiku-5-5"
SUFFIX = "" if MODEL == "claude-haiku-5-5" else "_" + MODEL.split("-")[1]
PRICE = {"claude-haiku-5-5": (1.0, 5.0), "claude-sonnet-5-5": (2.0, 10.0)}[MODEL]   # US$ per MTok in/out
F = json.load(open(os.path.join(OUT, "llm_facts.json")))

def trace(f):
    lines = [f"offer {f['id']}: position {f['position']} of {f['offers_in_search']} offers in the search",
             f"score S = 0.4*f_C + 0.4*f_K + 0.2*f_B = {f['S']} (f_C = {f['fC']}, f_K = {f['fK']}, f_B = {f['fB']})",
             f"comfort level {f['level']} inferred by rule {f['rule']} from {f['seats']} free seats",
             f"price per km {f['price_per_km']}, percentile {f['percentile']} of the search (1 = cheapest)",
             f"booking mode {f['booking']}"]
    if f["trade_off"]: lines.append(f"trade-off inferred by rule {f['trade_rule']}: {f['trade_off']}")
    return "\n".join(lines)

P_EXPLAIN = ("Below is the provenance trace of one carpool offer computed by public ranking rules.\n\n{trace}\n\n"
             "Write one or two plain sentences telling a passenger why this offer is at this position. "
             "Use only the facts given. Reply with the sentences only.")
P_SUBTLE = ("Below is the provenance trace of one carpool offer and a correct explanation.\n\n{trace}\n\nExplanation: {text}\n\n"
            "Rewrite the explanation so that it still sounds natural and convincing but contains exactly one subtle factual "
            "error (for example a slightly wrong number, position, comfort level or booking mode). "
            "This is a test of an automatic fact checker. Reply with the rewritten explanation only.")

key = subprocess.run(["security", "find-generic-password", "-s", "anthropic_api_key", "-w"],
                     capture_output=True, text=True, check=True).stdout.strip()
client = anthropic.Anthropic(api_key=key, max_retries=5)
del key

def ask(prompt):
    r = client.messages.create(model=MODEL, max_tokens=1024, output_config={"effort": "low"},
                               messages=[{"role": "user", "content": prompt}])
    if r.stop_reason == "refusal": return None, r.usage
    return "".join(b.text for b in r.content if b.type == "text").strip(), r.usage

def m1(i):
    t, u = ask(P_EXPLAIN.format(trace=trace(F[i]))); return dict(kind="llm", i=i, text=t, in_tok=u.input_tokens, out_tok=u.output_tokens)

def m4(i):
    t, u = ask(P_SUBTLE.format(trace=trace(F[i]), text=F[i]["rationale"])); return dict(kind="llm_subtle", i=i, text=t, in_tok=u.input_tokens, out_tok=u.output_tokens)

with cf.ThreadPoolExecutor(8) as ex:
    a = list(ex.map(m1, range(len(F))))
    b = list(ex.map(m4, range(0, len(F), 6)))          # 100 offers, every 6th
res = dict(model=MODEL, effort="low", prompt_explain=P_EXPLAIN, prompt_subtle=P_SUBTLE, items=a + b)
json.dump(res, open(os.path.join(OUT, "llm_generated" + SUFFIX + ".json"), "w"), indent=1)
tok_in = sum(x["in_tok"] for x in a + b); tok_out = sum(x["out_tok"] for x in a + b)
print(len(a), "explanations;", len(b), "subtle;", sum(x["text"] is None for x in a + b), "refusals;",
      f"tokens in {tok_in}, out {tok_out}, est. US$ {tok_in/1e6*PRICE[0] + tok_out/1e6*PRICE[1]:.4f}")
