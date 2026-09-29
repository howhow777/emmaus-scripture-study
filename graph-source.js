import { zoom, zoomIdentity } from 'd3-zoom';
import { select } from 'd3-selection';
import { entryMatches, visibleGraph } from './graph-model.mjs';
import { seedNode, makeSimulation } from './graph-layout.mjs';
import { MIN_ZOOM, MAX_ZOOM, clampZoom, panTransform, pinchTransform, tapEligible, STILL_SWAY, swayImpulse, springStep, displayX, displayY } from './graph-motion.mjs';

const data = window.EMMAUS_GRAPH_DATA;
const $ = id => document.getElementById(id);
const controls = {
  search: $('graphSearch'), scope: $('scopeFilter'), testament: $('testamentFilter'),
  book: $('bookFilter'), group: $('groupFilter'), topic: $('topicFilter'),
  evidence: $('evidenceFilter'), pentateuch: $('pentateuchOnly'),
  speech: $('jesusSpeechOnly'), compare: $('jesusCompareOnly'), topics: $('showTopics')
};
const canvas = $('graphCanvas');
const ctx = canvas.getContext('2d', { alpha: true });
const stage = canvas.parentElement;
const canvasSelection = select(canvas);
const colors = { entry: '#e8bf79', ot: '#7ed5b0', nt: '#87c5e8', topic: '#c7a4df' };
const topicNames = ['身分', '降生', '事工', '受苦', '贖罪', '復活', '榮耀', '立約', '萬邦', '終末'];
const groupNames = {
  pentateuch: '摩西五經', history: '歷史書', poetry: '詩歌智慧書',
  'major-prophets': '大先知書', 'minor-prophets': '小先知書',
  gospels: '福音書', acts: '使徒行傳', letters: '書信', revelation: '啟示錄', other: '其他書卷'
};
const bookOrder = 'GEN EXO LEV NUM DEU JOS JDG RUT 1SA 2SA 1KI 2KI 1CH 2CH EZR NEH EST JOB PSA PRO ECC SNG ISA JER LAM EZK DAN HOS JOL AMO OBA JON MIC NAM HAB ZEP HAG ZEC MAL MAT MRK LUK JHN ACT ROM 1CO 2CO GAL EPH PHP COL 1TH 2TH 1TI 2TI TIT PHM HEB JAS 1PE 2PE 1JN 2JN 3JN JUD REV'.split(' ');
const bookRank = new Map(bookOrder.map((code, i) => [code, i]));
const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

if (!data || data.version !== 1 || !Array.isArray(data.entries) || !ctx) {
  $('graphStatus').textContent = '圖譜資料未能載入。請重新開啟網站包，或返回研究頁。';
  throw new Error('Graph data or Canvas unavailable');
}

const entries = data.entries;
const entriesById = new Map(entries.map(entry => [entry.id, entry]));
const speechByEntry = new Map();
for (const item of data.speech || []) {
  if (!speechByEntry.has(item.entryId)) speechByEntry.set(item.entryId, new Map());
  speechByEntry.get(item.entryId).set(item.ntRef, item.spans);
}
const allNodes = new Map();
const passageNodes = new Map();
const topicNodes = new Map();
const entryNodes = new Map();

function addNode(node) {
  allNodes.set(node.id, seedNode(node));
  return node;
}
for (const topic of topicNames) {
  topicNodes.set(topic, addNode({ id: `topic:${topic}`, kind: 'topic', label: topic, related: [] }));
}
for (const entry of entries) {
  const entryNode = addNode({ id: `entry:${entry.id}`, kind: 'entry', label: `${entry.id} · ${entry.title}`, entry });
  entryNodes.set(entry.id, entryNode);
  for (const kind of ['ot', 'nt']) {
    for (const passage of entry[kind]) {
      const id = `${kind}:${passage.ref}`;
      let node = passageNodes.get(id);
      if (!node) {
        node = addNode({ id, kind, label: passage.label, ref: passage.ref, href: passage.href, related: [] });
        passageNodes.set(id, node);
      }
      if (!node.related.includes(entry.id)) node.related.push(entry.id);
    }
  }
  for (const tag of entry.tags) {
    const topicNode = topicNodes.get(tag);
    if (!topicNode) continue;
    topicNode.related.push(entry.id);
  }
}

