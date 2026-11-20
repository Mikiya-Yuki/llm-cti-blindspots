"""Build an ID->status index for Enterprise+ICS ATT&CK STIX bundles.
Usage: python3 -I attack_index.py <enterprise.json> <ics.json> <out.json>"""
import sys, json
out={}
for path,dom in [(sys.argv[1],'enterprise'),(sys.argv[2],'ics')]:
    b=json.load(open(path))
    objs={o['id']:o for o in b['objects']}
    revoked_by={}
    for o in b['objects']:
        if o.get('type')=='relationship' and o.get('relationship_type')=='revoked-by':
            revoked_by[o['source_ref']]=o['target_ref']
    for o in b['objects']:
        if o.get('type')!='attack-pattern': continue
        ext=[r for r in o.get('external_references',[]) if r.get('source_name') in ('mitre-attack','mitre-ics-attack')]
        if not ext: continue
        tid=ext[0]['external_id']
        st='revoked' if o.get('revoked') else ('deprecated' if o.get('x_mitre_deprecated') else 'active')
        rep=None
        if st=='revoked' and o['id'] in revoked_by:
            t=objs.get(revoked_by[o['id']])
            if t:
                e2=[r for r in t.get('external_references',[]) if r.get('source_name') in ('mitre-attack','mitre-ics-attack')]
                rep=e2[0]['external_id'] if e2 else None
        tactics=[p['phase_name'] for p in o.get('kill_chain_phases',[])]
        rec=dict(id=tid,name=o['name'],domain=dom,status=st,replaced_by=rep,tactics=tactics,version=o.get('x_mitre_version'))
        # keep active over non-active if duplicate id appears
        if tid in out and out[tid]['status']=='active': continue
        out[tid]=rec
json.dump(out,open(sys.argv[3],'w'),indent=0)
from collections import Counter
print(len(out), Counter((v['domain'],v['status']) for v in out.values()))
