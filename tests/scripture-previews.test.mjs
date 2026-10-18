import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';

const root = new URL('../', import.meta.url);
const file = name => readFileSync(new URL(name, root), 'utf8');
const context = { window: {} };
runInNewContext(file('scripture-previews-data.js'), context);
runInNewContext(file('scripture-search-data.js'), context);
runInNewContext(file('graph-data.js'), context);
const { source, passages } = context.window.EMMAUS_SCRIPTURE_PREVIEWS;
const fullSearch = context.window.EMMAUS_SCRIPTURE_SEARCH;
const graph = context.window.EMMAUS_GRAPH_DATA;

function referenceFromHref(href) {
  const encoded = href.split('/bible/46/')[1];
  const match = /^([0-9A-Z]+)\.(\d+)(?:\.(\d+)(?:-(\d+))?)?\.CUNP-神$/.exec(decodeURIComponent(encoded));
  assert.ok(match, `Unexpected Bible.com destination: ${href}`);
  return `${match[1]} ${match[2]}${match[3] ? `:${match[3]}${match[4] ? `-${match[4]}` : ''}` : ''}`;
}

test('every Bible.com scripture destination has a distinct preview', () => {
  const html = file('index.html');
  const refs = new Set();
  for (const text of [html, file('graph-data.js'), file('coverage.html')]) {
    for (const match of text.matchAll(/https:\/\/www\.bible\.com\/bible\/46\/[0-9A-Z.%-]+/g)) {
      refs.add(referenceFromHref(match[0]));
    }
  }
  assert.ok(refs.size >= 590);
  assert.deepEqual(new Set(Object.keys(passages)), refs);
  for (const entry of graph.entries) {
    for (const side of ['ot', 'nt']) {
      for (const passage of entry[side]) assert.ok(passages[passage.ref], passage.ref);
    }
  }
  for (const speech of graph.speech) {
    for (const span of speech.spans) assert.ok(passages[span.ref], span.ref);
  }
});

test('previews state their source and show every cited verse', () => {
  assert.match(source.label, /維基文庫 1919 用字版.*神版/);
  assert.match(source.url, /^https:\/\/zh\.wikisource\.org\//);
  assert.match(source.note, /CUNP-神/);
  for (const [ref, item] of Object.entries(passages)) {
    assert.ok(item.label, ref);
    assert.ok(Number.isInteger(item.total) && item.total > 0, ref);
    assert.equal(item.verses.length, fullSearch.passages[ref].length, ref);
    const match = /^[0-9A-Z]+ \d+(?::(\d+)(?:-\d+)?)?$/.exec(ref);
    assert.ok(match, ref);
    const first = Number(match[1] || 1);
    item.verses.forEach((verse, index) => {
      assert.equal(verse.number, fullSearch.passages[ref][index].number, ref);
      assert.ok(verse.text.length > 0, ref);
      assert.doesNotMatch(verse.text, /\{\{|\[\[|<[^>]+>/, ref);
    });
  }
});

test('preview and full search contain identical complete cited passages', () => {
  assert.equal(JSON.stringify(fullSearch.source), JSON.stringify(source));
  assert.deepEqual(new Set(Object.keys(fullSearch.passages)), new Set(Object.keys(passages)));
  for (const [ref, preview] of Object.entries(passages)) {
    const verses = fullSearch.passages[ref];
    assert.equal(JSON.stringify(verses), JSON.stringify(preview.verses), ref);
    assert.equal(verses.reduce((n,v)=>n+(v.coveredNumbers?.length || 1),0), preview.total - (ref === 'PSA 8:1-9' ? 2 : 0), ref);
  }
  assert.equal(fullSearch.passages['LUK 24'].at(-1).number, 53);
  assert.match(fullSearch.passages['GEN 22:1-14'][5].text, /燔祭的柴放在/);
  assert.equal(fullSearch.passages['PSA 8:1-9'].find(verse => verse.number === 8).numberLabel, '6–8');
});

test('chapter and source transcription edge cases remain accurate', () => {
  assert.equal(passages['LUK 24'].total, 53);
  assert.deepEqual(Array.from(passages['LUK 24'].verses, v => v.number), Array.from({length:53}, (_,i)=>i+1));
  assert.match(passages['LUK 24:44-47'].verses[0].text, /摩西的律法/);
  const isaiah = passages['ISA 4:2-6'].verses;
  assert.match(isaiah[1].text, /賸在錫安/);
  assert.match(isaiah[2].text, /公義的靈/);
  assert.doesNotMatch(isaiah[1].text, /公義的靈/);
  assert.match(passages['EZK 47:1-12'].verses[1].text, /又領我從外邊轉到朝東的外門/);
});

test('merged numbering and variant-only source notes are explicit instead of empty verses',()=>{
 const merged=fullSearch.passages['LUK 2:34-35'];
 assert.deepEqual(Array.from(merged[0].coveredNumbers),[34,35]);
 assert.equal(merged[0].numberLabel,'34–35');assert.match(merged[0].text,/西面/);
 assert.match(fullSearch.passages['MRK 15:24-34'].find(v=>v.number===28).text,/本來源異文註/);
});

function numbers(verses) {
  return verses.flatMap(verse => verse.coveredNumbers || (verse.numberLabel?.includes('–')
    ? Array.from({length:Number(verse.numberLabel.split('–')[1])-Number(verse.numberLabel.split('–')[0])+1}, (_,i)=>Number(verse.numberLabel.split('–')[0])+i)
    : [verse.number]));
}
test('every preview covers its complete citation with no omissions or duplicates', () => {
  assert.equal(Object.keys(passages).length, 901);
  for (const [ref,item] of Object.entries(passages)) {
    const first=Number(ref.match(/:(\d+)/)?.[1] || 1);
    assert.deepEqual(Array.from(numbers(item.verses)),Array.from({length:item.total},(_,i)=>first+i),ref);
  }
  for (const [ref,total,last] of [['LUK 1:26-38',13,38],['ISA 7:10-17',8,17],['LUK 24',53,53]]) {
    assert.equal(passages[ref].total,total,ref);
    assert.equal(passages[ref].verses.at(-1).number,last,ref);
  }
  assert.equal(numbers(passages['PSA 8:1-9'].verses).length,9);
  assert.match(passages['MRK 15:24-34'].verses.find(v=>v.number===28).text,/本來源異文註/);
});