for (const topic of topicNames) {
  const option = document.createElement('option'); option.value = topic; option.textContent = topic; controls.topic.append(option);
}
const usedBooks = new Set();
for (const entry of entries) for (const passage of [...entry.ot, ...entry.nt]) usedBooks.add(passage.ref.split(' ')[0]);
for (const code of [...usedBooks].sort((a, b) => (bookRank.get(a) ?? 999) - (bookRank.get(b) ?? 999))) {
  const book = data.books[code]; if (!book) continue;
  const option = document.createElement('option'); option.value = code; option.textContent = book.name; controls.book.append(option);
}
for (const group of Object.keys(groupNames)) {
  if (!Object.values(data.books).some(book => book.group === group)) continue;
  const option = document.createElement('option'); option.value = group; option.textContent = groupNames[group]; controls.group.append(option);
}

let visibleEntries = [];
let visibleNodes = [];
let visibleLinks = [];
let regularLinks = [], spokenLinks = [], topicLinks = [], selectedLinks = [];
let visibleNodeIds = new Set();
let selectedId = null;
let hoveredId = null;
let transform = zoomIdentity;
let width = 1, height = 1, dpr = 1, drawPending = false;
let userHasMovedView = false;
let wheelGesture = false;
let layoutSettled = true;
let sway = STILL_SWAY, swayLastFrame = null;
const pointers = new Map();
let pointerStart = null, pointerBaseTransform = null, pointerNode = null, pointerMoved = false, hadMultiplePointers = false, pinchStart = null;
let gestureStartedAt = null, lastSampleAt = null, sampleFrameId = null, frameIntervals = [];

const simulation = makeSimulation([], [], entriesById)
  .on('tick', () => { if (!pointers.size && !wheelGesture) scheduleDraw(); })
  .on('end', () => { layoutSettled = true; });

function maybeResumeLayout() {
  if (!reducedMotion && !layoutSettled && !pointers.size && !wheelGesture && sway === STILL_SWAY) simulation.restart();
}

const zoomBehavior = zoom()
  .scaleExtent([MIN_ZOOM, MAX_ZOOM])
  .filter(event => event.type === 'wheel')
  .on('start', event => { if (event.sourceEvent?.type === 'wheel') { wheelGesture = true; simulation.stop(); } })
  .on('zoom', event => { transform = event.transform; if (event.sourceEvent?.type === 'wheel') userHasMovedView = true; scheduleDraw(); })
  .on('end', event => { if (event.sourceEvent?.type === 'wheel') { wheelGesture = false; maybeResumeLayout(); scheduleDraw(); } });
canvasSelection.call(zoomBehavior);
canvasSelection.on('dblclick.zoom', null);

