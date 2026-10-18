// Shared, DOM-free selection logic for the graph and its data checks.
// Search-only equivalences; never rewrite displayed scripture text.
const SEARCH_FORMS = { '衞':'衛','喫':'吃','豫':'預','眞':'真','着':'著','爲':'為','裏':'裡','羣':'群','亚':'亞','钉':'釘','马':'馬','罗':'羅','约':'約','圣':'聖','经':'經','诗':'詩','记':'記','创':'創','赛':'賽','书':'書' };
const BOOK_QUERIES = { '創世記':'GEN','創':'GEN','出埃及記':'EXO','出':'EXO','利未記':'LEV','利':'LEV','民數記':'NUM','民':'NUM','申命記':'DEU','申':'DEU','詩篇':'PSA','詩':'PSA','以賽亞書':'ISA','賽':'ISA','馬太福音':'MAT','馬太':'MAT','太':'MAT','馬可福音':'MRK','馬可':'MRK','可':'MRK','路加福音':'LUK','路加':'LUK','路':'LUK','約翰福音':'JHN','約翰':'JHN','約':'JHN','使徒行傳':'ACT','徒':'ACT','羅馬書':'ROM','羅':'ROM','希伯來書':'HEB','來':'HEB','啟示錄':'REV','啟':'REV' };
const BOOK_PATTERN = new RegExp('(' + Object.keys(BOOK_QUERIES).sort((a,b)=>b.length-a.length).join('|') + ')\\s*(?=[0-9])', 'g');
export function normalizeQuery(value) {
  return String(value).normalize('NFKC').replace(/[衞喫豫眞着爲裏羣亚钉马罗约圣经诗记创赛书]/g, c => SEARCH_FORMS[c])
    .replace(BOOK_PATTERN, (_, name) => BOOK_QUERIES[name])
    .toLocaleLowerCase().replace(/[\p{P}\p{Z}\p{S}]+/gu, '');
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

export function standaloneMatches(ref, state, books, spokenRefs = new Set()) {
  const code = ref.split(' ')[0], book = books[code];
  if (!book) return false;
  if (state.testament !== 'both' && state.testament !== book.testament) return false;
  if (state.book && state.book !== code) return false;
  if (state.group && state.group !== book.group) return false;
  if (state.pentateuch && book.group !== 'pentateuch') return false;
  if (state.speech && !spokenRefs.has(ref)) return false;
  // These attributes describe a study, so an unlinked citation cannot satisfy them.
  if (state.topic || state.evidence || state.compare) return false;
  return true;
}
