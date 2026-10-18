import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer
from search_service import MODEL, ORIGIN, Search, ServiceError, catalog_messages, corpus_hash, documents, make_handler, selected_results


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.index = {'model': MODEL, 'corpus': 'fixture', 'documents': [
            {'kind': 'passage', 'ref': 'JHN 20:25-27', 'text': '多馬查看釘痕', 'excerpt': '多馬查看釘痕'},
            {'kind': 'entry', 'entryId': 'E167', 'text': '研究界線', 'excerpt': '研究界線'}]}
        (self.root / 'index.json').write_text(json.dumps(self.index))
        self.calls = []
        def classify(query, catalog):
            self.calls.append(query)
            return {'refs': ['JHN 20:25-27', 'JHN 20:25-27', 'XXX 1:1'], 'entryIds': ['E999']}
        self.search = Search(self.root, classifier=classify, daily_limit=1)

    def tearDown(self):
        self.search.db.close()
        self.directory.cleanup()

    def test_complete_catalog_survives_hermes_content_limit(self):
        catalog = ('GEN 1:1 | text\n' * 6000) + 'JHN 20:25-27 | 多馬與釘痕\n' + ('ZEC 13:6 | text\n' * 6000)
        messages = catalog_messages('Search instructions', catalog, '手上的傷口')
        self.assertGreater(len(messages), 3)
        self.assertTrue(all(len(message['content']) <= 50000 for message in messages))
        # Simulate the live gateway's per-message cap and system concatenation.
        transmitted = ''.join(m['content'][:65536] for m in messages[1:-1])
        self.assertEqual(transmitted, catalog)
        self.assertIn('JHN 20:25-27', transmitted)
        self.assertEqual(messages[-1], {'role': 'user', 'content': '手上的傷口'})

    def test_whitelist_deduplicates_and_drops_invented_references(self):
        result = selected_results(self.index, {'refs': ['XXX 1:1', 'JHN 20:25-27', 'JHN 20:25-27'], 'entryIds': ['E999']})
        self.assertEqual([x['ref'] for x in result], ['JHN 20:25-27'])
        self.assertNotIn('text', result[0])

    def test_real_release_corpus_is_complete_in_transport_and_matches_config(self):
        site = Path(__file__).resolve().parent.parent
        docs = documents(site)
        config = json.loads((site / 'semantic-config.js').read_text().split('=', 1)[1].strip().removesuffix(';'))
        self.assertEqual(config['corpus'], corpus_hash(docs))
        catalog = '\n'.join((d.get('ref') or d.get('entryId')) + ' | ' + d['text'] for d in docs)
        messages = catalog_messages('Search instructions', catalog, '挪亞')
        self.assertEqual(''.join(m['content'][:65536] for m in messages[1:-1]), catalog)
        self.assertTrue(all(len(m['content']) <= 50000 for m in messages[1:-1]))
        for ref in ['MAT 24:37-39', 'LUK 17:26-27', 'MAT 5:21-48', 'JHN 8:17-18']:
            self.assertIn(ref + ' | ', catalog)

    def test_cache_and_persistent_daily_budget(self):
        self.assertFalse(self.search.lookup('想摸釘痕才信', 'one')['cached'])
        self.assertTrue(self.search.lookup('想摸釘痕才信', 'one')['cached'])
        self.assertEqual(len(self.calls), 1)
        with self.assertRaises(ServiceError) as error:
            self.search.lookup('different query', 'two')
        self.assertEqual(error.exception.status, 429)
        other = Search(self.root, classifier=lambda *_: self.fail('Budget reset'), daily_limit=1)
        with self.assertRaises(ServiceError):
            other.lookup('new query after restart', 'two')
        other.db.close()

    def test_ip_rate_limit_also_applies_to_cached_queries(self):
        for _ in range(20):
            self.search.lookup('想摸釘痕才信', 'one')

    def test_daily_budget_is_atomic_between_independent_service_instances(self):
        other = Search(self.root, classifier=self.search.classifier, daily_limit=1)
        barrier = threading.Barrier(2)
        def attempt(search):
            barrier.wait()
            try:
                search.lookup('並行驗證', 'one', use_cache=False)
                return 'ok'
            except ServiceError as error:
                return error.code
        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                outcomes = list(pool.map(attempt, [self.search, other]))
            self.assertCountEqual(outcomes, ['ok', 'daily_limit'])
            self.assertEqual(len(self.calls), 1)
        finally:
            other.db.close()
        with self.assertRaises(ServiceError):
            self.search.lookup('想摸釘痕才信', 'one')

    def test_explicit_cache_bypass_is_internal_and_calls_model_again(self):
        self.search.daily_limit = 3
        first = self.search.lookup('多馬', 'one', use_cache=False)
        second = self.search.lookup('多馬', 'one', use_cache=False)
        self.assertFalse(first['cached']); self.assertFalse(second['cached'])
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(first['diagnostics'], {'selected': 3, 'rejected': 2})

    def test_upstream_failure_is_not_a_successful_empty_result(self):
        def failure(*_): raise TimeoutError('private detail not exposed')
        self.search.classifier = failure
        with self.assertRaises(ServiceError) as error:
            self.search.lookup('耶穌說挪亞', 'one')
        self.assertEqual(error.exception.status, 503)
        self.assertEqual(error.exception.code, 'upstream_timeout')
        self.assertNotIn('private detail', error.exception.message)

    def test_http_origin_payload_and_route_boundaries(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.search))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = 'http://127.0.0.1:' + str(server.server_port)
        def post(body, origin=ORIGIN, path='/search'):
            return urllib.request.urlopen(urllib.request.Request(base + path, data=json.dumps(body).encode(),
                headers={'Origin': origin, 'Content-Type': 'application/json'}))
        try:
            for body, origin, path, expected in [
                ({'query': '多馬'}, 'https://evil.example', '/search', 403),
                ({'query': '多馬', 'model': 'other'}, ORIGIN, '/search', 400),
                ({'messages': []}, ORIGIN, '/search', 400),
                ({'query': 'x'}, ORIGIN, '/search', 400),
                ({'query': '多' * 201}, ORIGIN, '/search', 400),
                ({'query': '多馬'}, ORIGIN, '/v1/chat/completions', 404)]:
                with self.assertRaises(urllib.error.HTTPError) as error:
                    post(body, origin, path)
                self.assertEqual(error.exception.code, expected)
            response = post({'query': '多馬'})
            self.assertEqual(response.headers['Access-Control-Allow-Origin'], ORIGIN)
            self.assertEqual(json.load(response)['results'][0]['ref'], 'JHN 20:25-27')
            self.assertEqual(len(self.calls), 1)
        finally:
            server.shutdown(); server.server_close(); thread.join()

if __name__ == '__main__':
    unittest.main()
