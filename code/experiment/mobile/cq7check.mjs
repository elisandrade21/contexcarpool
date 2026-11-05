// Checks CQ7 in Oxigraph against a reference built from the stored answers (R12 notes and S).
import { readFileSync } from "node:fs"; import { createRequire } from "node:module";
const ox=createRequire(import.meta.url)(process.argv[2]); const R=p=>readFileSync(p,"utf8");
const d=JSON.parse(R("experiment/out/mobile_searches.json"));
const WM="http://example.org/ridesharing#",X="http://www.w3.org/2001/XMLSchema#",S="https://schema.org/",dec=v=>`"${v}"^^<${X}decimal>`,int=v=>`"${v}"^^<${X}integer>`;
const T=R("ontology/ridesharing.ttl"),COST=R("experiment/sparql/cost_percentiles.rq"),RU=R("ontology/rules.ru"),CTX=R("ontology/rules_context.ru"),Q=R("experiment/sparql/cq7_personal_view.rq");
const tier=(o,c)=>o.dep<c.now?2:o.notes.includes("R13")?1:(o.notes.includes("R12")||o.notes.includes("R10"))?2:0;
let bad=0,moved=0,tot=0,searches=0;
for(const s of d.check){searches++;const c=s.context;const st=new ox.Store();st.load(T,{format:"text/turtle"});
 let t=`<${WM}device> a <${WM}DeviceContext> ; <${S}latitude> ${dec(c.lat)} ; <${S}longitude> ${dec(c.lon)} ; <${WM}hasCosLatitude> ${dec(c.cos)} ; <${WM}hasNowMinute> ${int(c.now)} .\n`;
 for(const o of s.offers)t+=`<${WM}${o.id}> a <${WM}Travel> ; <${WM}hasMarket> "${s.market}" ; <${WM}hasSeatsAvailable> ${int(o.seats)} ; <${WM}hasBookingMode> "${o.booking}" ; <${WM}hasPricePerKm> ${dec(o.price_per_km)} ; <${WM}hasDepartureMinute> ${int(o.dep)} ; <${WM}hasPickup> <${WM}${o.id}-p> .\n<${WM}${o.id}-p> a <${WM}Place> ; <${S}latitude> ${dec(o.plat)} ; <${S}longitude> ${dec(o.plon)} .\n`;
 st.load(t,{format:"text/turtle"});st.update(COST);st.update(RU);st.update(CTX);
 const got=st.query(Q).map(r=>r.get("offer").value.split("#")[1]);
 const ref=[...s.offers].map(o=>({id:o.id,S:o.S,b:tier(o,c)})).sort((a,b)=>a.b-b.b||b.S-a.S||(a.id<b.id?-1:1)).map(o=>o.id);
 const pub=[...s.offers].sort((a,b)=>b.S-a.S||(a.id<b.id?-1:1)).map(o=>o.id);
 // ties in S may be ordered differently; compare blocked sets and S sequence instead of ids where S ties
 const sOf=new Map(s.offers.map(o=>[o.id,o])); const key=id=>{const o=sOf.get(id);return tier(o,c)+":"+o.S.toFixed(9);};
 bad+=got.map(key).join()!==ref.map(key).join();
 moved+=s.offers.filter(o=>tier(o,c)>0).length; tot+=s.offers.length;}
const real=d.check.filter(s=>s.source==="registry");let mr=0,tr=0;for(const s of real){mr+=s.offers.filter(o=>tier(o,s.context)>0).length;tr+=s.offers.length;}
console.log(JSON.stringify({searches,mismatching_searches:bad,offers_moved_down_pct:+(100*moved/tot).toFixed(1),real_registry_moved_down_pct:+(100*mr/tr).toFixed(1)}));
