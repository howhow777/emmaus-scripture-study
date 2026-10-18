#!/usr/bin/env python3
"""Build complete, offline scripture previews from pinned Wikisource CUV pages.

The preview text is the Wikisource transcription adjusted toward 1919 usage,
not the CUNP-神 edition reached by the existing Bible.com links. `--fetch`
downloads pinned page revisions into a local cache; the website uses only the
generated JavaScript. `--check` never uses the network.
"""

import argparse
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import unquote
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "index.html"
GRAPH = ROOT / "graph-data.js"
OUTPUT = ROOT / "scripture-previews-data.js"
SEARCH_OUTPUT = ROOT / "scripture-search-data.js"
DEFAULT_SOURCE_DIR = ROOT.parent / "scripture-source" / "wikisource-1919"
SOURCE = {
    "label": "和合本（維基文庫 1919 用字版，神版）",
    "url": "https://zh.wikisource.org/wiki/聖經_(和合本)",
    "note": "維基文庫依 1919 年用字校訂；預覽與外連的 Bible.com 新標點和合本（CUNP-神）可能有文字差異。",
}

# Page revision and SHA-256 for every book currently cited on the site.
# These make a future rebuild independent of changes to live wiki pages.
PAGES = {
    "1CH": (334706, "73292ad3b38d66b5e8d64946602f7dd20fe2fc2fb263d8861b00b3fc19e79c93"),
    "1CO": (1338104, "8097f6f4bb26118531edec126e8f2aaa3dd688fe0dfc4b3e10582642ded2608b"),
    "1JN": (334875, "bc3a903dd4ca9faa19768542167eee1f8f601b896f74db61b0c6df946e11e9f9"),
    "1KI": (334715, "699f2bdf7d358d4106ea74c104c2245aae118c53e070fde9b0296f6b43193621"),
    "1PE": (1338096, "d2ab6a5ce1dadc109ee2154bda9096390081aaca9cc23a814d19ecf2b8f16d8e"),
    "1SA": (334702, "25e88c93b2c8e4847b1961cf97c4dfd9ee912cd49ee30689cf7419c20e316b91"),
    "2CH": (334707, "d11a8804a11b660cb43136cb4d35345dc485a63b7e98cb72bd21f1c27da70176"),
    "2CO": (1338099, "7fafef8b31ca034078edb741f8aab7031678ed7a0e675c111c080b008f7ce4b2"),
    "2KI": (940430, "8206ad802345cbe61e6e24cd2ed1422dd4121613eba013c428bd0ee0b8482e35"),
    "2PE": (1338093, "3c366a6e72e0479d90df80381936152040ff0914a71798be1de16d3380f66c79"),
    "2SA": (334703, "7943ec1f812cf6199706be85b849cc73402679b46e214b4f6467422ac224e3fc"),
    "2TH": (335269, "e95f01d9c08b9f1ca6b55dc3fce427dc08a47d16067e3cbf2abaccc08f82fa8d"),
    "ACT": (1338141, "7b1eab18b665c41429b5ad951996ebf67ac1cc1cff08f2bf1724143cb0f3ec5f"),
    "AMO": (334727, "81a0a8f0a858f283814f7429d31040788d54b82daf2cdb0bd0c3e17daab5233e"),
    "COL": (335267, "5d2712e669b588802dfdbe089431e86b669cfbb62c12fe82bb0250c1c4f03859"),
    "DAN": (413070, "b9ccc0264639ff02b8164c1450f16c5ab7530aa9b888a2512c2a2f11560512bc"),
    "DEU": (334698, "8d0855c369e22f626fb2793f1bc87fe8264a2507d5b8d93cdf87210433007d1e"),
    "EPH": (1338100, "821956bebff473e49b25043111039ebd1645926270ab63c04ca8887da4004d01"),
    "EST": (413074, "3514842f7ae67c5a1eb74c907dd75e861512e9930c5ed3cd641d9824246bcc5f"),
    "EXO": (413073, "ca551aef0eab760ee3c859f997134a6444dc034db10762425da97fa694355d4a"),
    "EZK": (334775, "2218075051947561913fa1844e011248f9a876da63389496723748f9b633b317"),
    "GAL": (1338095, "5d69a235125056138d8ca1dcea67344cf85629a194b8d3f8ac9d26878fc449c0"),
    "GEN": (2272026, "58d7de8800f638658194f732cbb1e5ed4486b82d5d74e466581c1611d78ba200"),
    "HAB": (334732, "a763c1401ad50a18033656f78c88ed97c59920f8ae16d54a0bbd99f95b5a00b2"),
    "HAG": (334734, "304477d1ee9dc39cd05e47a4e9939236c3a5cdd1841eef1034b25773023132ec"),
    "HEB": (1338101, "fa852addee45e7f968d76d9e6bc8f7b66f1cad905d63e58bc92974b3f4f9ed12"),
    "HOS": (334720, "b48c787fc68841838fabdbf913727ba13383b7f39c75ee21a0d2b27baf1f2ca2"),
    "ISA": (2522911, "cb3c5654f688e68a63138c2b57ea02986505d02b1616791856a08baea76a3097"),
    "JAS": (1338097, "a6de04acc2f5f1d227e9938d1a0d0eec9924e5c44c0b74faa04b626cf6768495"),
    "JDG": (413072, "20159219c97401df50dea3413789420798047d62e930d908a34c53b9bf33d1df"),
    "JER": (334723, "e961c56ef513be81fc2c67514f1bb81bf7ea55ffca3fd79e2b2bcc3c331fc599"),
    "JHN": (1338105, "4dc7ed737c7f18fab98539ccc5d183d714f3c86acd6cebd11cefb6f22307c216"),
    "JOB": (334726, "e8765767563db8be1da4ac91b9f227b8af2208bccbfce86cdc96fe65f4aa10d9"),
    "JOL": (2004411, "1f6fa1b33e3478f7d1a558b7fd76f5e97b27932b22dd905173f349932ce980c1"),
    "JON": (7903170, "9e9551c796208f9f9f18b2c9d1833ebb8f0c5212f9e009896601a78d448679fe"),
    "JOS": (334699, "918f836c4ed3cea047c7c19ddbda074aee6fc6cbcbcd7a3a0c67cb408994cbc1"),
    "LAM": (334778, "5855d9344df969f63560ca46fa1a4f9650b1adf34aede621a62c93c348e83bf2"),
    "LEV": (334694, "8c38462d743ad2c2d5b52c00b056a9036492ee05cba8ac8b75da2a456eeb9232"),
    "LUK": (1338069, "7c91fd5e2e652ab375d3c9233000bd1c6bae5c3e1c5b72c0fcee913384de4ffc"),
    "MAL": (334736, "415395225e5f73f58fcc54d67af07e3adb9cb29cc8613783e82482e88bc094a0"),
    "MAT": (1337560, "9b53db91ad895b57c4dc0ed24bfe570a1f637317ffc8053743c6943b1326f500"),
    "MIC": (334730, "f92b266a09d67e7ff0d32e853e9bfdf79a0417039a86f0db75d5fbac575e3b47"),
    "MRK": (1337559, "bbc2d54215fcd275f0da9424d94ae0210dfdb6e26eb29443cc7150e1733f6238"),
    "NAM": (334731, "6a86ee6b6084071de01a9527ab2201b001dcb1ad0198b274999f0098d034ff91"),
    "NUM": (334697, "42b20eb0a9357c0a202eb69f1c560c8df79eab7fe80dfa37059f69cc5cae6af0"),
    "PHP": (335266, "2730a48bcfec3d9f8c1132d23d652e639c89f9892e21cd17d60bdef41a08ea87"),
    "PRO": (2004286, "5cc082fdf60332a3bc7b1ea22d74b7a6307ad91ea0f32f1a194d193e5d551578"),
    "PSA": (1304951, "5ab690ff0e53b7baae91fb4e52f6be703393e0a821f0a21aade924d21ddbfd99"),
    "REV": (414061, "a1620558d9c4030cb9c68c3391f34a9d96baaba854a90f676079db08058d1486"),
    "ROM": (1338103, "a47e7e37c41b7fd1d490ad87e4f3ac26c9f5375e731740efd473e41c849d7414"),
    "RUT": (334701, "a80f213066ffb05f006762a1bb654b0474b9399f2a09ab82aae39011467b91d2"),
    "SNG": (2004216, "d612cdef3387f86f9968e639729de343acf488d51780ebb1b7b40eb782c028a1"),
    "TIT": (335272, "657ca984d0d73bfbf3b1df455102e0a80f379f399c6fbd0bcabea40d1bf32053"),
    "ZEC": (413067, "adcc8f29ab05cbd37d1a89c9a94d1b4dc633c3b63d5b1425bc21f168a7e284b9"),
    "ZEP": (334733, "50d7fda5d86bcbdd0332bbd6a22f2b75690be8cb968fbf2494e012aec9834814"),
    "1TH": (335268, "08f6519069fd49dc1a4495d004b7fc427d9aaf7922335977ca78f3be95afffa5"),
    "1TI": (1338102, "33d187002cab8f87e8e7f91f90b82be3e3b1ac87f8c13291e6fb6107698305b7"),
    "2TI": (1338094, "57cf0f8d84b05f0c5b61292d860ee45965920d8e908ed44625f0c83c046a933b"),
    "PHM": (335273, "da2e46de4e612441d51d689ae7589997ccc09e54b67252d4ae0417b934361c0f"),
    "2JN": (334876, "dbed5e012952ec2d1a839f9d0eb9698961775eb562fecbc447d7c0927b19a00f"),
    "3JN": (335274, "2e9c6b6686d95ed08a3d69c64a0fe1f00554304e4a034b88ae3bde4b0a476f8e"),
    "JUD": (335275, "8efb7d4b29442f733f58c616186701f983b9fcc59d4711d8756b585e01116b66"),
}

