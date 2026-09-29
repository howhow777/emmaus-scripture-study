import { forceSimulation, forceLink, forceManyBody, forceCollide, forceX, forceY } from 'd3-force';

export const TOPIC_ORDER = ['立約', '身分', '降生', '事工', '受苦', '贖罪', '復活', '榮耀', '萬邦', '終末'];

export function topicRingRadius(scope) {
  return scope === 'all' ? 280 : 200;
}

export function placeTopicRing(nodes, scope = null) {
  const entryCount = nodes.filter(node => node.kind === 'entry').length;
  const radius = topicRingRadius(scope || (entryCount > 49 ? 'all' : 'core'));
  for (const node of nodes) {
    if (node.kind !== 'topic') continue;
    const index = TOPIC_ORDER.indexOf(node.label || node.id.slice(6));
    if (index < 0) continue;
    const angle = -Math.PI / 2 + 2 * Math.PI * index / TOPIC_ORDER.length;
    node.fx = node.x = radius * Math.cos(angle);
    node.fy = node.y = radius * Math.sin(angle);
  }
  return radius;
}

function softOuterBoundary() {
  let nodes = [], limit = 160;
  function force(alpha) {
    for (const node of nodes) {
      if (node.kind === 'topic') continue;
      const distance = Math.hypot(node.x, node.y);
      if (distance <= limit) continue;
      const pull = (distance - limit) * .035 * alpha / distance;
      node.vx -= node.x * pull;
      node.vy -= node.y * pull;
    }
  }
  force.initialize = value => {
    nodes = value;
    const nonTopicCount = nodes.filter(node => node.kind !== 'topic').length;
    limit = Math.max(300, Math.min(660, 28 * Math.sqrt(nonTopicCount)));
  };
  return force;
}

function hashNumber(value) {
  let result = 2166136261;
  for (let i = 0; i < value.length; i++) result = Math.imul(result ^ value.charCodeAt(i), 16777619);
  return result >>> 0;
}

export function seedNode(node) {
  const baseX = node.kind === 'ot' ? -260 : node.kind === 'nt' ? 260 : 0;
  const rangeX = node.kind === 'topic' ? 420 : node.kind === 'entry' ? 260 : 170;
  node.x = baseX + ((hashNumber(node.id + 'x') / 4294967295) - .5) * rangeX;
  node.y = (node.kind === 'topic' ? -220 : 0) + ((hashNumber(node.id + 'y') / 4294967295) - .5) * 480;
  // Stable per-node differences make a dragged cluster flex instead of moving as one block.
  node.swayGain = .35 + .8 * hashNumber(node.id + 'swayGain') / 4294967295;
  node.swayTwist = -.25 + .5 * hashNumber(node.id + 'swayTwist') / 4294967295;
  return node;
}

export function linkDistance(link, entriesById) {
  if (link.kind === 'topic') return 150;
  const evidence = entriesById.get(link.entryId)?.ev;
  return evidence === 'C' ? 105 : evidence === 'D' ? 135 : 75;
}

export function linkStrength(link, entriesById) {
  if (link.kind === 'topic') return .025;
  const evidence = entriesById.get(link.entryId)?.ev;
  return evidence === 'C' ? .28 : evidence === 'D' ? .22 : .35;
}

export function makeSimulation(nodes, links, entriesById, scope = null) {
  placeTopicRing(nodes, scope);
  return forceSimulation(nodes)
    .force('link', forceLink(links).id(node => node.id)
      .distance(link => linkDistance(link, entriesById))
      .strength(link => linkStrength(link, entriesById)))
    .force('charge', forceManyBody().strength(node => node.kind === 'topic' ? -110 : node.kind === 'entry' ? -65 : -35).distanceMax(260))
    .force('collision', forceCollide().radius(node => node.kind === 'topic' ? 16 : node.kind === 'entry' ? 10 : 7).iterations(2))
    .force('x', forceX(node => node.kind === 'ot' ? -80 : node.kind === 'nt' ? 80 : 0).strength(.011))
    .force('y', forceY(0).strength(.011))
    .force('outerBoundary', softOuterBoundary());
}
