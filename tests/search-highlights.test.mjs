import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { nodeMatchesKeyword, passageSearchIndex, visibleGraph } from '../graph-model.mjs';
const asset = name => JSON.parse(readFileSync(new URL('../'+name, import.meta.url),'utf8').split('=').slice(1).join('=').trim().slice(0,-1));
const data = asset('graph-data.js'), corpus = asset('scripture-search-data.js').passages;
const index = passageSearchIndex(corpus);
const base = { scope:'all',testament:'both',book:'',group:'',topic:'',evidence:'',pentateuch:false,speech:false,compare:false,topics:false,search:'' };
test('Thomas is in the full corpus and an explicitly core-only search hides E167', () => {
  assert.ok(visibleGraph(data,{...base,search:'多馬'},index).entries.some(x=>x.id==='E167'));
  assert.equal(visibleGraph(data,{...base,scope:'core',search:'多馬'},index).entries.length,0);
});
test('literal highlighting does not color the linked OT passage when it lacks the word', () => {
  assert.equal(nodeMatchesKeyword({kind:'nt',label:'約翰福音',ref:'JHN 20:25-27'},'釘痕',index),true);
  assert.equal(nodeMatchesKeyword({kind:'ot',label:'撒迦利亞書',ref:'ZEC 13:6'},'釘痕',index),false);
  assert.equal(nodeMatchesKeyword({kind:'nt',label:'約翰福音',ref:'JHN 20:25-27'},'',index),false);
});
test('semantic passage hits retain original edges and compose with other filters', () => {
  const state={...base,search:'不相信復活，要摸手才肯信',semanticRefs:new Set(['JHN 20:25-27']),semanticEntryIds:new Set()};
  const result=visibleGraph(data,state,index);
  assert.deepEqual(result.entries.map(x=>x.id),['E167']);
  assert.ok(result.nodeIds.includes('ot:ZEC 13:6'));
  assert.equal(result.links.length,2);
  assert.equal(visibleGraph(data,{...state,scope:'core'},index).entries.length,0);
  assert.equal(visibleGraph(data,{...state,evidence:'A'},index).entries.length,0);
  assert.equal(visibleGraph(data,{...state,testament:'ot'},index).nodeIds.some(x=>x.startsWith('nt:')),false);
});
test('semantic entry matches do not require literal wording', () => {
  const result=visibleGraph(data,{...base,search:'看傷才信',semanticEntryIds:new Set(['E167'])},index);
  assert.deepEqual(result.entries.map(x=>x.id),['E167']);
});
