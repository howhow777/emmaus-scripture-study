import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { visibleGraph } from '../graph-model.mjs';
import { TOPIC_ORDER, linkDistance, linkStrength, makeSimulation, placeTopicRing, seedNode, topicRingRadius } from '../graph-layout.mjs';
import {
  MIN_ZOOM, MAX_ZOOM, STILL_SWAY, clampZoom, panTransform, pinchTransform,
  tapEligible, swayImpulse, springStep, displayX, displayY,
} from '../graph-motion.mjs';
import { selectionAfterTap, hashAfterSelection } from '../graph-selection.mjs';

const script = readFileSync(new URL('../graph-data.js', import.meta.url), 'utf8');
const data = JSON.parse(script.slice('window.EMMAUS_GRAPH_DATA='.length, -2));
const entriesById = new Map(data.entries.map(entry => [entry.id, entry]));
const state = {
  scope: 'all', testament: 'both', book: '', group: '', topic: '', evidence: '',
  pentateuch: false, speech: false, compare: false, search: '', topics: true,
};

const citation = entryId => ({ kind: 'citation', entryId });
const exampleId = evidence => data.entries.find(entry => entry.ev === evidence).id;

test('A and B share one layout target; C and D separate progressively', () => {
  const [a, b, c, d] = 'ABCD'.split('').map(ev => citation(exampleId(ev)));
  assert.equal(linkDistance(a, entriesById), linkDistance(b, entriesById));
  assert.equal(linkStrength(a, entriesById), linkStrength(b, entriesById));
  assert.ok(linkDistance(a, entriesById) < linkDistance(c, entriesById));
  assert.ok(linkDistance(c, entriesById) < linkDistance(d, entriesById));
  assert.ok(linkStrength(a, entriesById) > linkStrength(c, entriesById));
  assert.ok(linkStrength(c, entriesById) > linkStrength(d, entriesById));
});

test('theme classification has a longer, weaker target than every citation class', () => {
  const topic = { kind: 'topic', entryId: exampleId('D'), topic: '身分' };
  for (const evidence of 'ABCD') {
    const edge = citation(exampleId(evidence));
    assert.ok(linkDistance(topic, entriesById) > linkDistance(edge, entriesById));
    assert.ok(linkStrength(topic, entriesById) < linkStrength(edge, entriesById));
  }
});

function median(values) {
  const sorted = values.sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
}

function simulatedLayout(scope = 'all') {
  const graph = visibleGraph(data, { ...state, scope });
  const ids = new Set(graph.nodeIds);
  for (const topic of TOPIC_ORDER) ids.add(`topic:${topic}`);
  const nodes = [...ids].map(id => seedNode({ id, kind: id.split(':')[0] }));
  const links = graph.links.map(link => ({ ...link }));
  const simulation = makeSimulation(nodes, links, entriesById, scope);
  let randomState = 0x5eed1234;
  simulation.randomSource(() => ((randomState = (Math.imul(randomState, 1664525) + 1013904223) >>> 0) / 4294967296));
  simulation.stop().alpha(1).tick(350);
  const lengths = { A: [], B: [], C: [], D: [], topic: [] };
  for (const link of links) {
    const group = link.kind === 'topic' ? 'topic' : entriesById.get(link.entryId).ev;
    lengths[group].push(Math.hypot(link.source.x - link.target.x, link.source.y - link.target.y));
  }
  const medians = Object.fromEntries(Object.entries(lengths).map(([key, values]) => [key, values.length ? median(values) : null]));
  const inner = nodes.filter(node => node.kind !== 'topic');
  const xs = inner.map(node => node.x), ys = inner.map(node => node.y);
  const aspect = (Math.max(...xs) - Math.min(...xs)) / (Math.max(...ys) - Math.min(...ys));
  return { medians, aspect, nodes };
}

