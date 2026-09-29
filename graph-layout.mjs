import { forceSimulation, forceLink, forceManyBody, forceCollide, forceX, forceY } from 'd3-force';

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

export function makeSimulation(nodes, links, entriesById) {
  return forceSimulation(nodes)
    .force('link', forceLink(links).id(node => node.id)
      .distance(link => linkDistance(link, entriesById))
      .strength(link => linkStrength(link, entriesById)))
    .force('charge', forceManyBody().strength(node => node.kind === 'topic' ? -110 : node.kind === 'entry' ? -65 : -35).distanceMax(260))
    .force('collision', forceCollide().radius(node => node.kind === 'topic' ? 16 : node.kind === 'entry' ? 10 : 7).iterations(2))
    .force('x', forceX(node => node.kind === 'ot' ? -80 : node.kind === 'nt' ? 80 : 0).strength(.008))
    .force('y', forceY(node => node.kind === 'topic' ? -180 : 0).strength(.025));
}
