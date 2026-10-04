import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';

const root = new URL('../', import.meta.url);
const file = name => readFileSync(new URL(name, root), 'utf8');
const context = { window: {} };
runInNewContext(file('scripture-previews-data.js'), context);
runInNewContext(file('graph-data.js'), context);
const { source, passages } = context.window.EMMAUS_SCRIPTURE_PREVIEWS;
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
  for (const text of [html, file('graph-data.js')]) {
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

test('previews state their source and show up to four numbered verses', () => {
  assert.match(source.label, /維基文庫 1919 用字版.*神版/);
  assert.match(source.url, /^https:\/\/zh\.wikisource\.org\//);
  assert.match(source.note, /CUNP-神/);
  for (const [ref, item] of Object.entries(passages)) {
    assert.ok(item.label, ref);
    assert.ok(Number.isInteger(item.total) && item.total > 0, ref);
    assert.equal(item.verses.length, Math.min(item.total, 4), ref);
    const match = /^[0-9A-Z]+ \d+(?::(\d+)(?:-\d+)?)?$/.exec(ref);
    assert.ok(match, ref);
    const first = Number(match[1] || 1);
    item.verses.forEach((verse, index) => {
      assert.equal(verse.number, first + index, ref);
      assert.ok(verse.text.length > 0, ref);
      assert.doesNotMatch(verse.text, /\{\{|\[\[|<[^>]+>/, ref);
    });
  }
});

test('chapter and source transcription edge cases remain accurate', () => {
  assert.equal(passages['LUK 24'].total, 53);
  assert.deepEqual(Array.from(passages['LUK 24'].verses, v => v.number), [1, 2, 3, 4]);
  assert.match(passages['LUK 24:44-47'].verses[0].text, /摩西的律法/);
  const isaiah = passages['ISA 4:2-6'].verses;
  assert.match(isaiah[1].text, /賸在錫安/);
  assert.match(isaiah[2].text, /公義的靈/);
  assert.doesNotMatch(isaiah[1].text, /公義的靈/);
  assert.match(passages['EZK 47:1-12'].verses[1].text, /又領我從外邊轉到朝東的外門/);
});