test('the actual all-186 simulation has ordered median lengths with deterministic seeds', () => {
  const first = simulatedLayout().medians;
  const second = simulatedLayout().medians;
  for (const key of ['A', 'B', 'C', 'D', 'topic']) {
    assert.ok(Number.isFinite(first[key]));
    assert.ok(Math.abs(first[key] - second[key]) < 1e-7, `${key} layout drifted between identical runs`);
  }
  assert.ok(Math.max(first.A, first.B) < first.C, JSON.stringify(first));
  assert.ok(first.C < first.D && first.D < first.topic, JSON.stringify(first));
});

test('the 49-core and all-186 scripture clouds settle near circles around inset topic rings', () => {
  for (const scope of ['core', 'all']) {
    const { aspect, nodes, medians } = simulatedLayout(scope);
    assert.ok(aspect >= .85 && aspect <= 1.15, `${scope} aspect: ${aspect}`);
    const radius = topicRingRadius(scope);
    const topics = nodes.filter(node => node.kind === 'topic');
    const scriptures = nodes.filter(node => node.kind !== 'topic');
    assert.equal(topics.length, 10);
    assert.ok(scriptures.filter(node => Math.hypot(node.x, node.y) > radius).length / scriptures.length > .6,
      `${scope} topic ring is not surrounded by enough scripture and entry nodes`);
    assert.ok(topics.every(topic => scriptures.filter(node => Math.hypot(node.x - topic.x, node.y - topic.y) < 150).length >= (scope === 'core' ? 25 : 50)),
      `${scope} has an isolated topic node`);
    assert.ok(medians.topic < (scope === 'core' ? 300 : 380), `${scope} topic links remain too long: ${medians.topic}`);
    assert.ok(Math.abs(medians.A - medians.B) < 15, `${scope} A/B lengths differ: ${JSON.stringify(medians)}`);
    assert.ok(Math.max(medians.A, medians.B) < medians.C, `${scope} A/B/C lengths: ${JSON.stringify(medians)}`);
    if (scope === 'all') assert.ok(medians.C < medians.D, JSON.stringify(medians));
  }
});

test('all ten topic positions stay fixed when a scope is filtered', () => {
  for (const scope of ['core', 'all']) {
    const topics = selectedTopic => {
      const graph = visibleGraph(data, { ...state, scope, topic: selectedTopic });
      const ids = new Set(graph.nodeIds);
      for (const topic of TOPIC_ORDER) ids.add(`topic:${topic}`);
      const nodes = [...ids].map(id => seedNode({ id, kind: id.split(':')[0] }));
      placeTopicRing(nodes, scope);
      return new Map(nodes.filter(node => node.kind === 'topic').map(node => [node.id, [node.fx, node.fy]]));
    };
    const unfiltered = topics('');
    const filtered = topics('受苦');
    assert.equal(unfiltered.size, 10);
    for (const [id, position] of unfiltered) assert.deepEqual(filtered.get(id), position);
  }
});

test('pan and pinch calculations follow finger positions and keep the pinched world point fixed', () => {
  assert.deepEqual(panTransform({ x: 20, y: -10, k: 1.4 }, { x: 100, y: 80 }, { x: 145, y: 50 }),
    { x: 65, y: -40, k: 1.4 });

  const start = { world: [40, -20], k: 1.2, distance: 100 };
  const first = { x: 60, y: 100 };
  const near = pinchTransform(start, first, { x: 185, y: 100 });
  const farther = pinchTransform(start, first, { x: 210, y: 100 });
  assert.equal(near.k, 1.5);
  assert.equal(farther.k, 1.8);
  for (const [transform, second] of [[near, { x: 185, y: 100 }], [farther, { x: 210, y: 100 }]]) {
    const midpoint = { x: (first.x + second.x) / 2, y: (first.y + second.y) / 2 };
    assert.ok(Math.abs((midpoint.x - transform.x) / transform.k - start.world[0]) < 1e-10);
    assert.ok(Math.abs((midpoint.y - transform.y) / transform.k - start.world[1]) < 1e-10);
  }
});

