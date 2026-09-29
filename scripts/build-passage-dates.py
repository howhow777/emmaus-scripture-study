#!/usr/bin/env python3
"""Render cited passage dates into the reading page and a static source index.

The source of truth is data/passage-dates.json. Run with --check in CI to
verify both generated pages without changing them.
"""

import argparse
import html
import json
import re
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "index.html"
DATES = ROOT / "data" / "passage-dates.json"
DETAILS = ROOT / "dating.html"
GRAPH = ROOT / "graph-data.js"
BOOK_ORDER = (
    "GEN EXO LEV NUM DEU JOS JDG RUT 1SA 2SA 1KI 2KI 1CH 2CH EZR NEH EST "
    "JOB PSA PRO ECC SNG ISA JER LAM EZK DAN HOS JOL AMO OBA JON MIC NAM HAB "
    "ZEP HAG ZEC MAL MAT MRK LUK JHN ACT ROM 1CO 2CO GAL EPH PHP COL 1TH "
    "2TH 1TI 2TI TIT PHM HEB JAS 1PE 2PE 1JN 2JN 3JN JUD REV"
).split()

LINK_RE = re.compile(
    r'<a\b(?=[^>]*\bhref="https://www\.bible\.com/bible/46/)[^>]*>.*?</a>',
    re.DOTALL,
)
HREF_RE = re.compile(r'\bhref="([^"]+)"')
BIBLE_RE = re.compile(
    r"https://www\.bible\.com/bible/46/([0-9A-Z]+)\.(\d+)"
    r"(?:\.(\d+(?:-\d+)?))?\.CUNP-%E7%A5%9E"
)
GENERATED_RE = re.compile(
    r'<!-- passage-date:start --><span class="dated-citation">'
    r'(?P<link><a\b[^>]*>.*?</a>)'
    r'<small class="passage-date">.*?</small></span><!-- passage-date:end -->',
    re.DOTALL,
)


def canonical_ref(url):
    match = BIBLE_RE.fullmatch(url)
    if not match:
        raise ValueError(f"Unexpected Bible.com URL: {url}")
    return f"{match[1]} {match[2]}" + (f":{match[3]}" if match[3] else "")


def ref_id(ref):
    return "date-" + re.sub(r"[^A-Za-z0-9]+", "-", ref).strip("-")


def date_text(item):
    def label(field):
        value = item[field]["label"]
        return value + ("（有分歧）" if item[field]["certainty"] == "contested" else "")

    return f"背景：{label('background')}｜成書：{label('composition')}"


def load_dates():
    data = json.loads(DATES.read_text(encoding="utf-8"))
    if data["version"] != 1 or not data["references"] or not data["sources"]:
        raise ValueError("Invalid passage-dates.json")
    for ref, item in data["references"].items():
        for field in ("background", "composition"):
            if not item[field]["label"] or item[field]["certainty"] not in {
                "approximate", "contested", "unknown"
            }:
                raise ValueError(f"Invalid {field} date: {ref}")
        if not item["note"] or not item["sourceIds"]:
            raise ValueError(f"Missing date note or source: {ref}")
        for source_id in item["sourceIds"]:
            source = data["sources"].get(source_id)
            if not source or not source["url"].startswith("https://"):
                raise ValueError(f"Invalid date source {source_id}: {ref}")
    return data


def render_index(original, dates):
    source = GENERATED_RE.sub(lambda match: match["link"], original)
    seen = set()

    def replace(match):
        link = match.group(0)
        href = HREF_RE.search(link)
        if href is None:
            raise ValueError(f"Scripture anchor has no href: {link[:120]}")
        ref = canonical_ref(html.unescape(href[1]))
        item = dates["references"].get(ref)
        if item is None:
            raise ValueError(f"No dating record for linked passage: {ref}")
        seen.add(ref)
        label = html.escape(date_text(item))
        detail_href = f"dating.html#{ref_id(ref)}"
        return (
            '<!-- passage-date:start --><span class="dated-citation">'
            + link
            + f'<small class="passage-date">{label} '
            + f'<a href="{detail_href}" aria-label="查看 {html.escape(ref)} 的年代依據">依據</a></small>'
            + '</span><!-- passage-date:end -->'
        )

    result = LINK_RE.sub(replace, source)
    if len(seen) < 550:
        raise ValueError(f"Expected at least 550 distinct linked passages, found {len(seen)}")
    return result, seen


def book_names():
    source = GRAPH.read_text(encoding="utf-8")
    prefix = "window.EMMAUS_GRAPH_DATA="
    if not source.startswith(prefix):
        raise ValueError("graph-data.js is not in the expected format")
    graph = json.loads(source[len(prefix):].rstrip().removesuffix(";"))
    return {code: item["name"] for code, item in graph["books"].items()}


