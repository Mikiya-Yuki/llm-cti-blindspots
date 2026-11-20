"""Consistency checks for answer keys against frozen inputs.
- every CVE ID in the input appears in the key, and vice versa
- schema fields present; attribution code valid
- heuristic list of capitalized/camel-case tokens near tool words that are NOT in the key (possible omissions, for human review)
Usage: python3 -I check_keys.py <inputs_dir> <keys_dir> <case ids...>"""
import sys, os, re, json
inp_dir, key_dir, cases = sys.argv[1], sys.argv[2], sys.argv[3:]
FIELDS=['authoring_agencies','actor_designations','attribution_statements','attribution_strength_code','malware_tools','vulnerabilities','affected_products_or_technologies','target_sectors','target_regions','named_victims','dates','notes']
TOOLCTX=re.compile(r'(malware|tool|backdoor|implant|loader|downloader|web ?shell|ransomware|utility|utilities|framework|RAT|script|binary|executable|software|variant|payload|dropper|beacon|tunnel)',re.I)
STOP=set('The This These Those They Their There Then When While Although However After Before During Since Until If In On At For From With Without Into Onto Upon Over Under About Above Below Between Among Through Throughout Against Within Across Per Via Once Each Every Some Many Most Other Such Both Either Neither Also Additionally Furthermore Moreover Notably Further Finally First Second Third Initial Note Table Figure Appendix Summary Technical Details Mitigations FBI CISA NSA US U.S. United States Microsoft Windows Linux PowerShell Active Directory IP DNS HTTP HTTPS TCP UDP SSH RDP VPN SMB LDAP API ID IDs MFA OT IT PLC PLCs HMI HMIs CVE CVEs TTPs TTP IOCs IOC APT APTs PRC DPRK IRGC GRU SVR FSB MSS RGB'.split())
for c in cases:
    t=open(os.path.join(inp_dir,c+'_input.txt'),encoding='utf-8').read()
    kp=os.path.join(key_dir,c+'_key.json')
    if not os.path.exists(kp): print(c.upper(),'NO KEY'); continue
    k=json.load(open(kp,encoding='utf-8'))
    miss=[f for f in FIELDS if f not in k]
    cve_in=set(re.findall(r'CVE-\d{4}-\d{4,7}',t)); cve_key=set(v.get('cve','') for v in k.get('vulnerabilities',[]))
    names=' '.join([x.get('name','') for x in k.get('malware_tools',[])+k.get('affected_products_or_technologies',[])+k.get('actor_designations',[])+k.get('named_victims',[])]).lower()
    cand=set()
    for s in re.split(r'(?<=[\.\!\?:])\s+',t):
        if not TOOLCTX.search(s): continue
        for m in re.finditer(r'\b([A-Z][A-Za-z0-9]*[A-Z0-9][A-Za-z0-9\.\-]*|[A-Z][a-z]+[A-Z][A-Za-z0-9]+|[A-Za-z0-9\-]+\.(?:exe|dll|ps1|bat|vbs|sh|py|jsp|aspx|php))\b',s):
            w=m.group(1)
            if w in STOP or len(w)<3 or w.isdigit(): continue
            if w.lower() not in names: cand.add(w)
    print(f"{c.upper()}: missing_fields={miss} code={k.get('attribution_strength_code')} | CVE input={len(cve_in)} key={len(cve_key)} not_in_key={sorted(cve_in-cve_key)} not_in_input={sorted(cve_key-cve_in)}")
    print('   possible tool/product tokens not in key (review):', sorted(cand)[:60])