function readState() {
  return {
    search: controls.search.value.trim().toLocaleLowerCase(), scope: controls.scope.value,
    testament: controls.testament.value, book: controls.book.value, group: controls.group.value,
    topic: controls.topic.value, evidence: controls.evidence.value,
    pentateuch: controls.pentateuch.checked, speech: controls.speech.checked,
    compare: controls.compare.checked, topics: controls.topics.checked
  };
}
function matchesEntry(entry, state) {
  return entryMatches(entry, state, data.books, new Set(speechByEntry.keys()));
}
function buildVisible() {
  const state = readState();
  const result = visibleGraph(data, state);
  visibleEntries = result.entries;
  visibleLinks = result.links;
  regularLinks = visibleLinks.filter(link => link.kind === 'citation' && !link.spoken);
  spokenLinks = visibleLinks.filter(link => link.kind === 'citation' && link.spoken);
  topicLinks = visibleLinks.filter(link => link.kind === 'topic');
  visibleNodeIds = new Set(result.nodeIds);
  visibleNodes = [...visibleNodeIds].map(id => allNodes.get(id)).filter(Boolean);
  if (selectedId && !visibleNodeIds.has(selectedId)) clearSelection();
  updateSelectedLinks();
  $('graphStatus').textContent = `${visibleEntries.length} 組研究 · ${visibleNodes.filter(node => node.kind === 'ot').length} 處舊約 · ${visibleNodes.filter(node => node.kind === 'nt').length} 處新約`;
  $('resultCount').textContent = `${visibleEntries.length} 組`;
  renderResultList();
  simulation.stop();
  simulation.nodes(visibleNodes);
  simulation.force('link').links(visibleLinks.map(link => ({ ...link })));
  sway = STILL_SWAY; swayLastFrame = null;
  if (reducedMotion) {
    simulation.alpha(1);
    simulation.tick(Math.min(90, Math.max(35, Math.round(18000 / Math.max(visibleNodes.length, 1)))));
    simulation.stop();
    layoutSettled = true;
  } else {
    layoutSettled = false;
    simulation.alpha(.72);
    simulation.tick(60); // Establish near-final bounds before the first fit, without animating clipped edges.
    maybeResumeLayout();
  }
  fitGraph();
  scheduleDraw();
}

function renderResultList() {
  const target = $('resultList');
  target.replaceChildren();
  if (!visibleNodes.length) {
    const p = document.createElement('p'); p.textContent = '沒有符合條件的節點，請放寬篩選。'; target.append(p); return;
  }
  const groups = [
    ['entry', '研究條目', visibleNodes.filter(node => node.kind === 'entry').sort((a, b) => a.entry.id.localeCompare(b.entry.id))],
    ['ot', '舊約經文', visibleNodes.filter(node => node.kind === 'ot').sort((a, b) => a.label.localeCompare(b.label, 'zh-Hant'))],
    ['nt', '新約經文', visibleNodes.filter(node => node.kind === 'nt').sort((a, b) => a.label.localeCompare(b.label, 'zh-Hant'))],
    ['topic', '共同主題', visibleNodes.filter(node => node.kind === 'topic').sort((a, b) => topicNames.indexOf(a.label) - topicNames.indexOf(b.label))]
  ];
  const fragment = document.createDocumentFragment();
  for (const [kind, title, nodes] of groups) {
    if (!nodes.length) continue;
    const section = document.createElement('section'); section.className = 'result-group';
    const h = document.createElement('h3'); h.textContent = `${title}（${nodes.length}）`; section.append(h);
    const list = document.createElement('ul');
    for (const node of nodes) {
      const li = document.createElement('li'); const button = document.createElement('button');
      button.type = 'button'; button.textContent = node.label; button.dataset.nodeId = node.id;
      button.setAttribute('aria-label', `選取${title}：${node.label}`);
      if (node.id === selectedId) button.setAttribute('aria-current', 'true');
      li.append(button); list.append(li);
    }
    section.dataset.kind = kind; section.append(list); fragment.append(section);
  }
  target.append(fragment);
}

