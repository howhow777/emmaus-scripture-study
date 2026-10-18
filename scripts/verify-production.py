#!/usr/bin/env python3
"""Opt-in production smoke; one public API request, subject to normal cache and budget."""
from datetime import datetime,timezone
import json,time
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright
BASE='https://howhow777.github.io/emmaus-scripture-study'
ROOT=Path(__file__).resolve().parent.parent;checks=[];errors=[]
def check(name,condition):
 checks.append({'name':name,'pass':bool(condition)});print('PASS' if condition else 'FAIL',name,flush=True)
 if not condition:raise AssertionError(name)
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True,channel='chrome');context=browser.new_context(viewport={'width':1440,'height':1000},reduced_motion='reduce');page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
 response=page.goto(BASE+'/graph.html');page.wait_for_function('window.EMMAUS_GRAPH_APP')
 check('Public graph HTTP 200',response.status==200)
 check('Public corpus matches 901 passages and 206 studies',page.evaluate('EMMAUS_SEMANTIC_CONFIG.corpus')=='4dce84e4f5eb107fa141' and page.evaluate('EMMAUS_GRAPH_DATA.entries.length')==206 and page.evaluate('Object.keys(EMMAUS_SCRIPTURE_SEARCH.passages).length')==901)
 for query in ['彼拉多','多馬','釘痕','挪亞']:
  page.locator('#graphSearch').fill(query);page.wait_for_timeout(180)
  check('Public literal query '+query,query in page.locator('#resultList').inner_text())
 check('Public literal Noah both Gospel nodes',all(ref in page.evaluate('EMMAUS_GRAPH_APP.getVisible().keywordHits') for ref in ['nt:MAT 24:37-39','nt:LUK 17:26-27']))
 page.locator('#graphSearch').fill('耶穌曾經講過挪亞嗎？');start=time.monotonic()
 with page.expect_response(lambda r:r.url=='https://emmaus-search.promelink.link/search',timeout=55000) as response_event:page.locator('#semanticSearch').click()
 api=response_event.value;data=api.json();page.wait_for_function('!document.getElementById("semanticSearch").disabled',timeout=55000)
 semantic_seconds=round(time.monotonic()-start,3)
 check('Real public API success and CORS',api.status==200 and api.all_headers().get('access-control-allow-origin')=='https://howhow777.github.io')
 check('Real public semantic Noah both nodes',all(ref in page.evaluate('EMMAUS_GRAPH_APP.getVisible().semanticHits') for ref in ['nt:MAT 24:37-39','nt:LUK 17:26-27']))
 page.evaluate('EMMAUS_GRAPH_APP.selectEntry("E187")');check('Public graph to reading backlink',page.locator('#detailsContent a[href="index.html#E187"]').count()==1)
 link=page.locator('#detailsContent a[href*="MAT.24.37-39"]').first
 with page.expect_popup() as popup_event:link.click()
 popup=popup_event.value;popup.wait_for_function('location.href.includes("/MAT.24.37-39.") && document.body?.innerText.includes("挪亞")',timeout=20000);check('External Bible link opens correct passage','/MAT.24.37-39.CUNP-' in popup.evaluate('location.href'));popup.close()
 page.goto(BASE+'/index.html#E187');check('Public reading to graph backlink',page.locator('#E187 a[href="graph.html#E187"]').count()==1)
 page.locator('#E187 a[href="graph.html#E187"]').click();page.wait_for_function('window.EMMAUS_GRAPH_APP');check('Public bidirectional deep link','挪亞' in page.locator('#detailsContent').inner_text())
 check('No uncaught runtime errors',not errors)
 page.screenshot(path=str(ROOT.parent/'emmaus-audit-runtime/production-noah.png'),full_page=True)
 result={'verifiedAt':datetime.now(timezone.utc).isoformat(timespec='seconds'),'site':BASE+'/','corpus':data['corpus'],'checks':checks,'errors':errors,'realPublicSemantic':{'query':'耶穌曾經講過挪亞嗎？','status':api.status,'cached':data['cached'],'seconds':semantic_seconds,'results':data['results']},'browser':browser.version}
 (ROOT/'reports/production-verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');browser.close()