test('pinch scale stays bounded and multi-pointer gestures cannot become taps', () => {
  assert.equal(clampZoom(0), MIN_ZOOM);
  assert.equal(clampZoom(100), MAX_ZOOM);
  const start = { world: [10, 20], k: 1, distance: 100 };
  assert.equal(pinchTransform(start, { x: 0, y: 0 }, { x: 1, y: 0 }).k, MIN_ZOOM);
  assert.equal(pinchTransform(start, { x: 0, y: 0 }, { x: 1000, y: 0 }).k, MAX_ZOOM);
  assert.equal(tapEligible(false, false, false), true);
  assert.equal(tapEligible(true, false, false), false);
  assert.equal(tapEligible(false, true, false), false);
  assert.equal(tapEligible(false, false, true), false);
});

test('diagonal drag sway stays within 5 screen pixels at every zoom', () => {
  const sway = swayImpulse(STILL_SWAY, -1000, -1000);
  const nodes = visibleGraph(data, state).nodeIds.map(id => seedNode({ id, kind: id.split(':')[0] }));
  for (const node of nodes) {
    for (const k of [MIN_ZOOM, 1, MAX_ZOOM]) {
      const screenX = (displayX(node, sway, k) - node.x) * k;
      const screenY = (displayY(node, sway, k) - node.y) * k;
      assert.ok(Math.hypot(screenX, screenY) <= 5 + 1e-10);
    }
  }
});

test('dragged nodes flex visibly by different amounts without moving their layout coordinates', () => {
  const sway = swayImpulse(STILL_SWAY, -1000, 0);
  const nodes = data.entries.slice(0, 49).map(entry => seedNode({ id: `entry:${entry.id}`, kind: 'entry' }));
  const before = nodes.map(node => [node.x, node.y]);
  const offsets = nodes.map(node => ({ x: displayX(node, sway, 1) - node.x, y: displayY(node, sway, 1) - node.y }));
  const spread = Math.max(...offsets.map(offset => offset.x)) - Math.min(...offsets.map(offset => offset.x));
  assert.ok(spread > 2.5, `Expected visible relative flex; spread=${spread}`);
  assert.ok(offsets.some(offset => Math.abs(offset.y) > .5), 'Expected a subtle sideways offset');
  assert.deepEqual(nodes.map(node => [node.x, node.y]), before);
});

test('released sway makes one small overshoot and settles by about 700 ms', () => {
  let current = swayImpulse(STILL_SWAY, -1000, 0);
  assert.ok(current.x > 0);
  let lowest = 0;
  for (let frame = 0; frame < 42; frame++) {
    current = springStep(current, 1000 / 60);
    lowest = Math.min(lowest, current.x);
  }
  assert.ok(lowest < -.1 && lowest > -.6, `Expected a small sign-changing overshoot; min=${lowest}`);
  assert.deepEqual(current, STILL_SWAY);
  assert.deepEqual(springStep(current, 1000 / 60), STILL_SWAY);
});

test('tap selection toggles the same node, clears on blank, and replaces with another node', () => {
  assert.equal(selectionAfterTap(null, 'entry:E001'), 'entry:E001');
  assert.equal(selectionAfterTap('entry:E001', 'entry:E001'), null);
  assert.equal(selectionAfterTap('entry:E001', null), null);
  assert.equal(selectionAfterTap('entry:E001', 'ot:GEN 1:26-28'), 'ot:GEN 1:26-28');
});

test('selection hash tracks explicit choices without erasing a pending deep link', () => {
  assert.equal(hashAfterSelection('', null, 'entry:E001'), '#E001');
  assert.equal(hashAfterSelection('#E001', 'entry:E001', null), '');
  assert.equal(hashAfterSelection('#E001', 'entry:E001', 'nt:LUK 22:37'), '');
  assert.equal(hashAfterSelection('#E001', 'entry:E001', 'entry:E002'), '#E002');
  assert.equal(hashAfterSelection('#E002', 'entry:E001', null), '#E002');
});