# These consecutive verse markers share one source paragraph. Cite the complete
# group and retain the source numbering rather than inventing a split text.
COMBINED = {('LUK',1,1):2,('LUK',2,34):35,('ACT',1,24):25,
            ('ACT',4,29):30,('EPH',6,2):3,('COL',2,20):21}

LINK_RE = re.compile(r"https://www\.bible\.com/bible/46/([0-9A-Z.%-]+)")
REF_RE = re.compile(r"([0-9A-Z]+)\.(\d+)(?:\.(\d+)(?:-(\d+))?)?\.CUNP-神")
VERSE_RE = re.compile(r"\{\{\s*verse\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\}\}", re.I)
TEMPLATE_RE = re.compile(r"\{\{([^{}]+)\}\}")


def references():
    """Collect every current Bible.com destination, including Jesus speech spans."""
    found = set()
    for file in (INDEX, GRAPH, ROOT / "coverage.html"):
        for encoded in LINK_RE.findall(file.read_text(encoding="utf-8")):
            match = REF_RE.fullmatch(unquote(encoded))
            if not match:
                raise ValueError(f"Unexpected Bible.com passage: {encoded}")
            book, chapter, first, last = match.groups()
            first, last = int(first) if first else None, int(last) if last else None
            if last is not None and (first is None or last < first):
                raise ValueError(f"Reversed verse range: {encoded}")
            found.add((book, int(chapter), first, last))
    if not found:
        raise ValueError("No Bible.com passages found")
    return sorted(found, key=lambda ref: (ref[0], ref[1], ref[2] or 0, ref[3] or 0))


