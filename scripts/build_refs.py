"""Build per-case model input (narrative with inline ATT&CK IDs removed) and ATT&CK reference sets.
Usage: python3 -I build_refs.py <parsed_dir> <attack_index.json> <out_dir> <case ids...>"""
import sys, os, re, json, hashlib
pdir, idxp, out = sys.argv[1], sys.argv[2], sys.argv[3]
cases = sys.argv[4:]
idx = json.load(open(idxp))
os.makedirs(out, exist_ok=True)
STOP = re.compile(r'^(mitigations?|recommendations|validate security controls|security controls|resources|references|acknowledg|disclaimer|version history|appendix|indicators of compromise|contact|reporting|purpose|notes|works cited|footnotes|detection|incident response|mitre att&ck|mitre d3fend|trademark|dprk rewards|log4shell|web shell malware|endpoint activity|command line activity|packing|additional mitigation|network defenders|device manufacturers|software manufacturers|sigma rules|yara rules|open source yara|hunting guidance)', re.I)
ID_BR = re.compile(r'\s*[\[\(]\s*((?:T\d{4}(?:\.\d{3})?)(?:\s*[,;/]\s*T\d{4}(?:\.\d{3})?)*)\s*[\]\)]')
ID_ANY = re.compile(r'\bT\d{4}(?:\.\d{3})?\b')
WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9'\-\.]*")
summary=[]
for c in cases:
    d = json.load(open(os.path.join(pdir, c + '.json')))
    blocks = d['blocks']
    narr_paras=[]; table_ids={}; stopped=False
    for kind,h2,h3,content in blocks:
        hh = (h2 or '')
        if kind=='text':
            if STOP.search(hh) or STOP.search(h3 or ''): continue
            narr_paras.append(dict(h2=h2,h3=h3,text=content))
        elif kind=='table':
            t=json.loads(content)
            cap=(t.get('caption') or '')
            hdr=' '.join(t['rows'][0]) if t['rows'] else ''
            is_attack = bool(re.search(r'att&ck|reconnaissance|resource development|initial access|execution|persistence|privilege escalation|defense evasion|stealth|defense impairment|credential access|discovery|lateral movement|collection|command and control|exfiltration|impact', cap+' '+hh, re.I)) and ('ATT&CK' in (hh+cap).upper() or 'Technique' in hdr)
            if c=='aa24-190a' and 'Historical' in hh: is_attack=False
            if is_attack:
                for r in t['rows']:
                    rowtxt=' | '.join(r)
                    for m in ID_ANY.findall(rowtxt):
                        table_ids.setdefault(m, rowtxt[:300])
    # inline ids with evidence
    inline={}
    clean_paras=[]
    for i,p in enumerate(narr_paras):
        ids = ID_ANY.findall(p['text'])
        for tid in ids:
            inline.setdefault(tid, []).append(i)
        cleaned = ID_BR.sub('', p['text'])
        cleaned = re.sub(r'\s*\[\s*(?:S|G|TA|M|C|DS)\d{4}\s*\]', '', cleaned)   # MITRE software/group/tactic/mitigation IDs
        cleaned = re.sub(r'\s*\[\s*\d{1,3}\s*\]', '', cleaned)                     # numeric citation markers
        if re.match(r'^(Download the PDF version|For a downloadable copy of IOCs|Download the STIX|For a downloadable list of IOCs)', cleaned, re.I):
            continue
        cleaned = re.sub(r'\s+([,.;:])', r'\1', cleaned)
        cleaned = ID_ANY.sub('', cleaned) if ID_ANY.search(cleaned) else cleaned
        cleaned = re.sub(r'\s{2,}',' ',cleaned).strip()
        if cleaned: clean_paras.append(cleaned)
    inp = '\n\n'.join(clean_paras)
    def status(t):
        r=idx.get(t)
        if not r: return dict(id=t,status='not_found')
        return dict(id=t,name=r['name'],domain=r['domain'],status=r['status'],replaced_by=r['replaced_by'])
    inl=[dict(**status(t), evidence_paragraphs=v, evidence=narr_paras[v[0]]['text'][:600]) for t,v in sorted(inline.items())]
    tab=[dict(**status(t), table_row=v) for t,v in sorted(table_ids.items())]
    rec=dict(case_id=c.upper(), input_words=len(WORD.findall(inp)), input_sha256=hashlib.sha256(inp.encode()).hexdigest(),
             inline_ids=inl, table_ids=tab,
             n_inline=len(inl), n_table=len(tab), n_union=len(set(inline)|set(table_ids)),
             n_inline_not_active=sum(1 for x in inl if x['status']!='active'), n_table_not_active=sum(1 for x in tab if x['status']!='active'))
    json.dump(rec, open(os.path.join(out, c+'_attack_ref.json'),'w'), ensure_ascii=False, indent=1)
    open(os.path.join(out, c+'_input.txt'),'w').write(inp)
    summary.append(rec)
    print(f"{c.upper():10} input_words={rec['input_words']:5} inline={rec['n_inline']:3} table={rec['n_table']:3} union={rec['n_union']:3} inline_not_active={rec['n_inline_not_active']} table_not_active={rec['n_table_not_active']} sha={rec['input_sha256'][:12]}")
    for x in inl+tab:
        if x['status']!='active': print('     non-active:', x['id'], x.get('name'), x['status'], '->', x.get('replaced_by'))
json.dump(summary, open(os.path.join(out,'_attack_summary.json'),'w'), ensure_ascii=False, indent=1)
