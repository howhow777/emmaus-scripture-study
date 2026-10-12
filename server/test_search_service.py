import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer
from search_service import MODEL, ORIGIN, Search, ServiceError, make_handler, selected_results


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

    def test_whitelist_deduplicates_and_drops_invented_references(self):
        result = selected_results(self.index, {'refs': ['XXX 1:1', 'JHN 20:25-27', 'JHN 20:25-27'], 'entryIds': ['E999']})
        self.assertEqual([x['ref'] for x in result], ['JHN 20:25-27'])
        self.assertNotIn('text', result[0])

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
        with self.assertRaises(ServiceError):
            self.search.lookup('想摸釘痕才信', 'one')

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
