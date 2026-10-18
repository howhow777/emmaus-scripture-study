#!/usr/bin/env python3
"""Check all preview ranges against pinned sources; never fetch or call a model."""
import argparse
import hashlib
import importlib.util
import json
import re
import subprocess
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('previews', ROOT / 'scripts/build-scripture-previews.py')
previews = importlib.util.module_from_spec(spec)
spec.loader.exec_module(previews)
BASELINE = '435f765'
REPORT = ROOT / 'reports/preview-completeness.json'


def asset(name, raw=None):
    return json.loads((raw or (ROOT / name).read_text()).split('=', 1)[1].strip()[:-1])


def reference(href):
    match = re.fullmatch(r'https://www.bible.com/bible/46/([A-Z0-9]+)\.(\d+)(?:\.(\d+(?:-\d+)?))?\.CUNP-神', unquote(href))
    if not match:
        raise ValueError(href)
    return match[1] + ' ' + match[2] + (':' + match[3] if match[3] else '')


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        href = dict(attrs).get('href', '')
        if tag == 'a' and href.startswith('https://www.bible.com/bible/46/'):
            self.links.append(href)


def build():
    old = asset('', subprocess.check_output(['git', 'show', BASELINE + ':scripture-previews-data.js'], cwd=ROOT, text=True))
    current = asset('scripture-previews-data.js')
    expected, search = previews.build(previews.DEFAULT_SOURCE_DIR)
    assert current == expected, 'Preview text differs from pinned sources'
    assert (ROOT / 'scripture-search-data.js').read_text() == previews.serialized_search(search)
    unchanged = {}
    for name in ['scripture-search-data.js', 'graph-data.js', 'semantic-config.js']:
        before = subprocess.check_output(['git', 'show', BASELINE + ':' + name], cwd=ROOT)
        now = (ROOT / name).read_bytes()
        assert now == before, name + ' changed outside preview scope'
        unchanged[name] = hashlib.sha256(now).hexdigest()
    entrypoints = {key: set() for key in expected['passages']}
    hrefs = {}
    for name in ['index.html', 'coverage.html']:
        links = Links()
        links.feed((ROOT / name).read_text())
        for href in links.links:
            ref = reference(href)
            entrypoints[ref].add(name)
            hrefs[ref] = href
    graph = asset('graph-data.js')
    for entry in graph['entries']:
        for passage in entry['ot'] + entry['nt']:
            assert reference(passage['href']) == passage['ref']
            entrypoints[passage['ref']].add('graph.html#' + entry['id'])
            hrefs[passage['ref']] = passage['href']
    for speech in graph['speech']:
        for passage in speech['spans']:
            assert reference(passage['href']) == passage['ref']
            entrypoints[passage['ref']].add('graph.html#' + speech['entryId'] + ' (Jesus speech)')
            hrefs[passage['ref']] = passage['href']
    rows = []
    for ref, item in current['passages'].items():
        first = int(re.search(r':(\d+)', ref)[1]) if ':' in ref else 1
        expected_numbers = list(range(first, first + item['total']))
        covered = previews.covered_numbers(item['verses'])
        old_numbers = previews.covered_numbers(old['passages'][ref]['verses'])
        assert covered == expected_numbers and entrypoints[ref], ref
        revision, sha = previews.PAGES[ref.split()[0]]
        rows.append({'ref': ref, 'label': item['label'], 'entrypoints': sorted(entrypoints[ref]),
                     'href': hrefs[ref], 'expectedCount': item['total'], 'coveredCount': len(covered),
                     'renderedRows': len(item['verses']), 'firstVerse': covered[0], 'lastVerse': covered[-1],
                     'previousCoveredCount': len(old_numbers), 'previouslyTruncated': old_numbers != expected_numbers,
                     'sourceRevision': revision, 'sourceSha256': sha, 'result': 'pass'})
    assert len(rows) == 901
    assert sum(row['previouslyTruncated'] for row in rows) == 315
    return {'schema': 1, 'baselineCommit': BASELINE, 'references': len(rows), 'complete': len(rows),
            'previouslyTruncated': 315, 'alreadyComplete': 586, 'source': current['source'],
            'corpus': asset('semantic-config.js')['corpus'], 'unchangedSha256': unchanged,
            'checks': 'All citation ranges, combined numbering, text and pinned source hashes; no network or model calls.',
            'passages': rows}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    content = json.dumps(build(), ensure_ascii=False, indent=2) + '\n'
    if args.check:
        assert REPORT.read_text() == content, 'Preview completeness report is out of date'
    else:
        REPORT.write_text(content)
    print('901 complete previews; 315 formerly truncated; search and semantic corpus unchanged')
