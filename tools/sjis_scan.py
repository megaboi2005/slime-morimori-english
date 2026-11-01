import sys,re
d=open(sys.argv[1],'rb').read()
# find runs of valid Shift-JIS double-byte kana/kanji, length >= 4 chars
pat=re.compile(rb'(?:[\x81-\x9f\xe0-\xef][\x40-\x7e\x80-\xfc]|[\x20-\x7e]){6,}')
n=0;tot=0
for m in pat.finditer(d):
    s=m.group()
    if sum(1 for b in s if b>=0x81)<6: continue
    try: t=s.decode('shift_jis')
    except: continue
    if not re.search('[぀-ヿ]{3}',t): continue
    tot+=1
    if n<40: print(hex(m.start()),t[:60]); n+=1
print('total',tot)