function safeLink(href, label, external = false, className = '') {
  const a = document.createElement('a'); a.href = href; a.textContent = label;
  if (className) a.className = className;
  if (external) { a.target = '_blank'; a.rel = 'noopener noreferrer'; }
  return a;
}
function element(tag, text, className) {
  const item = document.createElement(tag); item.textContent = text;
  if (className) item.className = className;
  return item;
}
function appendSection(parent, title, items) {
  const section = document.createElement('section'); section.className = 'detail-section';
  section.append(element('h3', title));
  const list = document.createElement('ul');
  for (const item of items) list.append(item);
  section.append(list); parent.append(section);
}
function passageListItem(passage, spans = []) {
  const li = document.createElement('li');
  li.append(safeLink(passage.href, `${passage.label} ↗`, true));
  if (spans.length) {
    li.append(element('small', '含已核對的耶穌親口經節：'));
    for (const span of spans) li.append(safeLink(span.href, `${span.label} ↗`, true));
  }
  return li;
}
function entryListItem(entry) {
  const li = document.createElement('li');
  li.append(safeLink(`index.html#${entry.id}`, `${entry.id} · ${entry.title} ↗`));
  return li;
}
function renderDetails(node) {
  const target = $('detailsContent'); target.replaceChildren();
  if (!node) {
    const title = element('h2', '從一個點開始'); title.id = 'detailsTitle'; target.append(title);
    target.append(element('p', '點選圖上的研究、經文或主題，或從篩選結果清單選取，就能在這裡閱讀與開啟原研究及經文連結。'));
    return;
  }
  const title = element('h2', node.label); title.id = 'detailsTitle'; target.append(title);
  if (node.kind === 'entry') {
    const entry = node.entry;
    target.append(element('span', `證據 ${entry.ev}`, 'detail-badge'));
    if (entry.core) target.append(element('span', '主線優先', 'detail-badge'));
    if (entry.jesus) target.append(element('span', '原研究：耶穌親引／比較', 'detail-badge'));
    if (speechByEntry.has(entry.id)) target.append(element('span', '有逐節核對的耶穌發言', 'detail-badge'));
    target.append(element('p', `主題：${entry.tags.join('、')}。圖上的實線只連接本條目列出的經文。完整解說與解釋界線請見原研究。`));
    target.append(safeLink(`index.html#${entry.id}`, '閱讀原研究與解釋界線 ↗', false, 'detail-primary'));
    appendSection(target, `舊約段落（${entry.ot.length}）`, entry.ot.map(passage => passageListItem(passage)));
    appendSection(target, `新約段落（${entry.nt.length}）`, entry.nt.map(passage => passageListItem(passage, speechByEntry.get(entry.id)?.get(passage.ref) || [])));
    if (speechByEntry.has(entry.id)) target.append(element('p', '「耶穌親口說的」按可確認的發言經節另行標註；整段新約敘事不能一概算作耶穌原話。', 'detail-note'));
  } else if (node.kind === 'ot' || node.kind === 'nt') {
    target.append(element('span', node.kind === 'ot' ? '舊約經文' : '新約經文', 'detail-badge'));
    target.append(element('p', `全站共有 ${node.related.length} 組研究列出這處經文。下列連結可回到原研究的解說及界線。`));
    const spans = new Map();
    if (node.kind === 'nt') for (const id of node.related) for (const span of speechByEntry.get(id)?.get(node.ref) || []) spans.set(span.ref, span);
    if (spans.size) target.append(element('p', '此節點是原研究引用的完整段落；確切屬於耶穌發言的經節另列於下方。完整段落也可能含旁白或語者有爭議的經節。', 'detail-note'));
    target.append(safeLink(node.href, '開啟經文原頁 ↗', true, 'detail-primary'));
    appendSection(target, '全站相關研究條目', node.related.map(id => entryListItem(entriesById.get(id))));
    if (spans.size) appendSection(target, '已核對的耶穌親口經節', [...spans.values()].map(span => passageListItem(span)));
  } else {
    target.append(element('span', '共同研究主題', 'detail-badge'));
    target.append(element('p', '虛線只表示這些條目共用分類，不代表經文之間彼此引用或應驗。'));
    target.append(safeLink(`index.html?topic=${encodeURIComponent(node.label)}#catalog`, `在原研究查看「${node.label}」 ↗`, false, 'detail-primary'));
    appendSection(target, `全站相關研究條目（${node.related.length}）`, node.related.map(id => entryListItem(entriesById.get(id))));
  }
}
function clearSelection() {
  selectedId = null; renderDetails(null); $('detailsJump').hidden = true;
  updateSelectedLinks();
  $('resultList').querySelector('[aria-current="true"]')?.removeAttribute('aria-current');
  scheduleDraw();
}
function selectNode(node, focus = false, updateHash = true) {
  if (!node) return;
  selectedId = node.id;
  updateSelectedLinks();
  renderDetails(node);
  $('resultList').querySelector('[aria-current="true"]')?.removeAttribute('aria-current');
  const button = [...$('resultList').querySelectorAll('button[data-node-id]')].find(item => item.dataset.nodeId === node.id);
  button?.setAttribute('aria-current', 'true');
  if (focus) centerNode(node);
  if (node.kind === 'entry' && updateHash && location.hash !== `#${node.entry.id}`) history.replaceState(null, '', `#${node.entry.id}`);
  $('detailsJump').hidden = false;
  scheduleDraw();
}
function updateSelectedLinks() {
  selectedLinks = selectedId ? visibleLinks.filter(link => link.source === selectedId || link.target === selectedId) : [];
}
function centerNode(node) {
  userHasMovedView = true;
  const k = Math.max(transform.k, .8);
  canvasSelection.call(zoomBehavior.transform, zoomIdentity.translate(width / 2 - node.x * k, height / 2 - node.y * k).scale(k));
}
function fitGraph() {
  if (!visibleNodes.length) {
    canvasSelection.call(zoomBehavior.transform, zoomIdentity); return;
  }
  const xs = visibleNodes.map(node => node.x), ys = visibleNodes.map(node => node.y);
  const minX = Math.min(...xs) - 46, maxX = Math.max(...xs) + 46;
  const minY = Math.min(...ys) - 66, maxY = Math.max(...ys) + 85;
  const safety = layoutSettled ? 1 : .9;
  const k = Math.max(MIN_ZOOM, Math.min(2.2, (width - 48) / (maxX - minX), (height - 158) / (maxY - minY)) * safety);
  const midX = (minX + maxX) / 2, midY = (minY + maxY) / 2;
  canvasSelection.call(zoomBehavior.transform, zoomIdentity.translate(width / 2 - midX * k, height / 2 - midY * k).scale(k));
  userHasMovedView = false;
}
function resizeCanvas() {
  const rect = canvas.getBoundingClientRect();
  width = Math.max(1, rect.width); height = Math.max(1, rect.height);
  dpr = Math.min(2, window.devicePixelRatio || 1);
  canvas.width = Math.round(width * dpr); canvas.height = Math.round(height * dpr);
  if (!userHasMovedView) fitGraph();
  scheduleDraw();
}
function scheduleDraw() {
  if (drawPending) return;
  drawPending = true;
  requestAnimationFrame(time => { drawPending = false; draw(time); });
}
function endpoint(link, side) { return typeof link[side] === 'string' ? allNodes.get(link[side]) : link[side]; }
function drawLinks(links, color, lineWidth, dashed = false) {
  if (!links.length) return;
  ctx.beginPath(); ctx.strokeStyle = color; ctx.lineWidth = lineWidth / transform.k;
  ctx.setLineDash(dashed ? [4 / transform.k, 5 / transform.k] : []);
  for (const link of links) {
    const source = endpoint(link, 'source'), target = endpoint(link, 'target');
    const x1 = transform.applyX(source.drawX), y1 = transform.applyY(source.drawY);
    const x2 = transform.applyX(target.drawX), y2 = transform.applyY(target.drawY);
    if (Math.max(x1, x2) < -30 || Math.min(x1, x2) > width + 30 || Math.max(y1, y2) < -30 || Math.min(y1, y2) > height + 30) continue;
    ctx.moveTo(source.drawX, source.drawY); ctx.lineTo(target.drawX, target.drawY);
  }
  ctx.stroke(); ctx.setLineDash([]);
}
function draw(time) {
  const hadSway = sway !== STILL_SWAY;
  const pinching = pointers.size >= 2;
  if (hadSway && !pinching) {
    sway = springStep(sway, swayLastFrame === null ? 0 : time - swayLastFrame);
    swayLastFrame = time;
  } else if (pinching) swayLastFrame = null;
  for (const node of visibleNodes) {
    node.drawX = displayX(node, sway, transform.k);
    node.drawY = displayY(node, sway, transform.k);
  }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, width, height);
  ctx.translate(transform.x, transform.y); ctx.scale(transform.k, transform.k);
  drawLinks(regularLinks, '#7da48e55', .75);
  drawLinks(spokenLinks, '#eac98288', 1.15);
  drawLinks(topicLinks, '#b295cc55', .8, true);
  drawLinks(selectedLinks, '#f6d188', 1.7);
  const connected = new Set();
  for (const link of selectedLinks) { connected.add(endpoint(link, 'source').id); connected.add(endpoint(link, 'target').id); }
  for (const node of visibleNodes) {
    const screenX = transform.applyX(node.drawX), screenY = transform.applyY(node.drawY);
    if (screenX < -30 || screenX > width + 30 || screenY < -30 || screenY > height + 30) continue;
    const selected = node.id === selectedId, hovered = node.id === hoveredId;
    const radius = Math.max(node.kind === 'topic' ? 6 : node.kind === 'entry' ? 4.8 : 3.6, 2.1 / transform.k);
    ctx.globalAlpha = selectedId && !selected && !connected.has(node.id) ? .33 : 1;
    if (selected || hovered) {
      ctx.beginPath(); ctx.arc(node.drawX, node.drawY, radius + 7 / transform.k, 0, Math.PI * 2);
      ctx.fillStyle = selected ? '#f3cf8b38' : '#e8f1e138'; ctx.fill();
    }
    ctx.beginPath(); ctx.arc(node.drawX, node.drawY, radius, 0, Math.PI * 2);
    ctx.fillStyle = colors[node.kind]; ctx.fill();
    if (node.kind === 'entry' || node.kind === 'topic') {
      ctx.strokeStyle = selected ? '#fff3ce' : '#d8e8d277'; ctx.lineWidth = 1 / transform.k; ctx.stroke();
    }
  }
  ctx.globalAlpha = 1;
  const gesture = pointers.size > 0 || wheelGesture || sway !== STILL_SWAY;
  const labelNodes = visibleNodes.filter(node => node.id === selectedId || node.id === hoveredId ||
    (!gesture && (node.kind === 'topic' || (transform.k > 1.45 && node.kind === 'entry') || (transform.k > 2.4 && node.kind !== 'entry'))))
    .filter(node => { const x = transform.applyX(node.drawX), y = transform.applyY(node.drawY); return x > -120 && x < width + 120 && y > -40 && y < height + 40; });
  ctx.font = `${11 / transform.k}px -apple-system,BlinkMacSystemFont,"PingFang TC",sans-serif`;
  ctx.textBaseline = 'middle';
  for (const node of labelNodes) {
    const text = node.label.length > 27 ? node.label.slice(0, 27) + '…' : node.label;
    ctx.shadowColor = '#06160e'; ctx.shadowBlur = 5 / transform.k;
    ctx.fillStyle = node.id === selectedId ? '#fff5d7' : '#e0eee1';
    ctx.fillText(text, node.drawX + 10 / transform.k, node.drawY - 7 / transform.k);
  }
  ctx.shadowBlur = 0;
  if (sway !== STILL_SWAY && !pinching) scheduleDraw();
  else if (hadSway) { swayLastFrame = null; maybeResumeLayout(); }
}

