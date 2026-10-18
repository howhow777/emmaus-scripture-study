#!/usr/bin/env python3
"""Reproducible scoped NT coverage audit, independent of the original study list."""
import argparse, copy, hashlib, html, importlib.util, json, re
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
spec=importlib.util.spec_from_file_location('previews',ROOT/'scripts/build-scripture-previews.py')
previews=importlib.util.module_from_spec(spec);spec.loader.exec_module(previews)
CANDIDATE=re.compile('經上|記著|記着|應驗|先知|摩西|亞伯拉罕|挪亞|羅得|約拿|所羅門|大衞|以利亞|以利沙|銅蛇|嗎哪|會幕|麥基洗德|逾越|亞當|磐石|枝子|羔羊|人子|後裔|以撒|雅各|所多瑪|蛾摩拉|亞伯|約瑟|亞倫|聖所|祭司|聖殿|巴蘭|耶洗別|你們聽見|有話說|吩咐古人|誡命|律法|以賽亞|耶利米|但以理|撒迦利亞|何西阿')
OT_NAMES=set('創世記 出埃及記 利未記 民數記 申命記 約書亞記 士師記 路得記 撒母耳記上 撒母耳記下 列王紀上 列王紀下 歷代志上 歷代志下 以斯拉記 尼希米記 以斯帖記 約伯記 詩篇 箴言 傳道書 雅歌 以賽亞書 耶利米書 耶利米哀歌 以西結書 但以理書 何西阿書 約珥書 阿摩司書 俄巴底亞書 約拿書 彌迦書 那鴻書 哈巴谷書 西番雅書 哈該書 撒迦利亞書 瑪拉基書'.split())
def ot_footnotes(source):
 """Translator cross-references form a second candidate source, outside our studies."""
 result={}
 for line in source.splitlines():
  anchor=re.search(r'\{\{anchor\|([^}]+)\}\}',line,re.I)
  targets=re.findall(r'\[\[\.\./([^#|\]]+)(?:#([^|\]]+))?',line)
  refs=[book+(' '+verse if verse else '') for book,verse in targets if book in OT_NAMES]
  if anchor and refs:result[anchor[1]]=refs
 return result
def read(name):return json.loads((ROOT/name).read_text())
def asset(name):return json.loads((ROOT/name).read_text().split('=',1)[1].rstrip().removesuffix(';'))
def span(ref):
 m=re.fullmatch(r'([A-Z0-9]+) (\d+)(?::(\d+)(?:-(\d+))?)?',ref)
 if not m:raise ValueError(ref)
 return m[1],int(m[2]),int(m[3] or 1),int(m[4] or m[3] or 999)
def contains(parent,child):
 a,b,c,d=span(parent);e,f,g,h=span(child);return (a,b)==(e,f) and c<=g and d>=h
