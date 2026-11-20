"""Parse downloaded CISA advisory HTML files into structured JSON + plain text.
Usage: python3 -I parse_cisa.py <raw_dir> <out_dir>
"""
import sys, os, re, json, hashlib
from bs4 import BeautifulSoup, NavigableString, Tag

raw, out = sys.argv[1], sys.argv[2]
os.makedirs(out, exist_ok=True)

STOP_SECTIONS = re.compile(r'^(mitigations?|recommendations|validate security controls|resources|references|acknowledg|disclaimer|version history|appendix|indicators of compromise|contact information|reporting|purpose|notes|works cited|detection|mitre att&ck tactics and techniques|mitre att&ck techniques)', re.I)
ATTACK_SECTION = re.compile(r'mitre att&ck', re.I)
WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9'\-\.]*")

def words(t): return len(WORD.findall(t))

def main_container(s):
    cands = s.select('.l-page-section--rich-text .l-page-section__content') or s.select('.l-page-section__content')
    return max(cands, key=lambda c: len(c.get_text()))

rows=[]
for fn in sorted(os.listdir(raw)):
    if not fn.endswith('.html'): continue
    cid = fn[:-5]
    s = BeautifulSoup(open(os.path.join(raw,fn),encoding='utf-8').read(),'html.parser')
    title = s.select_one('.c-page-title__title').get_text(' ',strip=True)
    meta = {}
    for f in s.select('.c-field'):
        lab = f.select_one('.c-field__label')
        if lab:
            k = lab.get_text(' ',strip=True)
            v = f.get_text(' ',strip=True)[len(k):].strip()
            meta.setdefault(k, v)
    c = main_container(s)
    # walk block elements in order, tracking h2/h3 headings
    blocks=[]; cur_h2=''; cur_h3=''
    for el in c.descendants:
        if not isinstance(el, Tag): continue
        if el.name in ('h1','h2'):
            cur_h2 = el.get_text(' ',strip=True); cur_h3=''
            blocks.append(('heading', cur_h2, cur_h3, cur_h2)); continue
        if el.name in ('h3','h4'):
            if el.name=='h3': cur_h3 = el.get_text(' ',strip=True)
            blocks.append(('heading', cur_h2, cur_h3, el.get_text(' ',strip=True))); continue
        if el.name in ('p','li') and not el.find_parent('table'):
            if not el.find(['p','li']):
                blocks.append(('text', cur_h2, cur_h3, el.get_text(' ',strip=True)))
            else:
                # element has nested blocks: keep its own inline text (e.g. a CVE ID before a nested description)
                parts=[]
                for ch in el.children:
                    if isinstance(ch, NavigableString): parts.append(str(ch))
                    elif isinstance(ch, Tag) and ch.name not in ('p','li','ul','ol','div','table','h1','h2','h3','h4','h5','h6'):
                        parts.append(ch.get_text(' '))
                own=re.sub(r'\s+',' ',' '.join(parts)).strip()
                if own: blocks.append(('text', cur_h2, cur_h3, own))
        if el.name=='table':
            cap = el.find('caption')
            rows_ = [[td.get_text(' ',strip=True) for td in tr.find_all(['td','th'])] for tr in el.find_all('tr')]
            blocks.append(('table', cur_h2, cur_h3, json.dumps({'caption': cap.get_text(' ',strip=True) if cap else '', 'rows': rows_}, ensure_ascii=False)))
    # classify narrative vs other
    def is_narr(h2,h3):
        h = h2 or ''
        if STOP_SECTIONS.search(h) or STOP_SECTIONS.search(h3 or ''): return False
        if ATTACK_SECTION.search(h) or ATTACK_SECTION.search(h3 or ''): return False
        return True
    narr = [b[3] for b in blocks if b[0]=='text' and is_narr(b[1],b[2])]
    mitig = [b[3] for b in blocks if b[0]=='text' and re.match(r'mitigation', b[1] or '', re.I)]
    alltext = '\n'.join(b[3] for b in blocks if b[0] in ('text','heading'))
    tables = [json.loads(b[3]) for b in blocks if b[0]=='table']
    tabletext = '\n'.join(' | '.join(r) for t in tables for r in t['rows'])
    full = alltext + '\n' + tabletext
    tids_all = sorted(set(re.findall(r'\bT\d{4}(?:\.\d{3})?\b', full)))
    tids_tables = sorted(set(re.findall(r'\bT\d{4}(?:\.\d{3})?\b', tabletext)))
    tids_narr = sorted(set(re.findall(r'\bT\d{4}(?:\.\d{3})?\b', '\n'.join(narr))))
    cves = sorted(set(re.findall(r'CVE-\d{4}-\d{4,7}', full)))
    h2s = []
    for b in blocks:
        if b[0]=='heading' and b[1]==b[3] and b[3] not in h2s: h2s.append(b[3])
    narr_text='\n\n'.join(narr)
    rec = dict(case_id=cid.upper(), title=title, release_date=meta.get('Release Date',''), alert_code=meta.get('Alert Code',''),
               url=f'https://www.cisa.gov/news-events/cybersecurity-advisories/{cid}',
               words_total_text=words(alltext), words_narrative=words(narr_text), words_mitigations=words('\n'.join(mitig)),
               n_tables=len(tables), attack_ids_all=tids_all, attack_ids_tables=tids_tables, attack_ids_in_narrative=tids_narr,
               cves=cves, h2=h2s,
               sha256_narrative=hashlib.sha256(narr_text.encode('utf-8')).hexdigest())
    rows.append(rec)
    json.dump({'meta':rec,'blocks':blocks}, open(os.path.join(out,cid+'.json'),'w'), ensure_ascii=False, indent=1)
    open(os.path.join(out,cid+'_narrative.txt'),'w').write(narr_text)
json.dump(rows, open(os.path.join(out,'_summary.json'),'w'), ensure_ascii=False, indent=1)
for r in rows:
    print(f"{r['case_id']:10} {r['release_date']:20} narr={r['words_narrative']:5} total={r['words_total_text']:5} tbl={r['n_tables']:2} T={len(r['attack_ids_tables']):3} CVE={len(r['cves']):2} | {r['title'][:95]}")