function localPoint(event) {
  const rect = canvas.getBoundingClientRect(); return { x: event.clientX - rect.left, y: event.clientY - rect.top };
}
function hitNode(point) {
  let found = null, best = Infinity;
  for (const node of visibleNodes) {
    const sx = transform.applyX(displayX(node, sway, transform.k));
    const sy = transform.applyY(displayY(node, sway, transform.k));
    const distance = Math.hypot(point.x - sx, point.y - sy);
    const radius = node.kind === 'topic' ? 17 : node.kind === 'entry' ? 16 : 13;
    if (distance <= radius && distance < best) { found = node; best = distance; }
  }
  return found;
}
function applyTransform(x, y, k) {
  canvasSelection.call(zoomBehavior.transform, zoomIdentity.translate(x, y).scale(clampZoom(k)));
}
function sampleGestureFrame(time) {
  if (gestureStartedAt === null) return;
  if (lastSampleAt !== null && frameIntervals.length < 3600) frameIntervals.push(time - lastSampleAt);
  lastSampleAt = time;
  sampleFrameId = requestAnimationFrame(sampleGestureFrame);
}
function startGestureSampling() {
  gestureStartedAt = performance.now(); lastSampleAt = null; frameIntervals = [];
  sampleFrameId = requestAnimationFrame(sampleGestureFrame);
}
function stopGestureSampling() {
  if (gestureStartedAt === null) return;
  cancelAnimationFrame(sampleFrameId);
  const seconds = (performance.now() - gestureStartedAt) / 1000;
  const sorted = [...frameIntervals].sort((a, b) => a - b);
  const p95 = sorted[Math.max(0, Math.ceil(sorted.length * .95) - 1)];
  $('gestureDuration').textContent = `${seconds.toFixed(1)} 秒`;
  $('gestureP95').textContent = p95 === undefined ? '取樣不足' : `${p95.toFixed(1)} ms`;
  $('gestureLongFrames').textContent = String(frameIntervals.filter(ms => ms > 50).length);
  $('gestureFrameSamples').textContent = String(frameIntervals.length);
  gestureStartedAt = null; lastSampleAt = null; sampleFrameId = null;
}
function startPinch() {
  const points = [...pointers.values()].slice(0, 2);
  const mid = { x: (points[0].x + points[1].x) / 2, y: (points[0].y + points[1].y) / 2 };
  pinchStart = { distance: Math.max(1, Math.hypot(points[1].x - points[0].x, points[1].y - points[0].y)),
    world: transform.invert([mid.x, mid.y]), k: transform.k };
  pointerMoved = true; hadMultiplePointers = true; pointerNode = null;
}
function pointerDown(event) {
  if (event.pointerType === 'mouse' && event.button !== 0) return;
  event.preventDefault(); canvas.setPointerCapture(event.pointerId); simulation.stop();
  if (!pointers.size) startGestureSampling();
  const point = localPoint(event); pointers.set(event.pointerId, point);
  if (pointers.size === 1) {
    pointerStart = point; pointerBaseTransform = transform;
    pointerNode = hitNode(point);
    pointerMoved = false; hadMultiplePointers = false;
  } else startPinch();
}
function pointerMove(event) {
  const point = localPoint(event);
  if (!pointers.has(event.pointerId)) {
    if (event.pointerType === 'mouse') {
      const node = hitNode(point); if (node?.id !== hoveredId) { hoveredId = node?.id || null; scheduleDraw(); }
    }
    return;
  }
  event.preventDefault();
  const previousPoint = pointers.get(event.pointerId);
  pointers.set(event.pointerId, point);
  if (pointers.size >= 2) {
    const points = [...pointers.values()].slice(0, 2);
    const next = pinchTransform(pinchStart, points[0], points[1]);
    applyTransform(next.x, next.y, next.k);
    userHasMovedView = true; return;
  }
  if (Math.hypot(point.x - pointerStart.x, point.y - pointerStart.y) > 5) pointerMoved = true;
  if (!pointerMoved) return;
  const next = panTransform(pointerBaseTransform, pointerStart, point);
  applyTransform(next.x, next.y, next.k);
  if (!reducedMotion) sway = swayImpulse(sway, point.x - previousPoint.x, point.y - previousPoint.y);
  userHasMovedView = true;
}
function pointerEnd(event) {
  if (!pointers.has(event.pointerId)) return;
  event.preventDefault();
  const point = pointers.get(event.pointerId);
  const releasePoint = localPoint(event);
  if (pointerStart && Math.hypot(releasePoint.x - pointerStart.x, releasePoint.y - pointerStart.y) > 5) pointerMoved = true;
  if (pointers.size === 1 && pointerMoved) {
    const next = panTransform(pointerBaseTransform, pointerStart, releasePoint);
    applyTransform(next.x, next.y, next.k);
    if (!reducedMotion) sway = swayImpulse(sway, releasePoint.x - point.x, releasePoint.y - point.y);
    userHasMovedView = true;
  }
  pointers.delete(event.pointerId);
  if (canvas.hasPointerCapture(event.pointerId)) canvas.releasePointerCapture(event.pointerId);
  if (pointers.size >= 2) { startPinch(); return; }
  if (pointers.size === 1) {
    pointerNode = null; pointerStart = [...pointers.values()][0]; pointerBaseTransform = transform;
    pointerMoved = true; scheduleDraw(); return;
  }
  stopGestureSampling();
  if (tapEligible(pointerMoved, hadMultiplePointers, event.type === 'pointercancel')) {
    const node = pointerNode || hitNode(point);
    if (node) selectNode(node, false);
  }
  pointerNode = null; pointerStart = null; pinchStart = null;
  maybeResumeLayout();
  scheduleDraw();
}
canvas.addEventListener('pointerdown', pointerDown);
canvas.addEventListener('pointermove', pointerMove);
canvas.addEventListener('pointerup', pointerEnd);
canvas.addEventListener('pointercancel', pointerEnd);
canvas.addEventListener('pointerleave', () => { if (!pointers.size) { hoveredId = null; scheduleDraw(); } });
$('resultList').addEventListener('click', event => {
  const button = event.target.closest('button[data-node-id]'); if (!button) return;
  selectNode(allNodes.get(button.dataset.nodeId), true);
  if (window.matchMedia('(max-width: 760px)').matches) $('graphDetails').scrollIntoView({ block: 'start', behavior: reducedMotion ? 'instant' : 'smooth' });
});
$('detailsJump').addEventListener('click', () => $('graphDetails').scrollIntoView({ block: 'start', behavior: reducedMotion ? 'instant' : 'smooth' }));
$('zoomIn').addEventListener('click', () => { userHasMovedView = true; canvasSelection.call(zoomBehavior.scaleBy, 1.3); });
$('zoomOut').addEventListener('click', () => { userHasMovedView = true; canvasSelection.call(zoomBehavior.scaleBy, 1 / 1.3); });
$('fitGraph').addEventListener('click', fitGraph);
$('clearFilters').addEventListener('click', () => {
  controls.search.value = ''; controls.scope.value = 'core'; controls.testament.value = 'both';
  controls.book.value = ''; controls.group.value = ''; controls.topic.value = ''; controls.evidence.value = '';
  controls.pentateuch.checked = false; controls.speech.checked = false; controls.compare.checked = false; controls.topics.checked = true;
  buildVisible();
});
let searchTimer;
for (const [name, control] of Object.entries(controls)) {
  control.addEventListener(name === 'search' ? 'input' : 'change', () => {
    if (name === 'search') { clearTimeout(searchTimer); searchTimer = setTimeout(buildVisible, 120); }
    else buildVisible();
  });
}
function focusHash() {
  const id = decodeURIComponent(location.hash.slice(1));
  const entry = entriesById.get(id); if (!entry) return;
  if (!entry.core && controls.scope.value === 'core') controls.scope.value = 'all';
  if (!matchesEntry(entry, readState())) {
    controls.search.value = ''; controls.book.value = ''; controls.group.value = '';
    controls.topic.value = ''; controls.evidence.value = ''; controls.pentateuch.checked = false;
    controls.speech.checked = false; controls.compare.checked = false;
  }
  buildVisible();
  if (!reducedMotion) { simulation.stop(); simulation.tick(65); scheduleDraw(); }
  selectNode(entryNodes.get(id), true, false);
}
window.addEventListener('hashchange', focusHash);
if (window.matchMedia('(max-width: 760px)').matches) $('graphControls').querySelector('.filter-fold').open = false;
new ResizeObserver(resizeCanvas).observe(stage);
resizeCanvas(); buildVisible(); focusHash();
window.EMMAUS_GRAPH_APP = { readState, getVisible: () => ({ entries: visibleEntries.map(entry => entry.id), nodes: visibleNodes.map(node => node.id), links: visibleLinks.length }), selectEntry: id => selectNode(entryNodes.get(id), true) };
