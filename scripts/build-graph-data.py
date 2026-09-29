#!/usr/bin/env python3
"""Build the graph's static data from the existing reading page.

Run normally to update graph-data.js, or with --check to verify that it is current.
The site itself has no Python or network dependency.
"""

import argparse
import json
import re
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "index.html"
OUTPUT = ROOT / "graph-data.js"
SPEECH = ROOT / "data" / "jesus-speech.json"

BOOK_GROUPS = {
    "pentateuch": "GEN EXO LEV NUM DEU",
    "history": "JOS JDG RUT 1SA 2SA 1KI 2KI 1CH 2CH EST",
    "poetry": "JOB PSA PRO SNG",
    "major-prophets": "ISA JER LAM EZK DAN",
    "minor-prophets": "HOS JOL AMO JON MIC NAM HAB ZEP HAG ZEC MAL",
    "gospels": "MAT MRK LUK JHN",
    "acts": "ACT",
    "letters": "ROM 1CO 2CO GAL EPH PHP COL 2TH TIT HEB JAS 1PE 2PE 1JN",
    "revelation": "REV",
}
GROUP_BY_BOOK = {
    code: group for group, codes in BOOK_GROUPS.items() for code in codes.split()
}


class SourceParser(HTMLParser):
    """Capture the embedded records and the two scripture-link sections per card."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.scripts = {}
        self.cards = []
        self.script_id = None
        self.script_chunks = []
        self.card = None
        self.section = None
        self.link = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = set(attrs.get("class", "").split())
        if tag == "script" and attrs.get("id") in {"fullData", "searchData"}:
            self.script_id = attrs["id"]
            self.script_chunks = []
        elif tag == "article" and "entry" in classes:
            if self.card is not None:
                raise ValueError("Nested entry card")
            self.card = {"id": attrs["id"], "ot": [], "nt": [], "sections": 0}
            self.cards.append(self.card)
        elif tag == "section" and self.card is not None and "note-section" in classes:
            self.card["sections"] += 1
            if self.card["sections"] > 2:
                raise ValueError(f"Too many note sections in {self.card['id']}")
            self.section = "ot" if self.card["sections"] == 1 else "nt"
        elif tag == "a" and self.section is not None and "scripture" in classes:
            self.link = {"href": attrs["href"], "label": ""}

    def handle_data(self, data):
        if self.script_id is not None:
            self.script_chunks.append(data)
        elif self.link is not None:
            self.link["label"] += data

    def handle_endtag(self, tag):
        if tag == "script" and self.script_id is not None:
            self.scripts[self.script_id] = json.loads("".join(self.script_chunks))
            self.script_id = None
        elif tag == "a" and self.link is not None:
            self.link["label"] = self.link["label"].strip()
            self.card[self.section].append(self.link)
            self.link = None
        elif tag == "section" and self.section is not None:
            self.section = None
        elif tag == "article" and self.card is not None:
            if self.card["sections"] != 2:
                raise ValueError(f"Expected two note sections in {self.card['id']}")
            self.card = None


def ref_from_href(href):
    match = re.fullmatch(
        r"https://www\.bible\.com/bible/46/([0-9A-Z]+)\.(\d+)\.([0-9-]+)\.CUNP-%E7%A5%9E",
        href,
    )
    if not match:
        raise ValueError(f"Unexpected Bible.com link: {href}")
    return f"{match[1]} {match[2]}:{match[3]}"


def verse_range(ref):
    match = re.fullmatch(r"([0-9A-Z]+) (\d+):(\d+)(?:-(\d+))?", ref)
    if not match:
        raise ValueError(f"Unexpected verse reference: {ref}")
    first, last = int(match[3]), int(match[4] or match[3])
    if first > last:
        raise ValueError(f"Reversed verse reference: {ref}")
    return match[1], match[2], first, last


def build():
    parser = SourceParser()
    parser.feed(SOURCE.read_text(encoding="utf-8"))
    full = parser.scripts["fullData"]
    search = parser.scripts["searchData"]
    cards = parser.cards
    ids = [record["id"] for record in full]
    if len(full) != 186 or len(set(ids)) != 186:
        raise ValueError("Expected 186 distinct study entries")
    if ids != [record["id"] for record in search] or ids != [card["id"] for card in cards]:
        raise ValueError("Entry order differs between fullData, searchData and cards")
    if sum(bool(record["core"]) for record in full) != 49:
        raise ValueError("Expected 49 core entries")

    books = {}
    references = {}
    entries = []
    for record, search_record, card in zip(full, search, cards):
        if any(record[key] != search_record[key] for key in ("ev", "tags", "core", "jesus")):
            raise ValueError(f"Search data disagrees with {record['id']}")
        entry = {key: record[key] for key in ("id", "title", "ev", "tags", "core", "jesus")}
        entry["text"] = search_record["text"]
        for side in ("ot", "nt"):
            refs = record[side].split(";")
            links = card[side]
            if len(refs) != len(links) or len(set(refs)) != len(refs):
                raise ValueError(f"Reference/link mismatch in {record['id']} {side}")
            entry[side] = []
            for ref, link in zip(refs, links):
                if ref != ref_from_href(link["href"]):
                    raise ValueError(f"Reference/link mismatch in {record['id']}: {ref}")
                label = link["label"]
                name_match = re.fullmatch(r"(.+?)\s+\d+:.+", label)
                if not name_match:
                    raise ValueError(f"Unexpected scripture label: {label}")
                code = ref.split(" ", 1)[0]
                if code not in GROUP_BY_BOOK:
                    raise ValueError(f"Unclassified Bible book: {code}")
                book = {"name": name_match[1], "testament": side, "group": GROUP_BY_BOOK[code]}
                if code in books and books[code] != book:
                    raise ValueError(f"Inconsistent book name/testament: {code}")
                books[code] = book
                passage = {"ref": ref, "label": label, "href": link["href"]}
                if ref in references and references[ref] != passage:
                    raise ValueError(f"Inconsistent shared reference: {ref}")
                references[ref] = passage
                entry[side].append(passage)
        entries.append(entry)

    speech = []
    if SPEECH.exists():
        speech = json.loads(SPEECH.read_text(encoding="utf-8"))
        if not isinstance(speech, list):
            raise ValueError("data/jesus-speech.json must contain an array")
        by_id = {entry["id"]: entry for entry in entries}
        seen = set()
        for item in speech:
            entry_id, nt_ref = item["entryId"], item["ntRef"]
            if entry_id not in by_id or nt_ref not in [p["ref"] for p in by_id[entry_id]["nt"]]:
                raise ValueError(f"Speech parent passage is missing: {entry_id} {nt_ref}")
            if (entry_id, nt_ref) in seen or not item["spans"]:
                raise ValueError(f"Duplicate or empty speech record: {entry_id} {nt_ref}")
            seen.add((entry_id, nt_ref))
            parent_book, parent_chapter, parent_first, parent_last = verse_range(nt_ref)
            for span in item["spans"]:
                if span["ref"] != ref_from_href(span["href"]) or not span["label"]:
                    raise ValueError(f"Invalid speech span: {entry_id} {nt_ref}")
                book, chapter, first, last = verse_range(span["ref"])
                if (book, chapter) != (parent_book, parent_chapter) or not (
                    parent_first <= first <= last <= parent_last
                ):
                    raise ValueError(f"Speech span is outside source passage: {entry_id} {nt_ref}")

    return {"version": 1, "entries": entries, "books": books, "speech": speech}


def main():
    arg_parser = argparse.ArgumentParser(description=__doc__)
    arg_parser.add_argument("--check", action="store_true", help="verify graph-data.js without writing")
    args = arg_parser.parse_args()
    output = "window.EMMAUS_GRAPH_DATA=" + json.dumps(
        build(), ensure_ascii=False, separators=(",", ":")
    ) + ";\n"
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_text(encoding="utf-8") != output:
            arg_parser.exit(1, "graph-data.js is missing or out of date\n")
        print("graph-data.js is current")
    else:
        OUTPUT.write_text(output, encoding="utf-8")
        print("Updated graph-data.js")


if __name__ == "__main__":
    main()
