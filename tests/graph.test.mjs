import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { visibleGraph } from '../graph-model.mjs';

const read = path => readFileSync(new URL(path, import.meta.url), 'utf8');
const dataScript = read('../graph-data.js');
const prefix = 'window.EMMAUS_GRAPH_DATA=';
assert.ok(dataScript.startsWith(prefix) && dataScript.endsWith(';\n'));
const data = JSON.parse(dataScript.slice(prefix.length, -2));
const index = read('../index.html');

const base = {
  scope: 'all', testament: 'both', book: '', group: '', topic: '', evidence: '',
  pentateuch: false, speech: false, compare: false, search: '', topics: false,
};
const show = changes => visibleGraph(data, { ...base, ...changes });
const ids = graph => graph.entries.map(entry => entry.id);

test('generated data matches the 186 original cards and their linked passages', () => {
  assert.equal(data.version, 1);
  assert.equal(data.entries.length, 186);
  assert.equal(data.entries.filter(entry => entry.core).length, 49);
  assert.equal(new Set(data.entries.map(entry => entry.id)).size, 186);

  const cards = new Map([...index.matchAll(/<article class="entry" id="(E\d{3})"[\s\S]*?<\/article>/g)]
    .map(match => [match[1], match[0]]));
  assert.equal(cards.size, 186);
  assert.match(index, /href="graph\.html"[^>]*>探索互動經文圖譜/);
  assert.match(index, /link\.href='graph\.html#'\+id/);

  for (const entry of data.entries) {
    const card = cards.get(entry.id);
    assert.ok(card, `Missing original card ${entry.id}`);
    assert.ok(entry.ot.length && entry.nt.length, `${entry.id} needs both source and comparison passages`);
    for (const side of ['ot', 'nt']) {
      for (const passage of entry[side]) {
        assert.ok(card.includes(`href="${passage.href}"`), `${entry.id} ${passage.ref} differs from original link`);
        const url = new URL(passage.href);
        assert.equal(url.hostname, 'www.bible.com');
        assert.ok(url.pathname.startsWith(`/bible/46/${passage.ref.replace(' ', '.').replace(':', '.')}.`));
        const code = passage.ref.split(' ')[0];
        assert.equal(data.books[code]?.testament, side);
      }
    }
  }
});

test('citation edges represent only listed passages; topic edges remain distinct', () => {
  const graph = show({});
  const expectedLinks = data.entries.reduce((count, entry) => count + entry.ot.length + entry.nt.length, 0);
  assert.equal(graph.entries.length, 186);
  assert.equal(graph.links.length, expectedLinks);
  assert.equal(new Set(graph.nodeIds).size, graph.nodeIds.length);
  assert.ok(graph.links.every(link => link.kind === 'citation'));
  for (const link of graph.links) {
    const entry = data.entries.find(item => item.id === link.entryId);
    assert.equal(link.source, `entry:${entry.id}`);
    assert.equal(link.target, `${link.testament}:${link.ref}`);
    assert.ok(entry[link.testament].some(passage => passage.ref === link.ref));
  }

  const withTopics = show({ topics: true });
  const topicLinks = withTopics.links.filter(link => link.kind === 'topic');
  assert.equal(topicLinks.length, data.entries.reduce((count, entry) => count + entry.tags.length, 0));
  assert.ok(topicLinks.every(link => link.target.startsWith('topic:')));
});

test('a shared New Testament passage is one node with separate evidence edges', () => {
  const graph = show({});
  const target = 'nt:GAL 3:10-14';
  assert.equal(graph.nodeIds.filter(id => id === target).length, 1);
  assert.deepEqual(graph.links.filter(link => link.target === target).map(link => link.entryId).sort(), ['E042', 'E043']);
});

test('core, book, topic, and evidence filters combine without dropping linked passages', () => {
  const graph = show({ scope: 'core', book: 'ISA', topic: '受苦', evidence: 'A' });
  assert.deepEqual(ids(graph), ['E099', 'E113', 'E117']);
  assert.ok(graph.links.every(link => graph.entries.some(entry => entry.id === link.entryId)));
  assert.ok(graph.links.some(link => link.target === 'nt:LUK 22:37'));
  assert.deepEqual(ids(show({ scope: 'core', book: 'ISA', topic: '受苦', evidence: 'A', pentateuch: true })), []);
});

