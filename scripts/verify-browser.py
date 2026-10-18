#!/usr/bin/env python3
import argparse,json,time,sys
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parent.parent
parser=argparse.ArgumentParser(description='HTTPS browser regression; no model calls (error responses are injected)')
parser.add_argument('--site',default='https://emmaus-preview.promelink.link');args=parser.parse_args();SITE=args.site.rstrip('/')
OUT=ROOT.parent/'emmaus-audit-runtime';OUT.mkdir(exist_ok=True)
config=json.loads((ROOT/'semantic-config.js').read_text().split('=',1)[1].strip().removesuffix(';'))
report={'url':SITE,'corpus':config['corpus'],'checks':[],'consoleErrors':[]}
def check(name,condition,detail=''):
 report['checks'].append({'name':name,'pass':bool(condition),'detail':detail})
 (ROOT/'reports/browser-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 if not condition:raise AssertionError(name+' '+str(detail))
 print('PASS',name,flush=True)
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True,channel='chrome')
 context=browser.new_context(viewport={'width':1440,'height':1000},reduced_motion='reduce')
 page=context.new_page();page.on('pageerror',lambda error:report['consoleErrors'].append(str(error)))
 page.goto(SITE+'/graph.html');page.wait_for_function('window.EMMAUS_GRAPH_APP')
 check('default 49 core studies',len(page.evaluate('EMMAUS_GRAPH_APP.getVisible().entries'))==49)
 page.locator('#graphSearch').fill('挪亞');page.wait_for_timeout(350)
 visible=page.evaluate('EMMAUS_GRAPH_APP.getVisible()')
 check('Noah actual literal UI both Gospels',all('nt:'+ref in visible['keywordHits'] for ref in ['MAT 24:37-39','LUK 17:26-27']))
 check('Noah lookup auto all',page.locator('#scopeFilter').input_value()=='all')
 page.locator('#jesusSpeechOnly').check();page.wait_for_timeout(150)
 check('verified Jesus-only Noah UI',all('nt:'+ref in page.evaluate('EMMAUS_GRAPH_APP.getVisible().keywordHits') for ref in ['MAT 24:37-39','LUK 17:26-27']))
 page.locator('#scopeFilter').select_option('core');page.wait_for_timeout(100)
 check('core restriction explained',page.locator('#searchFeedback').is_visible() and len(page.evaluate('EMMAUS_GRAPH_APP.getVisible().entries'))==0)
 page.locator('#searchFeedback button').click();page.locator('#testamentFilter').select_option('ot');page.wait_for_timeout(100)
 check('testament hidden refs explained',page.locator('#searchFeedback').is_visible())
 page.locator('#searchFeedback button').click();page.locator('#bookFilter').select_option('MAT');page.wait_for_timeout(100)
 check('combined book Noah filter', 'E187' in page.evaluate('EMMAUS_GRAPH_APP.getVisible().entries'))
 page.locator('#clearFilters').click();page.locator('#graphSearch').fill('兩個人的見證');page.wait_for_timeout(200)
 check('standalone quote searchable',page.locator('#resultList').inner_text().find('約翰福音 8:17–18')>=0)
 page.locator('#testamentFilter').select_option('ot');page.wait_for_timeout(100)
 check('standalone-only hidden result explained',page.locator('#searchFeedback').is_visible())
 page.locator('#searchFeedback button').click();page.locator('#graphSearch').fill('約翰福音8:17');page.wait_for_timeout(100)
 check('standalone citation alias lookup',page.locator('#resultList').inner_text().find('約翰福音 8:17–18')>=0)
 page.goto(SITE+'/graph.html#E187');page.wait_for_function('window.EMMAUS_GRAPH_APP');page.wait_for_timeout(150)
 check('new non-core deep link auto reveal', 'E187' in page.evaluate('EMMAUS_GRAPH_APP.getVisible().entries') and '挪亞' in page.locator('#detailsContent').inner_text())
 check('new study backlinks',page.locator('#detailsContent a[href="index.html#E187"]').count()==1)
 page.locator('#detailsContent a[href*="MAT.24.37-39"]').first.hover();page.wait_for_timeout(250)
 check('new scripture hover preview',page.locator('#scripturePreview').is_visible() and '挪亞' in page.locator('#scripturePreview').inner_text())
 page.keyboard.press('Escape');check('preview keyboard dismissal',not page.locator('#scripturePreview').is_visible())
 page.goto(SITE+'/index.html#E187');page.wait_for_timeout(300)
 check('new reading anchor exists',page.locator('#E187').count()==1)
 check('new reading graph backlink',page.locator('#E187 a[href="graph.html#E187"]').count()==1)
 page.goto(SITE+'/graph.html#E117');page.wait_for_function('window.EMMAUS_GRAPH_APP');check('legacy E117 deep link','E117' in page.evaluate('EMMAUS_GRAPH_APP.getVisible().entries'))
 # Error branches are deliberately injected; they do not call the model or count as semantic evidence.
 for name,status,body,expected in [
 ('HTTP 503 not empty success',503,{'error':'語意搜尋暫時無法使用','code':'upstream_unavailable'},'無法使用'),
 ('stale corpus not empty success',200,{'corpus':'stale','results':[]},'索引正在更新'),
 ('unknown refs diagnostic not empty claim',200,{'corpus':report['corpus'],'results':[],'diagnostics':{'rejected':1}},'不在目前索引')]:
  page.route('**/search',lambda route,request,*,status=status,body=body:route.fulfill(status=status,content_type='application/json',body=json.dumps(body)))
  page.locator('#graphSearch').fill('耶穌說挪亞');page.locator('#semanticSearch').click();page.wait_for_timeout(100)
  check(name,expected in page.locator('#semanticStatus').inner_text())
  page.unroute('**/search')
 # Delayed reply must not overwrite a newer literal search.
 pending=[];page.route('**/search',lambda route:pending.append(route))
 page.locator('#graphSearch').fill('耶穌說挪亞');page.locator('#semanticSearch').click();page.wait_for_timeout(50);check('request dispatched before superseding',len(pending)==1);page.locator('#graphSearch').fill('釘痕')
 for route in pending:
  try:route.fulfill(status=200,content_type='application/json',body=json.dumps({'corpus':report['corpus'],'results':[{'kind':'passage','ref':'MAT 24:37-39'}]}))
  except Exception:pass # Abort can close the intercepted request before fulfillment.
 page.wait_for_timeout(200)
 check('stale reply cancelled',page.evaluate('EMMAUS_GRAPH_APP.getVisible().semanticHits.length')==0 and 'JHN 20:25-27' in ' '.join(page.evaluate('EMMAUS_GRAPH_APP.getVisible().keywordHits')))
 page.unroute('**/search')
 page.screenshot(path=str(OUT/'desktop-search-audit.png'),full_page=True)
 # Touch Chromium emulation is a UI check, not iPhone Safari or Android hardware proof.
 mobile=browser.new_context(viewport={'width':390,'height':844},device_scale_factor=3,is_mobile=True,has_touch=True)
 mp=mobile.new_page();mp.on('pageerror',lambda error:report['consoleErrors'].append(str(error)))
 mp.goto(SITE+'/graph.html');mp.wait_for_function('window.EMMAUS_GRAPH_APP');mp.locator('.filter-fold summary').click();mp.locator('#graphSearch').fill('挪亞');mp.wait_for_timeout(250)
 check('mobile Noah real layout',all('nt:'+ref in mp.evaluate('EMMAUS_GRAPH_APP.getVisible().keywordHits') for ref in ['MAT 24:37-39','LUK 17:26-27']))
 check('mobile graph no page overflow',mp.evaluate('document.documentElement.scrollWidth <= innerWidth+1'))
 mp.goto(SITE+'/coverage.html');mp.wait_for_timeout(200)
 check('coverage table mobile contained overflow',mp.evaluate('document.documentElement.scrollWidth <= innerWidth+1'))
 merged=mp.locator('a[href*="LUK.2.34-35"]').first;merged.scroll_into_view_if_needed();mp.wait_for_timeout(100)
 box=merged.bounding_box();cdp=mobile.new_cdp_session(mp);point={'x':box['x']+box['width']/2,'y':box['y']+box['height']/2}
 cdp.send('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[point]});mp.wait_for_timeout(650)
 check('mobile held preview open',mp.locator('#scripturePreview').is_visible())
 cdp.send('Input.dispatchTouchEvent',{'type':'touchEnd','touchPoints':[]});mp.wait_for_timeout(200)
 check('mobile held preview persists',mp.locator('#scripturePreview').is_visible())
 check('merged numbering actually rendered',mp.locator('#scripturePreview strong').first.inner_text()=='34–35')
 check('merged preview no false truncation',mp.locator('.scripture-preview-extent').inner_text()=='全段 2 節')
 mp.screenshot(path=str(OUT/'mobile-merged-preview.png'),full_page=False)
 check('no uncaught JS errors',not report['consoleErrors'],report['consoleErrors'])
 report['browser']=browser.version;report['realPhones']='pending user';(ROOT/'reports/browser-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');browser.close()
