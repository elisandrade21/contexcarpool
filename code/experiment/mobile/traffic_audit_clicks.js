// Pasted in the page's console (served through traffic_proxy.py) to run the audit session of out/traffic_audit/summary.json.
const W=ms=>new Promise(r=>setTimeout(r,ms));
const B=(p,t)=>[...document.querySelectorAll('#'+p+' button')].find(b=>b.textContent.trim()===t);
const tab=t=>[...document.querySelectorAll('button')].find(b=>b.textContent.trim()===t&&!b.closest('.chips'));
const btn=t=>[...document.querySelectorAll('button')].find(b=>b.textContent.trim()===t);
for(const c of ["Paris","Lyon","Recife","Rome","Lisbon","Kyiv"]){
  B('city',c).click(); await W(1500);
  for(const p of ["Current spot","1.5 km north","4 km west"]){ B('pos',p).click(); await W(600);
    for(const k of ["Now","In 2 hours","In 5 hours"]){ B('clock',k).click(); await W(600);
      for(const o of ["Public ranking","Best total cost for me"]){ B('order',o).click(); await W(500); } } }
  tab("Map").click(); await W(2500); tab("Check").click(); await W(500);
  btn("Check server ranking").click(); await W(3500); btn("Check a tampered copy").click(); await W(2500);
  btn("Compute fare on this phone").click(); await W(1500); tab("Offers").click(); await W(500);
}