test('keyword search accepts spaced and unspaced Chinese scripture references', () => {
  assert.deepEqual(ids(show({ search: '詩篇22' })), ['E065']);
  assert.deepEqual(ids(show({ search: '詩篇 22' })), ['E065']);
  assert.deepEqual(ids(show({ search: '以賽亞書53' })), ['E117']);
});

test('testament scope changes passage nodes, not matching study entries', () => {
  const both = show({ scope: 'core' });
  const ot = show({ scope: 'core', testament: 'ot' });
  const nt = show({ scope: 'core', testament: 'nt' });
  assert.deepEqual(ids(ot), ids(both));
  assert.deepEqual(ids(nt), ids(both));
  assert.ok(ot.links.every(link => link.testament === 'ot' && link.target.startsWith('ot:')));
  assert.ok(nt.links.every(link => link.testament === 'nt' && link.target.startsWith('nt:')));
  assert.equal(ot.links.length + nt.links.length, both.links.length);
});

test('Pentateuch filter matches all five books and composes with New Testament display', () => {
  const codes = new Set(['GEN', 'EXO', 'LEV', 'NUM', 'DEU']);
  for (const code of codes) assert.equal(data.books[code].group, 'pentateuch');
  const pentateuch = show({ pentateuch: true });
  assert.equal(pentateuch.entries.length, 48);
  assert.ok(pentateuch.entries.every(entry => entry.ot.some(passage => codes.has(passage.ref.split(' ')[0]))));
  assert.deepEqual(ids(pentateuch), ids(show({ group: 'pentateuch' })));
  const nt = show({ pentateuch: true, testament: 'nt' });
  assert.deepEqual(ids(nt), ids(pentateuch));
  assert.ok(nt.links.length > 0 && nt.links.every(link => link.testament === 'nt'));
});

test('Jesus-spoken verses use the verified annotation, independent of legacy comparison flag', () => {
  const speech = show({ speech: true, testament: 'nt' });
  assert.equal(speech.entries.length, 65);
  assert.equal(speech.links.length, 87);
  assert.ok(speech.links.every(link => link.spoken));
  assert.ok(ids(speech).includes('E034'));
  assert.ok(!data.entries.find(entry => entry.id === 'E034').jesus);
  assert.ok(!ids(speech).includes('E001'));
  assert.ok(!ids(show({ compare: true })).includes('E034'));

  const servant = speech.links.filter(link => link.entryId === 'E117');
  assert.deepEqual(servant.map(link => link.ref), ['LUK 22:37']);
  assert.ok(data.speech.find(item => item.entryId === 'E117' && item.ntRef === 'LUK 22:37').spans.length);
  assert.deepEqual(data.speech.find(item => item.entryId === 'E037' && item.ntRef === 'JHN 3:14-17')
    .spans.map(span => span.ref), ['JHN 3:14-15']);
  assert.ok(!data.speech.some(item => item.spans.some(span => span.ref === 'REV 22:12' || span.ref === 'HEB 10:5-7')));
});

test('every spoken verse span stays inside its cited New Testament passage', () => {
  const range = ref => {
    const match = /^([0-9A-Z]+) (\d+):(\d+)(?:-(\d+))?$/.exec(ref);
    assert.ok(match, `Invalid verse reference ${ref}`);
    return { book: match[1], chapter: match[2], first: Number(match[3]), last: Number(match[4] ?? match[3]) };
  };
  for (const citation of data.speech) {
    const entry = data.entries.find(item => item.id === citation.entryId);
    assert.ok(entry?.nt.some(passage => passage.ref === citation.ntRef));
    const parent = range(citation.ntRef);
    assert.ok(citation.spans.length > 0);
    for (const span of citation.spans) {
      const child = range(span.ref);
      assert.equal(child.book, parent.book);
      assert.equal(child.chapter, parent.chapter);
      assert.ok(parent.first <= child.first && child.first <= child.last && child.last <= parent.last,
        `${citation.entryId}: ${span.ref} lies outside ${citation.ntRef}`);
    }
  }
});

test('a noncore deep-linked study remains available in all-entry mode', () => {
  const all = show({ search: 'E002' });
  assert.deepEqual(ids(all), ['E002']);
  assert.deepEqual(ids(show({ scope: 'core', search: 'E002' })), []);
  assert.ok(index.includes('id="E002"'));
  assert.ok(index.includes("link.href='graph.html#'+id"));
});
