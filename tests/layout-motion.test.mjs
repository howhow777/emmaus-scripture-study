import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { visibleGraph } from '../graph-model.mjs';
import { linkDistance, linkStrength, makeSimulation, seedNode } from '../graph-layout.mjs';
import {
  MIN_ZOOM, MAX_ZOOM, STILL_SWAY, clampZoom, panTransform, pinchTransform,
  tapEligible, swayImpulse, springStep, displayX, displayY,
} from '../graph-motion.mjs';

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

function simulatedMedians() {
  const graph = visibleGraph(data, state);
  assert.equal(graph.entries.length, 186);
  const nodes = graph.nodeIds.map(id => seedNode({ id, kind: id.split(':')[0] }));
  const links = graph.links.map(link => ({ ...link }));
  const simulation = makeSimulation(nodes, links, entriesById);
  let randomState = 0x5eed1234;
  simulation.randomSource(() => ((randomState = (Math.imul(randomState, 1664525) + 1013904223) >>> 0) / 4294967296));
  simulation.stop().alpha(1).tick(350);
  const lengths = { A: [], B: [], C: [], D: [], topic: [] };
  for (const link of links) {
    const group = link.kind === 'topic' ? 'topic' : entriesById.get(link.entryId).ev;
    lengths[group].push(Math.hypot(link.source.x - link.target.x, link.source.y - link.target.y));
  }
  return Object.fromEntries(Object.entries(lengths).map(([key, values]) => [key, median(values)]));
}

test('the actual all-186 simulation has ordered median lengths with deterministic seeds', () => {
  const first = simulatedMedians();
  const second = simulatedMedians();
  for (const key of ['A', 'B', 'C', 'D', 'topic']) {
    assert.ok(Number.isFinite(first[key]));
    assert.ok(Math.abs(first[key] - second[key]) < 1e-7, `${key} layout drifted between identical runs`);
  }
  assert.ok(Math.max(first.A, first.B) < first.C, JSON.stringify(first));
  assert.ok(first.C < first.D && first.D < first.topic, JSON.stringify(first));
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
  const node = { x: 100, y: -80, swayX: 1.2, swayY: 1.2 };
  for (const k of [MIN_ZOOM, 1, MAX_ZOOM]) {
    const screenX = (displayX(node, sway, k) - node.x) * k;
    const screenY = (displayY(node, sway, k) - node.y) * k;
    assert.ok(Math.hypot(screenX, screenY) <= 5 + 1e-10);
  }
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