def book_names():
    data = GRAPH.read_text(encoding="utf-8")
    prefix = "window.EMMAUS_GRAPH_DATA="
    if not data.startswith(prefix):
        raise ValueError("graph-data.js has unexpected format")
    return {code: value["name"] for code, value in json.loads(data[len(prefix):].rstrip(";\n"))["books"].items()}


def source_text(book, source_dir):
    if book not in PAGES:
        raise ValueError(f"No pinned Wikisource revision for {book}")
    path = source_dir / f"{book}.txt"
    raw = path.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != PAGES[book][1]:
        raise ValueError(f"Source checksum differs for {book}: {actual}")
    return raw.decode("utf-8")


def parse_book(book, source_dir):
    source = source_text(book, source_dir)
    markers = list(VERSE_RE.finditer(source))
    if not markers:
        raise ValueError(f"No verse markers in {book}")
    chapters = {}
    for position, marker in enumerate(markers):
        chapter, verse = int(marker[1]), int(marker[2])
        end = markers[position + 1].start() if position + 1 < len(markers) else len(source)
        raw_lines = source[marker.end():end].splitlines()
        body_lines = []
        for line in raw_lines:
            stripped = line.strip()
            if stripped.startswith((":", "{{gototop", "{{footer", "{{Pd/", "==")):
                break
            if stripped:
                body_lines.append(stripped)
        verse_body = "".join(body_lines)
        verses = chapters.setdefault(chapter, {})
        if verse in verses:
            raise ValueError(f"Repeated marker in {book} {chapter}:{verse}")
        verses[verse] = verse_body

    # The pinned Isaiah source accidentally places 4:3 and 4:4 on one line,
    # after the 4:4 marker and in reverse order. Correct only that known case.
    if book == "ISA":
        fourth = chapters[4]
        wrong = fourth[4]
        if fourth[3] != "" or "那時、賸在錫安" not in wrong:
            raise ValueError("Wikisource Isaiah 4:3–4 changed; review correction")
        fourth[4], third = wrong.split("那時、", 1)
        fourth[3] = "那時、" + third
        fourth[4] = fourth[4].rstrip("、") + "。"
    return chapters


