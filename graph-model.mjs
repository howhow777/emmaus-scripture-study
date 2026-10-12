// Shared, DOM-free selection logic for the graph and its data checks.
export function normalizeQuery(value) {
  return String(value).normalize('NFKC').toLocaleLowerCase().replace(/[\p{P}\p{Z}\p{S}]+/gu, '');
}

export function passageSearchIndex(passages) {
  return Object.fromEntries(Object.entries(passages).map(([ref, verses]) =>
    [ref, verses.map(verse => normalizeQuery(verse.text))]));
}

export function nodeMatchesKeyword(node, value, passageSearch = {}) {
  const query = normalizeQuery(value);
  if (!query) return false;
  if (node.kind === 'entry') return normalizeQuery(node.entry.text).includes(query);
  return normalizeQuery(`${node.label} ${node.ref || ''}`).includes(query)
    || Boolean(passageSearch[node.ref]?.some(verse => verse.includes(query)));
}

export function entryMatches(entry, state, books, spokenEntryIds, passageSearch = {}) {
  const passages = [...entry.ot, ...entry.nt];
  const hasBook = code => passages.some(passage => passage.ref.startsWith(code + ' '));
  const hasGroup = group => passages.some(passage => books[passage.ref.split(' ')[0]]?.group === group);
  if (state.scope === 'core' && !entry.core) return false;
  if (state.evidence && entry.ev !== state.evidence) return false;
  if (state.topic && !entry.tags.includes(state.topic)) return false;
  if (state.book && !hasBook(state.book)) return false;
  if (state.group && !hasGroup(state.group)) return false;
  if (state.pentateuch && !hasGroup('pentateuch')) return false;
  if (state.speech && !spokenEntryIds.has(entry.id)) return false;
  if (state.compare && !entry.jesus) return false;
  if (state.search) {
    const query = normalizeQuery(state.search);
    if (query && !normalizeQuery(entry.text).includes(query)
      && !passages.some(passage => passageSearch[passage.ref]?.some(verse => verse.includes(query)))
      && !state.semanticEntryIds?.has(entry.id)
      && !passages.some(passage => state.semanticRefs?.has(passage.ref))) return false;
  }
  return true;
}

export function visibleGraph(data, state, passageSearch = {}) {
  const spokenRefs = new Set(data.speech.map(item => `${item.entryId}|${item.ntRef}`));
  const spokenEntryIds = new Set(data.speech.map(item => item.entryId));
  const entries = data.entries.filter(entry => entryMatches(entry, state, data.books, spokenEntryIds, passageSearch));
  const nodes = new Set(entries.map(entry => `entry:${entry.id}`));
  const links = [];
  for (const entry of entries) {
    for (const testament of ['ot', 'nt']) {
      if (state.testament !== 'both' && state.testament !== testament) continue;
      for (const passage of entry[testament]) {
        const spoken = testament === 'nt' && spokenRefs.has(`${entry.id}|${passage.ref}`);
        if (state.speech && testament === 'nt' && !spoken) continue;
        const target = `${testament}:${passage.ref}`;
        nodes.add(target);
        links.push({ source: `entry:${entry.id}`, target, kind: 'citation', entryId: entry.id, testament, ref: passage.ref, spoken });
      }
    }
    if (state.topics) for (const topic of entry.tags) {
      const target = `topic:${topic}`;
      nodes.add(target);
      links.push({ source: `entry:${entry.id}`, target, kind: 'topic', entryId: entry.id, topic });
    }
  }
  return { entries, nodeIds: [...nodes], links };
}
