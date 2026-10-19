#!/usr/bin/env python3
"""Real Chromium preview/scroll regression against HTTPS; zero model calls."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--site', default='https://emmaus-preview.promelink.link')
parser.add_argument('--report', type=Path, default=Path('reports/preview-browser.json'))
args = parser.parse_args()
SITE = args.site.rstrip('/')
OUT = ROOT.parent / 'emmaus-full-preview-runtime'
OUT.mkdir(exist_ok=True)
REPORT = args.report if args.report.is_absolute() else ROOT / args.report
expected = json.loads((ROOT / 'scripture-search-data.js').read_text().split('=', 1)[1][:-2])['passages']
acceptance = json.loads((ROOT / 'reports/preview-device-acceptance.json').read_text())
report = {'url': SITE, 'startedAt': datetime.now(timezone.utc).isoformat(), 'checks': [], 'passages': {}, 'consoleErrors': [], 'modelRequests': 0, 'assetSha256': {},
          'realPhones': {key: acceptance[key] for key in ['iphoneSafari', 'androidChrome']},
          'limitations': 'Chromium touch emulation is not real iPhone Safari or Android hardware acceptance.'}


def save():
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')


def check(name, passed, detail=None):
    report['checks'].append({'name': name, 'pass': bool(passed), 'detail': detail})
    save()
    if not passed:
        raise AssertionError(name + ': ' + str(detail))
    print('PASS', name, flush=True)


def watch(context):
    context.on('page', lambda page: page.on('pageerror', lambda error: report['consoleErrors'].append(str(error))))
    # Fail closed: previews must not spend a semantic-search request.
    def no_model(route):
        report['modelRequests'] += 1
        route.abort()
    context.route('**/search', no_model)


def anchor(page, ref):
    return page.locator('a[href*="/46/' + ref.replace(' ', '.').replace(':', '.') + '.CUNP-"]').first


def geometry(page):
    return page.locator('#scripturePreview').evaluate('''card => {
      const rect=card.getBoundingClientRect(), head=card.querySelector('.scripture-preview-head').getBoundingClientRect();
      const tail=card.querySelector('.scripture-preview-verse:last-child')?.getBoundingClientRect();
      const close=card.querySelector('button').getBoundingClientRect();
      return {scrollTop:card.scrollTop,max:card.scrollHeight-card.clientHeight,
        contained:rect.left>=-1 && rect.right<=innerWidth+1 && rect.top>=-1 && rect.bottom<=innerHeight+1,
        headerVisible:head.top>=rect.top-1 && close.bottom<=rect.bottom && close.top>=rect.top,
        tailVisible:!!tail && tail.bottom<=rect.bottom+1 && tail.top>=head.bottom-1,
        tailTop:tail?.top,tailBottom:tail?.bottom,headerBottom:head.bottom,
        bodyY:scrollY,innerScroll:getComputedStyle(card.querySelector('.scripture-preview-verses')).overflowY};
    }''')


def keyboard_open(page, ref):
    page.keyboard.press('Escape')
    page.keyboard.press('Tab')  # restore keyboard input mode after any pointer gesture
    link = anchor(page, ref)
    link.scroll_into_view_if_needed()
    link.focus()
    page.locator('#scripturePreview').wait_for(state='visible')
    page.keyboard.press('ArrowDown')
    return link


def check_close(page, label):
    result = page.locator('.scripture-preview-close').evaluate('''button => {
      const b=button.getBoundingClientRect(),s=button.querySelector('svg').getBoundingClientRect();
      return {width:b.width,height:b.height,offsetX:s.x+s.width/2-b.x-b.width/2,offsetY:s.y+s.height/2-b.y-b.height/2,
        accessibleName:button.getAttribute('aria-label')};
    }''')
    check(label + ' close icon centered in circular touch target', abs(result['width']-result['height']) < .5 and result['width'] >= 44
          and abs(result['offsetX']) < .5 and abs(result['offsetY']) < .5 and result['accessibleName'] == '關閉經文預覽', result)


for name in ['scripture-preview.js', 'scripture-preview.css', 'scripture-previews-data.js']:
    with urlopen(Request(SITE + '/' + name + '?v=full-preview2', headers={'User-Agent': 'Mozilla/5.0'}), timeout=30) as response:
        body = response.read()
    report['assetSha256'][name] = hashlib.sha256(body).hexdigest()
    check('HTTPS preview matches current ' + name, body == (ROOT / name).read_bytes())


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True, channel='chrome')
    report['browser'] = browser.version
    context = browser.new_context(viewport={'width': 1440, 'height': 1000}, reduced_motion='reduce')
    watch(context)
    page = context.new_page()
    # Exercise actual anchors: static reading/coverage pages, then every study's dynamic details.
    verify_links = '''({expected, entries}) => {
      const results=[];
      const inspect=()=>{
        const links=[...document.querySelectorAll('a[href^="https://www.bible.com/bible/46/"]')].filter(a=>!a.closest('#scripturePreview'));
        for(const a of links){
          const match=decodeURIComponent(new URL(a.href).pathname).match(/\/46\/([A-Z0-9]+)\.(\d+)(?:\.(\d+(?:-\d+)?))?\.CUNP-/);
          const ref=match[1]+' '+match[2]+(match[3]?':'+match[3]:'');
          a.focus({preventScroll:true});
          const card=document.querySelector('#scripturePreview');
          const rows=[...card.querySelectorAll('.scripture-preview-verse')].map(row=>({number:row.querySelector('strong').textContent,text:row.querySelector('span').textContent}));
          const want=expected[ref].map(v=>({number:String(v.numberLabel||v.number),text:v.text}));
          results.push({ref,pass:!card.hidden && JSON.stringify(rows)===JSON.stringify(want) && card.scrollTop===0,
            rows:rows.length,lastNumber:rows.at(-1)?.number,caption:card.querySelector('.scripture-preview-extent').textContent});
        }
      };
      if(entries){ for(const entry of window.EMMAUS_GRAPH_DATA.entries){window.EMMAUS_GRAPH_APP.selectEntry(entry.id);inspect();} }
      else inspect();
      return results;
    }'''
    for filename in ['index.html', 'coverage.html', 'graph.html']:
        page.goto(SITE + '/' + filename)
        page.wait_for_function('window.EMMAUS_SCRIPTURE_PREVIEWS && document.querySelector("#scripturePreview")')
        if filename == 'index.html':
            page.locator('#showAll').click()
            page.locator('#expandVisible').click()
            page.keyboard.press('Tab')
        if filename == 'graph.html':
            page.wait_for_function('window.EMMAUS_GRAPH_APP')
            page.locator('#scopeFilter').select_option('all')
            page.keyboard.press('Tab')
        results = page.evaluate(verify_links, {'expected': expected, 'entries': filename == 'graph.html'})
        check(filename + ' all actual scripture anchors render full source text', all(row['pass'] for row in results), {'anchorCount': len(results), 'failures': [r for r in results if not r['pass']][:5]})
        check_close(page, filename)
        for row in results:
            prior = report['passages'].setdefault(row['ref'], dict(row, entrypoints=[]))
            if filename not in prior['entrypoints']:
                prior['entrypoints'].append(filename)
    check('all 901 distinct references exercised in browser', set(report['passages']) == set(expected), len(report['passages']))
    page.goto(SITE + '/index.html')
    page.locator('#showAll').click()
    page.locator('#expandVisible').click()
    for ref, last in [('LUK 1:26-38', '38'), ('ISA 7:10-17', '17'), ('LUK 24', '53')]:
        link = keyboard_open(page, ref)
        check(ref + ' opens at beginning', geometry(page)['scrollTop'] == 0)
        before = page.evaluate('scrollY')
        page.keyboard.press('End')
        g = geometry(page)
        check(ref + ' keyboard scroll reaches visible final verse with sticky close', g['tailVisible'] and g['headerVisible'] and g['contained'] and g['bodyY'] == before, g)
        check(ref + ' correct final verse', page.locator('.scripture-preview-verse strong').last.inner_text() == last)
        page.keyboard.press('Escape')
        check(ref + ' Escape restores source-link focus', link.evaluate('a=>document.activeElement===a') and not page.locator('#scripturePreview').is_visible())
    # True pointer hover, wheel and internal focus must retain the popup and its scroll position.
    page.mouse.move(0, 0)
    link = anchor(page, 'LUK 24')
    link.hover()
    page.wait_for_timeout(250)
    card = page.locator('#scripturePreview')
    card.hover(position={'x': 150, 'y': 150})
    before = page.evaluate('scrollY')
    page.mouse.wheel(0, 100000)
    page.wait_for_timeout(250)
    g = geometry(page)
    check('hover to card and mouse wheel reaches chapter tail without background scrolling', g['tailVisible'] and g['bodyY'] == before and card.is_visible(), g)
    top = g['scrollTop']
    page.locator('.scripture-preview-close').focus()
    check('moving focus inside same popup preserves reading position', geometry(page)['scrollTop'] == top)
    page.screenshot(path=str(OUT / 'desktop-chapter-tail.png'))
    # Switching source anchors resets to verse one, even with the previous card scrolled.
    keyboard_open(page, 'LUK 1:26-38')
    check('switching passages resets scroll', geometry(page)['scrollTop'] == 0)
    page.goto(SITE + '/graph.html#E117')
    page.wait_for_function('window.EMMAUS_GRAPH_APP')
    link = page.locator('#detailsContent a[href*="ISA.53.1-12."]').first
    link.hover()
    page.wait_for_timeout(250)
    card.hover(position={'x': 150, 'y': 150})
    before = page.evaluate('({y:scrollY,zoom:JSON.stringify(document.querySelector("canvas").__zoom)})')
    page.mouse.wheel(0, 100000)
    page.wait_for_timeout(200)
    after = page.evaluate('({y:scrollY,zoom:JSON.stringify(document.querySelector("canvas").__zoom)})')
    check('graph preview wheel reaches tail without panning or zooming canvas', geometry(page)['tailVisible'] and before == after, geometry(page))
    check('original Bible.com destination preserved', page.locator('.scripture-preview-open').get_attribute('href') == link.get_attribute('href'))
    card.focus()
    page.keyboard.press('Escape')
    check('graph Escape closes preview, preserves selected study and restores link focus', link.count() == 1 and link.evaluate('a=>document.activeElement===a') and not card.is_visible())
    # Cache mismatch is injected deliberately, not a production/source edit.
    bad = browser.new_context(viewport={'width': 1280, 'height': 900})
    watch(bad)
    short = json.loads((ROOT / 'scripture-previews-data.js').read_text().split('=', 1)[1][:-2])
    short['passages']['LUK 24']['verses'] = short['passages']['LUK 24']['verses'][:4]
    bad.route('**/scripture-previews-data.js*', lambda route: route.fulfill(content_type='application/javascript', body='window.EMMAUS_SCRIPTURE_PREVIEWS=' + json.dumps(short) + ';'))
    bp = bad.new_page()
    bp.goto(SITE + '/index.html')
    keyboard_open(bp, 'LUK 24')
    check('old truncated cache explicitly errors instead of claiming full text', '資料不完整' in bp.locator('.scripture-preview-extent').inner_text() and bp.locator('.scripture-preview-verse').count() == 0)
    bad.close()
    # Touch sequences are real CDP input, not dispatched synthetic JS events.
    for width, height in [(390, 844), (320, 568), (844, 390)]:
        mobile = browser.new_context(viewport={'width': width, 'height': height}, is_mobile=True, has_touch=True, reduced_motion='reduce')
        watch(mobile)
        mp = mobile.new_page()
        cdp = mobile.new_cdp_session(mp)
        # Installed Chrome's native window includes browser chrome. Make it larger
        # than the emulated CSS viewport, or bottom-edge CDP input misses the compositor.
        window = cdp.send('Browser.getWindowForTarget', {})
        cdp.send('Browser.setWindowBounds', {'windowId': window['windowId'], 'bounds': {'width': max(600, width + 100), 'height': height + 240}})
        mp.goto(SITE + '/index.html')
        mp.wait_for_function('document.querySelector("#scripturePreview")')
        mp.locator('#showAll').click()
        mp.locator('#expandVisible').click()
        mp.mouse.move(0, 0)
        check(f'{width}x{height} CSS viewport unchanged by native window sizing', mp.evaluate('({width:innerWidth,height:innerHeight})') == {'width': width, 'height': height})
        for ref in ['LUK 1:26-38', 'ISA 7:10-17', 'LUK 24']:
            mp.keyboard.press('Escape')
            link = anchor(mp, ref)
            link.scroll_into_view_if_needed()
            # No focus event before the actual hold.
            mp.wait_for_timeout(120)
            mp.keyboard.press('Escape')
            box = link.bounding_box()
            point = {'x': box['x'] + box['width'] / 2, 'y': box['y'] + box['height'] / 2}
            cdp.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': [point]})
            mp.wait_for_timeout(600)
            check(f'{width}x{height} {ref} long-press opens pinned', mp.locator('#scripturePreview').is_visible() and 'is-pinned' in mp.locator('#scripturePreview').get_attribute('class'))
            cdp.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []})
            mp.wait_for_timeout(120)
            check(f'{width}x{height} {ref} remains after release', mp.locator('#scripturePreview').is_visible())
            before = mp.evaluate('scrollY')
            for _ in range(45):
                g = geometry(mp)
                if g['tailVisible']:
                    break
                b = mp.locator('#scripturePreview').bounding_box()
                head = mp.locator('.scripture-preview-head').bounding_box()
                x = b['x'] + b['width'] / 2
                start = b['y'] + b['height'] - 20
                end = head['y'] + head['height'] + 15
                if g['max'] - g['scrollTop'] <= 1:
                    # At the footer, a small viewport may hide the tail's first
                    # line under the fixed heading. Swipe down to read the whole verse.
                    start = head['y'] + head['height'] + 15
                    end = min(b['y'] + b['height'] - 20, start + max(30, g['headerBottom'] + 8 - g['tailTop']))
                cdp.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': [{'x': x, 'y': start}]})
                for step in range(1, 6):
                    cdp.send('Input.dispatchTouchEvent', {'type': 'touchMove', 'touchPoints': [{'x': x, 'y': start + (end - start) * step / 5}]})
                    mp.wait_for_timeout(25)
                cdp.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []})
                mp.wait_for_timeout(100)
            g = geometry(mp)
            check(f'{width}x{height} {ref} finger scrolling reaches last verse without background scroll', g['tailVisible'] and g['headerVisible'] and g['contained'] and g['bodyY'] == before and g['innerScroll'] == 'visible', g)
            check_close(mp, f'{width}x{height} {ref} scrolled header')
            mp.screenshot(path=str(OUT / f'touch-{width}-{height}-{ref.replace(" ", "-").replace(":", "-")}.png'))
            mp.get_by_role('button', name='關閉經文預覽', exact=True).click()
            check(f'{width}x{height} {ref} close control works', not mp.locator('#scripturePreview').is_visible())
        if width == 390:
            mp.goto(SITE + '/index.html#E098')
            mp.mouse.move(0, 0)
            link = anchor(mp, 'LUK 1:26-38')
            link.scroll_into_view_if_needed()
            mp.wait_for_timeout(150)
            mp.keyboard.press('Escape')
            box = link.bounding_box()
            point = {'x': box['x'] + box['width'] / 2, 'y': box['y'] + box['height'] / 2, 'id': 1}
            cdp.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': [point]})
            cdp.send('Input.dispatchTouchEvent', {'type': 'touchMove', 'touchPoints': [dict(point, y=point['y'] - 30)]})
            mp.wait_for_timeout(600)
            cdp.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []})
            check('movement before hold threshold cancels preview', not mp.locator('#scripturePreview').is_visible())
            link.scroll_into_view_if_needed()
            mp.wait_for_timeout(150)
            mp.keyboard.press('Escape')
            box = link.bounding_box()
            point.update(x=box['x'] + box['width'] / 2, y=box['y'] + box['height'] / 2)
            cdp.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': [point]})
            cdp.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': [point, dict(point, x=point['x'] + 40, id=2)]})
            mp.wait_for_timeout(600)
            cdp.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []})
            check('second finger before hold threshold cancels preview', not mp.locator('#scripturePreview').is_visible())
            cdp.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': [point]})
            mp.wait_for_timeout(600)
            cdp.send('Input.dispatchTouchEvent', {'type': 'touchCancel', 'touchPoints': []})
            check('browser cancellation after opening keeps preview stable', mp.locator('#scripturePreview').is_visible() and 'is-pressing' not in mp.locator('#scripturePreview').get_attribute('class'))
        mobile.close()
    # Source-preserved special cases and single-verse references remain short and complete.
    for ref in ['LUK 2:34-35', 'PSA 8:1-9', 'MRK 15:24-34', 'MAT 4:4']:
        check(ref + ' browser verified', report['passages'][ref]['pass'], report['passages'][ref])
    check('no uncaught browser errors', not report['consoleErrors'], report['consoleErrors'])
    check('zero semantic model requests', report['modelRequests'] == 0, report['modelRequests'])
    save()
    browser.close()
