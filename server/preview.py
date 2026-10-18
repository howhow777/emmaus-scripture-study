#!/usr/bin/env python3
"""Serve a review site and isolated search corpus without changing production."""
import argparse,json,mimetypes
from pathlib import Path
from urllib.parse import urlsplit,unquote
from http.server import ThreadingHTTPServer
from search_service import Search,make_handler

def handler(search,site,origin):
    parent=make_handler(search,origin)
    class Preview(parent):
        def do_GET(self):
            path=unquote(urlsplit(self.path).path)
            if path=='/health':return super().do_GET()
            if path=='/semantic-config.js':
                body=('window.EMMAUS_SEMANTIC_CONFIG='+json.dumps({'endpoint':'/search','corpus':search.index['corpus']})+';\n').encode()
                content_type='application/javascript'
            else:
                relative=path.lstrip('/') or 'index.html'
                file=(site/relative).resolve()
                allowed=(relative in {'index.html','graph.html','coverage.html','dating.html','graph.css','graph-data.js','graph.bundle.js','scripture-preview.css','scripture-preview.js','scripture-previews-data.js','scripture-search-data.js','README.md','THIRD_PARTY_NOTICES.txt'} or relative.startswith(('data/','reports/')) and file.suffix in ['.json','.md'])
                if not allowed or not file.is_relative_to(site) or not file.is_file():return self.reply(404,{'error':'Not found'})
                body=file.read_bytes();content_type=mimetypes.guess_type(str(file))[0] or 'application/octet-stream'
            self.send_response(200);self.send_header('Content-Type',content_type);self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(body)
    return Preview

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--site',type=Path,required=True);p.add_argument('--runtime',type=Path,required=True);p.add_argument('--origin',required=True);p.add_argument('--port',type=int,default=18892);a=p.parse_args()
    search=Search(a.runtime);httpd=ThreadingHTTPServer(('127.0.0.1',a.port),handler(search,a.site.resolve(),a.origin));print('Review server port',a.port,'corpus',search.index['corpus'],flush=True);httpd.serve_forever()