def plain_verse(raw):
    # Superscript cross-reference numerals and textual-variant notes are not
    # scripture words. Retain dotted text and Psalm superscriptions.
    raw = re.sub(r"<sup\b[^>]*>.*?</sup>", "", raw, flags=re.I | re.S)
    # A verse consisting solely of a textual-variant note must remain visible
    # as a note rather than silently becoming an empty canonical verse.
    variant_only = re.fullmatch(r"\s*\{\{\*\|(.+)\}\}\s*", raw, flags=re.S)
    if variant_only:
        return "（本來源異文註：" + plain_verse(variant_only[1]) + "）"
    raw = re.sub(r"<ref\b[^>]*>.*?</ref>", "", raw, flags=re.I | re.S)

    def template(match):
        parts = match[1].split("|")
        name = parts[0].strip().lower()
        if name == "*":
            return ""
        if name in {"udots", "-", "!"} and len(parts) >= 2:
            return parts[1]
        raise ValueError(f"Unexpected template in verse: {match[0]}")

    while "{{" in raw:
        updated = TEMPLATE_RE.sub(template, raw)
        if updated == raw:
            raise ValueError(f"Unparsed template in verse: {raw}")
        raw = updated
    raw = re.sub(r"\[\[[^\]|]+\|([^\]]+)\]\]", r"\1", raw)
    raw = re.sub(r"\[\[([^\]]+)\]\]", r"\1", raw)
    raw = re.sub(r"<[^>]+>", "", raw)
    raw = re.sub(r"[\t\r\n ]+", " ", raw).strip()
    if not raw or any(marker in raw for marker in ("{{", "}}", "[[", "]]", "<", ">")):
        raise ValueError(f"Empty or marked-up verse: {raw}")
    return raw


def passage_key(book, chapter, first, last):
    if first is None:
        return f"{book} {chapter}"
    suffix = f"-{last}" if last is not None else ""
    return f"{book} {chapter}:{first}{suffix}"


