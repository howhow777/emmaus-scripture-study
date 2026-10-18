import assert from 'node:assert/strict';
import test from 'node:test';
import {readFileSync} from 'node:fs';
import {normalizeQuery,passageSearchIndex,entryMatches,nodeMatchesKeyword,standaloneMatches,visibleGraph} from '../graph-model.mjs';
const json=n=>JSON.parse(readFileSync(new URL('../'+n,import.meta.url),'utf8'));
const asset=n=>JSON.parse(readFileSync(new URL('../'+n,import.meta.url),'utf8').split('=').slice(1).join('=').trim().slice(0,-1));
const graph=asset('graph-data.js'),corpus=asset('scripture-search-data.js'),index=passageSearchIndex(corpus.passages);
const additions=json('data/research-additions.json');
const baseline=json('data/research-baseline.json'),manifest=json('data/coverage-manifest.json'),golden=json('data/coverage/search-golden.json');
const base={scope:'all',testament:'both',book:'',group:'',topic:'',evidence:'',pentateuch:false,speech:false,compare:false,search:'',topics:false};
test('the independent NT audit covers 27 books, all 260 chapters, 7957 markers and has no unreviewed candidates',()=>{
 assert.equal(manifest.books.length,27);assert.equal(new Set(manifest.books.map(b=>b.book)).size,27);
 assert.equal(manifest.books.reduce((n,b)=>n+b.chapters,0),260);assert.equal(manifest.books.reduce((n,b)=>n+b.verseMarkers,0),7957);
 assert.equal(manifest.candidates.length,1220);assert.equal(manifest.books.reduce((n,b)=>n+b.pending,0),0);
 for(const ref of ['MAT 5:21','MAT 5:27','MAT 19:19','JHN 8:17'])assert.ok(manifest.candidates.find(r=>r.ref===ref)?.sourceOtCrossReferences?.length,ref+' independent translator cross-reference');
 assert.ok(manifest.candidates.some(r=>r.ref==='MAT 24:37'&&!r.originalEntries.length&&r.entryIds.includes('E187')));
 assert.ok(manifest.candidates.every(r=>r.reason&&['included','supplemental','excluded'].includes(r.status)));
 assert.ok(manifest.sourceNotes.some(n=>n.ref==='LUK 2:34'));
});
test('original studies, core selection, original citations and original speech spans are preserved',()=>{
 const full=JSON.parse(/<script\b[^>]*\bid="fullData"[^>]*>([\s\S]*?)<\/script>/.exec(readFileSync(new URL('../index.html',import.meta.url),'utf8'))[1]);
 for(const original of baseline.entries){
  const current=full.find(e=>e.id===original.id);assert.ok(current,original.id);
  for(const key of ['title','ot','ev','kind','tags','context','bridge','limit','core','jesus'])assert.deepEqual(current[key],original[key],original.id+' '+key);
  for(const ref of original.nt.split(';'))assert.ok(current.nt.split(';').includes(ref),original.id+' '+ref);
 }
 for(const approved of additions.newStudies){const current=full.find(e=>e.id===approved.id);for(const [key,value] of Object.entries(approved))if(key!=='speech')assert.deepEqual(current[key],value,approved.id+' '+key);}
 const reading=readFileSync(new URL('../index.html',import.meta.url),'utf8');
 for(const id of full.map(e=>e.id))assert.match(reading,new RegExp('data-read="'+id+'"'),id+' reading footer must exist before navigation initializes');
 assert.deepEqual(graph.entries.filter(e=>e.core).map(e=>e.id),baseline.coreEntryIds);
 for(const speech of baseline.speech)assert.ok(graph.speech.some(s=>JSON.stringify(s)===JSON.stringify(speech)));
});
test('all 60 independently selected literal golden cases agree with the actual search pipeline',()=>{
 assert.equal(golden.literal.length,60);assert.equal(golden.literal.filter(c=>c.kind==='positive').length,40);
 for(const c of golden.literal){
  const query=normalizeQuery(c.query);const found=Object.keys(corpus.passages).filter(ref=>index[ref].some(v=>v.includes(query)));
  if(c.kind==='negative')assert.deepEqual(found,[],c.id+' '+c.query);
  else for(const ref of c.expectedRefs){
   if(c.expectedHit==='study-title'){const result=visibleGraph(graph,{...base,search:c.query},index);for(const id of c.expectedEntries)assert.ok(result.entries.some(e=>e.id===id),c.id+' '+id);assert.ok(result.nodeIds.some(n=>n.endsWith(':'+ref)),c.id+' linked '+ref);}
   else assert.ok(found.includes(ref),c.id+' '+c.query+' missing '+ref);
   const related=graph.entries.filter(e=>[...e.ot,...e.nt].some(p=>p.ref===ref));
   for(const entry of related)assert.ok(entryMatches(entry,{...base,search:c.query},graph.books,new Set(),index),c.id+' entry '+entry.id);
  }
 }
});
test('every indexed verse or explicitly merged verse is reachable by its own full text',()=>{
 let checked=0;
 for(const [ref,verses] of Object.entries(corpus.passages))for(const verse of verses){
  assert.ok(nodeMatchesKeyword({kind:graph.books[ref.split(' ')[0]].testament,ref,label:ref},verse.text,index),ref+' '+verse.number);
  for(const entry of graph.entries.filter(e=>[...e.ot,...e.nt].some(p=>p.ref===ref)))assert.ok(entryMatches(entry,{...base,search:verse.text},graph.books,new Set(),index),entry.id+' '+ref);
  checked++;
 }
 assert.equal(checked,4188);
});
test('law quotations without a named OT person remain searchable after the independent source audit',()=>{
 for(const [query,ref] of [['不可殺人','MAT 5:21-48'],['不可姦淫','MRK 10:17-22'],['兩個人的見證','JHN 8:17-18'],['兩三個人的口','MAT 18:16']])assert.ok(index[ref].some(text=>text.includes(normalizeQuery(query))),ref+' '+query);
});
test('Noah survives the verified-Jesus filter and filters do not invent citation edges',()=>{
 const result=visibleGraph(graph,{...base,search:'挪亞',speech:true},index);
 assert.ok(result.entries.some(e=>e.id==='E187'));
 for(const ref of ['MAT 24:37-39','LUK 17:26-27'])assert.ok(result.nodeIds.includes('nt:'+ref));
 const scoped=visibleGraph(graph,{...base,search:'挪亞',book:'MAT',speech:true,testament:'nt'},index);
 assert.ok(scoped.entries.some(e=>e.id==='E187'));assert.ok(scoped.nodeIds.every(n=>!n.startsWith('ot:')));
 assert.equal(visibleGraph(graph,{...base,search:'挪亞',scope:'core'},index).entries.length,0);
});
test('speaker annotations exclude the lawyer, narrator and divine voice from Jesus-only spans',()=>{
 const speech=graph.speech.filter(s=>s.entryId==='E194'&&s.ntRef==='LUK 10:25-28')[0];
 assert.deepEqual(speech.spans.map(s=>s.ref),['LUK 10:26','LUK 10:28']);
 assert.ok(!graph.speech.some(s=>s.ntRef==='JHN 12:32-34'&&s.spans.some(x=>x.ref.includes('33'))));
 assert.ok(!graph.speech.some(s=>s.entryId==='E196'&&s.spans.some(x=>x.ref.includes('17:5'))));
});
test('search normalizes common reference and orthographic variants without rewriting the Bible',()=>{
 assert.equal(normalizeQuery('太24：37'),normalizeQuery('馬太福音 24:37'));
 assert.equal(normalizeQuery('挪亚'),normalizeQuery('挪亞'));assert.equal(normalizeQuery('大衞'),normalizeQuery('大衛'));
 assert.equal(normalizeQuery('喫喝'),normalizeQuery('吃喝'));
 assert.ok(corpus.passages['MAT 24:37-39'].some(v=>v.text.includes('喫喝')));
});
test('unlinked scope citations respect testament, book and verified-speech filters',()=>{
 assert.equal(standaloneMatches('LUK 3:23-38',{...base,speech:true},graph.books,new Set()),false);
 assert.equal(standaloneMatches('LUK 3:23-38',{...base,testament:'ot'},graph.books),false);
 assert.equal(standaloneMatches('LUK 3:23-38',{...base,book:'MAT'},graph.books),false);
 assert.equal(standaloneMatches('LUK 3:23-38',base,graph.books),true);
});
