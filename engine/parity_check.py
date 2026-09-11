#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""파이썬 엔진(predict.py)과 앱 JS 엔진이 같은 답을 내는지 대조한다.
엔진을 고칠 때마다 돌려라. 어긋나면 예측 기록과 화면이 달라진다.

    python3 parity_check.py
"""
import json, os, re, subprocess, sys, tempfile
import predict as P

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(os.path.dirname(HERE), "totoscanner.html")

CASES = [
  {"name":"아스널-에버턴 (승무패 배당 있음)","matches":[
    {"no":1,"league":"E0","home":"Arsenal","away":"Everton","kick":"2026-09-12T23:00","market":"1X2","line":None,"betman":[1.40,4.30,7.00],"ref":[1.36,5.20,9.50]},
    {"no":2,"league":"E0","home":"Arsenal","away":"Everton","kick":"2026-09-12T23:00","market":"HANDICAP","line":-1,"betman":[2.30,3.60,2.75],"ref":None},
    {"no":3,"league":"E0","home":"Arsenal","away":"Everton","kick":"2026-09-12T23:00","market":"OU","line":2.5,"betman":[1.95,1.75],"ref":[2.05,1.80]},
    {"no":4,"league":"E0","home":"Arsenal","away":"Everton","kick":"2026-09-12T23:00","market":"SUM","line":None,"betman":[1.81,1.79],"ref":None}]},
  {"name":"레알-오사수나 (승무패만)","matches":[
    {"no":5,"league":"SP1","home":"Real Madrid","away":"Osasuna","kick":"2026-09-13T04:00","market":"1X2","line":None,"betman":[1.25,4.80,9.00],"ref":[1.28,6.00,11.0]},
    {"no":6,"league":"SP1","home":"Real Madrid","away":"Osasuna","kick":"2026-09-13T04:00","market":"HANDICAP","line":-2,"betman":[2.60,3.90,2.20],"ref":None}]},
  {"name":"모델 단독 (해외 배당 없음)","matches":[
    {"no":7,"league":"D1","home":"Union Berlin","away":"Schalke 04","kick":"2026-09-12T03:30","market":"1X2","line":None,"betman":[1.75,3.60,4.20],"ref":None}]},
]

JS_RUNNER = r"""
const fs=require('fs');
const s=fs.readFileSync(process.argv[2],'utf8');
const js=s.match(/<script>([\s\S]*)<\/script>/)[1];
const i=js.indexOf('/* ═══════════════ 상태 ═══════════════ */');
eval(js.slice(0,i));
global.ST={devig:'power',wMkt:1,zeroEven:true};
const cases=JSON.parse(fs.readFileSync(process.argv[3],'utf8'));
const out=[];
for(const c of cases){
  const groups={};
  for(const m of c.matches){
    const k=[m.league,m.home,m.away,(m.kick||'').slice(0,10)].join('|');
    (groups[k]=groups[k]||{league:m.league,home:m.home,away:m.away,rows:[]}).rows.push(m);
  }
  for(const G of Object.values(groups)){
    const B=buildMatrix(G);
    for(const m of G.rows){
      m._B=B; const r=evaluate(m);
      if(r.error) continue;
      r.picks.forEach(p=>{ if(p.odds==null) return;
        out.push({no:m.no,market:m.market,sel:p.i,p:+p.p.toFixed(5),ev:+p.ev.toFixed(5),
                  evLo:+p.evLo.toFixed(5),grade:p.grade,source:r.source,derived:!!r.derived}); });
    }
  }
}
console.log(JSON.stringify(out));
"""

def main():
    with tempfile.TemporaryDirectory() as td:
        runner = os.path.join(td, "r.js"); open(runner, "w").write(JS_RUNNER)
        cj = os.path.join(td, "c.json"); json.dump(CASES, open(cj, "w"), ensure_ascii=False)
        try:
            raw = subprocess.run(["node", runner, APP, cj], capture_output=True, text=True, timeout=90)
        except FileNotFoundError:
            print("node 가 없어 대조를 건너뛴다."); return 0
        if raw.returncode:
            print("JS 실행 실패:\n" + raw.stderr[:600]); return 1
        js = json.loads(raw.stdout)

    py = []
    for c in CASES:
        py += P.predict_round({"matches": c["matches"]})
    key = lambda r: (r["no"], r["market"], r["sel"])
    jm = {key(r): r for r in js}
    bad = 0
    print("파이썬 엔진 ↔ 앱 JS 엔진 대조  (%d개 픽)" % len(py))
    for r in py:
        j = jm.get(key(r))
        if not j:
            print("  ✗ JS 에 없음:", key(r)); bad += 1; continue
        dp, de = abs(r["p"]-j["p"]), abs(r["ev"]-j["ev"])
        same = dp < 2e-4 and de < 5e-4 and r["grade"] == j["grade"] and r["source"] == j["source"]
        if not same:
            print("  ✗ #%s %-9s sel%d  p %.5f/%.5f  EV %.5f/%.5f  %s/%s" %
                  (r["no"], r["market"], r["sel"], r["p"], j["p"], r["ev"], j["ev"], r["grade"], j["grade"]))
            bad += 1
    if bad: print("\n✗ 불일치 %d건 — 엔진이 갈라졌다. 고쳐라." % bad)
    else:   print("✓ 전부 일치 (확률 오차 < 0.02%p)")
    return 1 if bad else 0

if __name__ == "__main__":
    sys.exit(main())