def build(source_dir):
    refs, names = references(), book_names()
    books = {ref[0] for ref in refs}
    if books - names.keys():
        raise ValueError(f"Missing book names: {sorted(books - names.keys())}")
    parsed = {book: parse_book(book, source_dir) for book in books}
    passages = {}
    search_passages = {}
    for book, chapter, first, last in refs:
        chapter_verses = parsed[book].get(chapter)
        if not chapter_verses:
            raise ValueError(f"Missing chapter: {book} {chapter}")
        if first is None:
            final = max(chapter_verses)
            numbers = range(1, final + 1)
            label = f"{names[book]} {chapter} 章"
        else:
            final = last or first
            numbers = range(first, final + 1)
            label = f"{names[book]} {chapter}:{first}" + (f"–{last}" if last else "")
        missing = [number for number in numbers if number not in chapter_verses]
        if missing:
            raise ValueError(f"Missing verses in {book} {chapter}: {missing}")
        verses = []
        skipped = set()
        for number in numbers:
            if number in skipped:
                continue
            combined_last = COMBINED.get((book, chapter, number))
            if combined_last:
                if combined_last not in numbers:
                    raise ValueError(f'Source combines {book} {chapter}:{number}-{combined_last}; cite the complete group')
                if chapter_verses[number] != '':
                    raise ValueError(f'Combined source changed: {book} {chapter}:{number}')
                verses.append({'number': number, 'numberLabel': f'{number}–{combined_last}',
                               'coveredNumbers': list(range(number, combined_last+1)),
                               'text': plain_verse(chapter_verses[combined_last])})
                skipped.update(range(number+1,combined_last+1))
                continue
            raw = chapter_verses[number]
            if book == "PSA" and chapter == 8 and number in (6, 7):
                if raw != "":
                    raise ValueError("Wikisource Psalm 8:6–8 verse grouping changed; review correction")
                continue
            verse = {"number": number, "text": plain_verse(raw)}
            if book == "PSA" and chapter == 8 and number == 8:
                verse["numberLabel"] = "6–8"
            verses.append(verse)
        passage = {
            "label": label,
            "verses": verses,
            "total": len(numbers),
        }
        key = passage_key(book, chapter, first, last)
        passages[key] = passage
        search_passages[key] = verses
    supplemental = json.loads((ROOT / "data/coverage/supplemental-passages.json").read_text())
    return {"source": SOURCE, "passages": passages}, {"source": SOURCE, "passages": search_passages, "supplemental": {item["ref"]: item for item in supplemental}}


def serialized(data):
    return "window.EMMAUS_SCRIPTURE_PREVIEWS=" + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n"


def serialized_search(data):
    return "window.EMMAUS_SCRIPTURE_SEARCH=" + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n"


def covered_numbers(verses):
    """Expand source-preserved combined numbering without changing source text."""
    numbers = []
    for verse in verses:
        if "coveredNumbers" in verse:
            numbers.extend(verse["coveredNumbers"])
        elif re.fullmatch(r"\d+[–-]\d+", str(verse.get("numberLabel", ""))):
            first, last = map(int, re.split("[–-]", verse["numberLabel"]))
            numbers.extend(range(first, last + 1))
        else:
            numbers.append(verse["number"])
    return numbers