def href(ref):return 'https://www.bible.com/bible/46/'+ref.replace(' ','.').replace(':','.')+'.CUNP-%E7%A5%9E'
def build():
 pins=read('data/audit-source-pins.json');baseline=read('data/research-baseline.json');graph=asset('graph-data.js');supp=read('data/coverage/supplemental-passages.json')
 decisions=[];books=[];source_notes=[];exclusions=read('data/coverage/review-exclusions.json')
 for code,pin in pins.items():
  path=previews.DEFAULT_SOURCE_DIR/(code+'.txt');assert hashlib.sha256(path.read_bytes()).hexdigest()==pin['sha256']
  chapters=previews.parse_book(code,previews.DEFAULT_SOURCE_DIR);footnotes=ot_footnotes(path.read_text())
  assert sorted(chapters)==list(range(1,len(chapters)+1)),code
  count=0;book_rows=[]
  for ch,verses in chapters.items():
   assert sorted(verses)==list(range(1,max(verses)+1)),(code,ch)
   for number,raw in verses.items():
    count+=1;ref=f'{code} {ch}:{number}'
    if not raw:
     source_notes.append({'ref':ref,'kind':'combined-numbering','note':'固定來源將本節與下一節合排；不當作不存在的經文。'});continue
    text=previews.plain_verse(raw)
    if text.startswith('（本來源異文註：'):source_notes.append({'ref':ref,'kind':'textual-variant-note','note':'來源在此節僅列異文註，須明示與正文不同。'})
    crossrefs=list(dict.fromkeys(target for anchor in re.findall(r'\[\[#([^|\]]+)\|',raw) for target in footnotes.get(anchor,[])))
    triggers=list(dict.fromkeys(CANDIDATE.findall(text)))
    if crossrefs:triggers.append('來源舊約交叉註')
    if not triggers:continue
    original=[e['id'] for e in baseline['graphEntries'] if any(contains(p['ref'],ref) for p in e['nt'])]
    final=[e['id'] for e in graph['entries'] if any(contains(p['ref'],ref) for p in e['nt'])]
    supplement=next((r for r in supp if contains(r['ref'],ref)),None)
    if ref in exclusions:
     status='excluded';reason=exclusions[ref]
    elif final:
     status='included';reason='已列於有解說與解釋界線的研究引用；保留上下文，不將每個附帶語詞都當作獨立預言。'
    elif supplement:
     status='supplemental';reason=supplement['reason']
    elif code=='JUD' and number in [9,14]:
     status='excluded';reason='此段涉及舊約正典未記載的傳統（摩西屍首／以諾的宣告）；本輪不擴大正典來源或斷言身份與預言歸屬。'
    elif '以利沙伯' in text or set(triggers)<=set(['約瑟','雅各','祭司','聖殿','聖所','先知']):
     status='excluded';reason='此處是新約人物姓名、職分或敘事場景；未在本節辨認某項舊約對耶穌的引用、預表或應許成全。以利沙伯不等於先知以利沙，新約雅各／約瑟也不自動等同列祖。'
    elif code in ['ROM','1CO','2CO','GAL','EPH','1TH','1TI','2TI','JAS','1PE','2PE','HEB']:
     status='excluded';reason='上下文主要以舊約說明信徒倫理、群體生活、歷史或信心榜樣；本節未單獨辨認耶穌身分或預言成全，也非耶穌親口引用。本研究不因出現舊約人名便擴充為全本經文索引。'
    elif code=='ACT':
     status='excluded';reason='此處主要是使徒敘事、人物或以色列歷史回顧；沒有在此節建立可核對的耶穌身分／預表對應。與耶穌相連的講論另以完整段落收錄。'
    elif code=='REV':
     status='excluded';reason='此處主要是異象情境或教會／先知群體的敘述，未另建立特定舊約與基督的明示對應；不是宣稱與基督毫無關係。已有明示羔羊、王權、生命與救贖的相關段落另列。'
    else:
     status='review-required';reason='須逐段補入判定，不得以無結果代替審核。'
    row={'ref':ref,'text':text,'triggers':triggers,'status':status,'reason':reason,'originalEntries':original,'entryIds':final}
    if crossrefs:row['sourceOtCrossReferences']=crossrefs
    if supplement:row['supplementalRef']=supplement['ref']
    book_rows.append(row);decisions.append(row)
  books.append({'book':code,'name':pin['name'],'chapters':len(chapters),'verseMarkers':count,'sourceRevision':pin['revision'],'sourceSha256':pin['sha256'],'sourceUrl':f'https://zh.wikisource.org/w/index.php?oldid={pin["revision"]}', 'candidates':len(book_rows),'included':sum(r['status']=='included' for r in book_rows),'supplemental':sum(r['status']=='supplemental' for r in book_rows),'excluded':sum(r['status']=='excluded' for r in book_rows),'pending':sum(r['status']=='review-required' for r in book_rows)})
 manifest={'version':1,'method':'27卷新約、260章逐章完整來源掃描；以固定的引文／人物／稱號／律法觸發詞，加上固定來源的舊約交叉註，產生可重現候選，再依研究引用及逐段範圍判定。來源交叉註只觸發審核，不自動建立圖譜連線。候選集合獨立於原186組，並非宣稱已窮盡所有學界有爭議的互文。','scope':'耶穌的舊約引用、人物事件比較、身分與降生、捨命救贖、復活及應許的見證；不提供全本聖經搜尋。','originalStudies':186,'studies':len(graph['entries']),'core':49,'books':books,'sourceNotes':source_notes,'candidates':decisions}
 return manifest,supp,graph

