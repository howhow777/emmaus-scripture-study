#!/usr/bin/env python3
"""Opt-in live evaluation; uses the real scoped Hermes model and persistent call budget."""
import argparse, hashlib, importlib.util, json, re, time
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
spec=importlib.util.spec_from_file_location('service',ROOT/'server/search_service.py');service=importlib.util.module_from_spec(spec);spec.loader.exec_module(service)
def span(ref):
 m=re.fullmatch(r'([A-Z0-9]+) (\d+)(?::(\d+)(?:-(\d+))?)?',ref)
 return (m[1],int(m[2]),int(m[3] or 1),int(m[4] or m[3] or 999)) if m else None

def overlap(a,b):
 x,y=span(a),span(b)
 return bool(x and y and x[:2]==y[:2] and x[2]<=y[3] and y[2]<=x[3])
def evaluate(case,result,graph):
 hits=result['results'];refs=[h['ref'] for h in hits if h['kind']=='passage'];allowed=[]
 for e in graph['entries']:
  if e['id'] in case['relevantEntries']:allowed.extend(p['ref'] for p in e['ot']+e['nt'])
 allowed+=case['requiredAnchors']
 relevant=lambda h: h.get('entryId') in case['relevantEntries'] if h['kind']=='entry' else any(overlap(h['ref'],a) for a in allowed)
 top=refs[:case['topK']];found=sum(any(overlap(a,r) for r in refs[:10]) for a in case['requiredAnchors'])
 return {'recallHits':found,'recallTotal':len(case['requiredAnchors']),'relevantHits':sum(relevant(h) for h in hits),'returned':len(hits), 'requiredTopK':all(any(overlap(a,r) for r in top) for a in case['requiredAnchors']), 'negativePass':bool(case['requiredAnchors']) or not hits}
def main():
 p=argparse.ArgumentParser();p.add_argument('--runtime',type=Path,required=True);p.add_argument('--output',type=Path,default=ROOT/'reports/semantic-live.json');p.add_argument('--rounds',type=int,default=2);p.add_argument('--resume',action='store_true');p.add_argument('--call-limit',type=int,default=service.DAILY_MODEL_CALLS);a=p.parse_args()
 if not 1<=a.call_limit<=service.DAILY_MODEL_CALLS:p.error('Internal call limit must be between 1 and the public default')
 golden=json.loads((ROOT/'data/coverage/search-golden.json').read_text());graph=service.read_asset(ROOT,'graph-data.js');search=service.Search(a.runtime,daily_limit=a.call_limit)
 if search.index['corpus'] != service.corpus_hash(service.documents(ROOT)):raise SystemExit('Runtime index is stale; rebuild before testing')
 report=json.loads(a.output.read_text()) if a.resume and a.output.exists() else {'corpus':search.index['corpus'],'model':service.MODEL,'rounds':a.rounds,'cacheBypassed':True,'callLimit':a.call_limit,'runs':[]}
 if report['corpus']!=search.index['corpus']:raise SystemExit('Cannot resume a different corpus')
 done={(r['round'],r['id']) for r in report['runs']}
 for round_ in range(1,a.rounds+1):
  for case in golden['semantic']:
   if (round_,case['id']) in done:continue
   start=time.monotonic()
   try:
    result=search.lookup(case['query'],'local-evaluation',use_cache=False)
    row={'round':round_,'id':case['id'],'query':case['query'],'seconds':round(time.monotonic()-start,3),'cached':result['cached'],'results':result['results'],'diagnostics':result.get('diagnostics'),**evaluate(case,result,graph)}
   except Exception as e:
    row={'round':round_,'id':case['id'],'query':case['query'],'error':type(e).__name__+': '+str(e)}
   report['runs'].append(row);a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
   print('LIVE',round_,case['id'],str(row.get('seconds','error'))+'s',[(h.get('ref') or h.get('entryId')) for h in row.get('results',[])],row.get('error',''),flush=True)
   if row.get('error'):raise SystemExit('Live evaluation stopped; inspect error, do not hide skipped cases')
 # Report raw precision and recall without rounding thresholds upward.
 runs=report['runs'];positive=[r for r in runs if r['recallTotal']];neg=[r for r in runs if not r['recallTotal']]
 summary={'runs':len(runs),'recallAt10':sum(r['recallHits'] for r in positive)/sum(r['recallTotal'] for r in positive),'precision':sum(r['relevantHits'] for r in runs)/max(1,sum(r['returned'] for r in runs)),'negativePass':all(r['negativePass'] for r in neg),'noahTop5':all(r['requiredTopK'] for r in runs if r['id'] in ['S01','S02','S03'])}
 report['summary']=summary;a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(summary,flush=True)
 if summary['recallAt10']<.95 or summary['precision']<.9 or not summary['negativePass'] or not summary['noahTop5']:raise SystemExit('Acceptance thresholds not met; report failures before revising')
if __name__=='__main__':main()
