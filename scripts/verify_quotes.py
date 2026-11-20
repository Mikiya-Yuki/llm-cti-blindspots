"""Verify that every 'quote' field in an answer-key JSON appears verbatim (whitespace-normalized) in the case input text.
Usage: python3 -I verify_quotes.py <input_txt> <answer_key_json>"""
import sys, json, re
norm=lambda s: re.sub(r'\s+',' ',s.replace('’',"'").replace('‘',"'").replace('“','"').replace('”','"')).strip()
text=norm(open(sys.argv[1],encoding='utf-8').read())
key=json.load(open(sys.argv[2],encoding='utf-8'))
bad=[]; n=0
def walk(o,path):
    global n
    if isinstance(o,dict):
        for k,v in o.items():
            if k=='quote' and isinstance(v,str):
                n+=1
                if norm(v) not in text: bad.append((path,v[:120]))
            else: walk(v,path+'/'+k)
    elif isinstance(o,list):
        for i,v in enumerate(o): walk(v,f'{path}[{i}]')
walk(key,'')
print(f'{sys.argv[2].split("/")[-1]}: {n} quotes checked, {len(bad)} not found')
for p,q in bad: print('  MISSING', p, '|', q)