def check_existing():
    if not OUTPUT.exists():
        raise ValueError("scripture-previews-data.js is missing")
    current = OUTPUT.read_text(encoding="utf-8")
    prefix = "window.EMMAUS_SCRIPTURE_PREVIEWS="
    if not current.startswith(prefix) or not current.endswith(";\n"):
        raise ValueError("scripture-previews-data.js has unexpected format")
    data = json.loads(current[len(prefix):-2])
    expected_keys = {passage_key(*ref) for ref in references()}
    if data.get("source") != SOURCE or set(data.get("passages", {})) != expected_keys:
        raise ValueError("Preview source or reference coverage is out of date")
    for key, item in data["passages"].items():
        if not item.get("label") or not isinstance(item.get("total"), int) or item["total"] < 1:
            raise ValueError(f"Invalid preview metadata: {key}")
        verses = item.get("verses")
        if not isinstance(verses, list) or not 1 <= len(verses) <= item["total"]:
            raise ValueError(f"Invalid preview verse count: {key}")
        if any(not isinstance(v.get("number"), int) or not isinstance(v.get("text"), str) or not v["text"] for v in verses):
            raise ValueError(f"Invalid preview text: {key}")
        first = int(re.search(r":(\d+)", key).group(1)) if ":" in key else 1
        if covered_numbers(verses) != list(range(first, first + item["total"])):
            raise ValueError(f"Incomplete scripture preview range: {key}")
    if current != serialized(data):
        raise ValueError("scripture-previews-data.js is not canonically serialized")
    if not SEARCH_OUTPUT.exists():
        raise ValueError("scripture-search-data.js is missing")
    search_current = SEARCH_OUTPUT.read_text(encoding="utf-8")
    search_prefix = "window.EMMAUS_SCRIPTURE_SEARCH="
    if not search_current.startswith(search_prefix) or not search_current.endswith(";\n"):
        raise ValueError("scripture-search-data.js has unexpected format")
    search_data = json.loads(search_current[len(search_prefix):-2])
    if search_data.get("source") != SOURCE or set(search_data.get("passages", {})) != expected_keys:
        raise ValueError("Search source or reference coverage is out of date")
    for key, verses in search_data["passages"].items():
        preview = data["passages"][key]
        book_chapter = key.split(":")[0]
        combined_psalm_8 = book_chapter == "PSA 8" and preview["total"] >= 8
        expected_length = preview["total"] - (2 if combined_psalm_8 else 0)
        if not isinstance(verses, list) or sum(len(verse.get("coveredNumbers", [verse["number"]])) for verse in verses) != expected_length or verses != preview["verses"]:
            raise ValueError(f"Incomplete scripture search range: {key}")
        first = int(re.search(r":(\d+)", key).group(1)) if ":" in key else 1
        expected_numbers = [number for number in range(first, first + preview["total"])
                            if not (combined_psalm_8 and number in (6, 7))]
        if [number for verse in verses for number in verse.get("coveredNumbers", [verse.get("number")])] != expected_numbers or any(
            not isinstance(verse.get("text"), str) or not verse["text"] for verse in verses
        ):
            raise ValueError(f"Invalid scripture search verse: {key}")
    if search_current != serialized_search(search_data):
        raise ValueError("scripture-search-data.js is not canonically serialized")
    return current, search_current


def fetch_sources(source_dir):
    source_dir.mkdir(parents=True, exist_ok=True)
    for book in sorted({ref[0] for ref in references()}):
        revision, expected_sha = PAGES[book]
        url = f"https://zh.wikisource.org/w/index.php?oldid={revision}&action=raw"
        request = Request(url, headers={"User-Agent": "EmmausScripturePreview/1.0 (https://github.com/howhow777/emmaus-scripture-study)"})
        with urlopen(request, timeout=30) as response:
            raw = response.read()
        if hashlib.sha256(raw).hexdigest() != expected_sha:
            raise ValueError(f"Pinned source checksum differs for {book}")
        (source_dir / f"{book}.txt").write_bytes(raw)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR, help="local pinned Wikisource raw cache")
    parser.add_argument("--fetch", action="store_true", help="download pinned revisions into the local cache")
    parser.add_argument("--check", action="store_true", help="check data without network or writing")
    args = parser.parse_args()
    if args.check and args.fetch:
        parser.error("--check and --fetch cannot be used together")
    if args.fetch:
        fetch_sources(args.source_dir)
    if args.check:
        current, search_current = check_existing()
        if all((args.source_dir / f"{book}.txt").exists() for book in {ref[0] for ref in references()}):
            preview_data, search_data = build(args.source_dir)
            if current != serialized(preview_data) or search_current != serialized_search(search_data):
                parser.exit(1, "Scripture preview or search data differs from pinned source\n")
            print("Preview and full-range search data match all pinned source pages and current links")
        else:
            print("Preview and search coverage and format match; source cache absent, text comparison skipped")
    else:
        preview_data, search_data = build(args.source_dir)
        OUTPUT.write_text(serialized(preview_data), encoding="utf-8")
        SEARCH_OUTPUT.write_text(serialized_search(search_data), encoding="utf-8")
        print(f"Updated preview and search data ({len(references())} passages)")


if __name__ == "__main__":
    main()