def sort_ref(ref, order):
    code, location = ref.split(" ", 1)
    chapter, _, verse = location.partition(":")
    return (order.get(code, len(order)), int(chapter), int(verse.split("-")[0] or 0))


def render_details(dates, names):
    references = dates["references"]
    order = {code: index for index, code in enumerate(BOOK_ORDER)}
    groups = defaultdict(list)
    for ref in sorted(references, key=lambda item: sort_ref(item, order)):
        groups[ref.split(" ", 1)[0]].append(ref)
    parts = ["""<!doctype html>
<html lang="zh-Hant-TW"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>經文年代與依據｜以馬忤斯之路</title>
<style>
:root{--ink:#183a32;--paper:#f7f5ee;--line:#dce1d6;--muted:#52675b}*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:#263c33;font:16px/1.8 -apple-system,BlinkMacSystemFont,"PingFang TC","Noto Sans TC",sans-serif}
header,main{max-width:900px;margin:auto;padding:18px 24px}header{display:flex;gap:20px;flex-wrap:wrap;border-bottom:1px solid var(--line)}
a{color:#275f4d;text-underline-offset:3px}a:focus-visible{outline:3px solid #2b6c59;outline-offset:3px}
h1,h2{font-family:Georgia,"Noto Serif TC",serif;color:var(--ink);line-height:1.4}h1{font-size:clamp(30px,5vw,44px);margin:24px 0 10px}
h2{font-size:25px;margin:42px 0 14px;border-bottom:1px solid var(--line);padding-bottom:8px}h3{font-size:17px;margin:0 0 6px}
.intro{color:var(--muted);max-width:75ch}.date-record{background:#fffefb;border:1px solid var(--line);border-radius:8px;margin:12px 0;padding:16px 20px;scroll-margin-top:15px}
.date-record:target{outline:3px solid #a27a36}.date-record p{margin:6px 0}.date-pair{font-weight:600}.date-note{color:var(--muted)}
.sources{margin:5px 0 0;padding-left:22px;font-size:14px}.sources li{margin:3px 0}footer{max-width:900px;margin:40px auto;padding:20px 24px;border-top:1px solid var(--line)}
@media(max-width:600px){header,main,footer{padding-left:16px;padding-right:16px}.date-record{padding:14px}}
</style></head><body><header><a href="index.html#why">研究首頁</a><a href="graph.html">互動圖譜</a></header><main>
<h1>經文年代與依據</h1><p class="intro">「背景」指敘事、詩歌或宣講所處的大致時代；「成書」指文本形成的大致時期，兩者可能相隔很久。年份與世紀是研究估計，不是精確日期；無法合理推定時標為年代未定。此頁依研究網站引用的段落列出說明與資料來源。</p>
"""]
    for code, refs in groups.items():
        parts.append(f'<section aria-labelledby="book-{code}"><h2 id="book-{code}">{html.escape(names.get(code, code))}</h2>')
        for ref in refs:
            item = references[ref]
            _, location = ref.split(" ", 1)
            display_ref = f"{names.get(code, code)} {location}"
            sources = "".join(
                f'<li><a href="{html.escape(dates["sources"][source_id]["url"], quote=True)}" target="_blank" rel="noopener noreferrer">{html.escape(dates["sources"][source_id]["title"])}</a></li>'
                for source_id in item["sourceIds"]
            )
            parts.append(
                f'<article class="date-record" id="{ref_id(ref)}"><h3>{html.escape(display_ref)}</h3>'
                f'<p class="date-pair">{html.escape(date_text(item))}</p>'
                f'<p class="date-note">{html.escape(item["note"])}</p>'
                f'<ul class="sources">{sources}</ul></article>'
            )
        parts.append("</section>")
    parts.append('</main><footer><a href="index.html#why">回到以馬忤斯之路</a></footer></body></html>\n')
    return "".join(parts)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify generated files without writing")
    args = parser.parse_args()
    dates = load_dates()
    index, seen = render_index(INDEX.read_text(encoding="utf-8"), dates)
    missing = set(dates["references"]) - seen
    if missing:
        print(f"Date records without an index link (may appear in graph details): {len(missing)}")
    details = render_details(dates, book_names())
    if args.check:
        if INDEX.read_text(encoding="utf-8") != index or not DETAILS.exists() or DETAILS.read_text(encoding="utf-8") != details:
            parser.exit(1, "Passage date pages are out of date\n")
        print("Passage date pages are current")
    else:
        INDEX.write_text(index, encoding="utf-8")
        DETAILS.write_text(details, encoding="utf-8")
        print(f"Updated passage dates for {len(seen)} distinct linked passages")


if __name__ == "__main__":
    main()