def page(manifest,supp,graph):
 names={k:v['name'] for k,v in graph['books'].items()};dates=read('data/passage-dates.json')['references']
 def citation(ref):
  d=dates[ref];label=names.get(ref.split()[0],ref.split()[0])+' '+ref.split()[1].replace('-','–');anchor='date-'+re.sub('[^A-Za-z0-9]+','-',ref).strip('-')
  return f'<a class="scripture" href="{href(ref)}" target="_blank" rel="noopener noreferrer">{label}</a><small>背景：{html.escape(d["background"]["label"])}｜成書：{html.escape(d["composition"]["label"])} <a href="dating.html#{anchor}">年代依據</a></small>'
 text='''<!doctype html><html lang="zh-Hant-TW"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>經文覆蓋查核｜以馬忤斯之路</title><link rel="stylesheet" href="graph.css?v=coverage1"><link rel="stylesheet" href="scripture-preview.css?v=full-preview1"><script defer src="scripture-previews-data.js?v=full-preview1"></script><script defer src="scripture-preview.js?v=full-preview1"></script><style>main{max-width:1000px;margin:auto;padding:24px}table{border-collapse:collapse;width:100%;font-size:13px}td,th{padding:8px;border-bottom:1px solid #456}small{display:block;color:#b5c5bb}li{margin:15px 0}.scope-note{padding:14px;border:1px solid #987;border-radius:12px}</style><main><nav><a href="index.html">研究首頁</a> · <a href="graph.html">互動圖譜</a></nav><h1>經文覆蓋查核</h1>'''
 text+='<p class="scope-note">'+manifest['scope']+' 原有186組及49組主線保留；補收20組研究與57處平行／相關引用。下列補充經文在研究範圍內，但未以新實線強行連結舊約。未另建研究條目不代表經文沒有價值。</p>'
 text+='<p>'+manifest['method']+'</p><p><a href="data/coverage-manifest.json">下載逐項判定與來源</a> · <a href="reports/search-audit-report.md">問題與驗證報告</a></p><h2>27卷查核表</h2><div style="overflow:auto"><table><tr><th>書卷</th><th>章</th><th>節號</th><th>候選</th><th>研究引用</th><th>補充</th><th>範圍排除</th><th>待審</th></tr>'
 for b in manifest['books']:text+='<tr><td><a href="'+b['sourceUrl']+'">'+b['name']+'</a></td>'+''.join('<td>'+str(b[k])+'</td>' for k in ['chapters','verseMarkers','candidates','included','supplemental','excluded','pending'])+'</tr>'
 text+='</table></div><h2>範圍內的補充經文</h2><p>搜尋可找到這些引用；圖上沒有新增研究實線。含耶穌發言的段落仍需分辨旁白與對話者。</p><ul>'
 for item in supp:text+='<li id="supp-'+re.sub('[^A-Za-z0-9]+','-',item['ref'])+'">'+citation(item['ref'])+'<p>'+html.escape(item['reason'])+'</p></li>'
 text+='</ul><h2>來源注意事項</h2><p>固定維基文庫來源有合排節號與異文註；預覽會明示，不以空白當作該節不存在。經文文字不因搜尋正規化而改寫。</p></main></html>'
 return text

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');parser.add_argument('--fetch',action='store_true');a=parser.parse_args()
 if a.fetch:
  from urllib.request import Request,urlopen
  pins=read('data/audit-source-pins.json');previews.DEFAULT_SOURCE_DIR.mkdir(parents=True,exist_ok=True)
  for code,pin in pins.items():
   request=Request(f'https://zh.wikisource.org/w/index.php?oldid={pin["revision"]}&action=raw',headers={'User-Agent':'EmmausCoverageAudit/1.0'})
   raw=urlopen(request,timeout=30).read()
   if hashlib.sha256(raw).hexdigest()!=pin['sha256']:raise ValueError('Pinned source changed: '+code)
   (previews.DEFAULT_SOURCE_DIR/(code+'.txt')).write_bytes(raw)
 manifest,supp,graph=build()
 files={'data/coverage-manifest.json':json.dumps(manifest,ensure_ascii=False,indent=2)+'\n','coverage.html':page(manifest,supp,graph)}
 for name,text in files.items():
  path=ROOT/name
  if a.check:
   if not path.exists() or path.read_text()!=text:raise SystemExit(name+' is out of date')
  else:path.write_text(text)
 print('Coverage:',len(manifest['books']),'books,',sum(b['verseMarkers'] for b in manifest['books']),'verse markers,',len(manifest['candidates']),'candidates;',sum(b['pending'] for b in manifest['books']),'pending')
 if not a.check:
  pending=[x['ref']+' '+x['text'] for x in manifest['candidates'] if x['status']=='review-required'];print('\n'.join(pending))
if __name__=='__main__':main()
