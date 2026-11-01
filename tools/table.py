H="あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよらりるれろわをんぁぃぅぇぉゃゅょっ"
K="アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲンァィゥェォャュョッ"
HV="がぎぐげござじずぜぞだぢづでどばびぶべぼ"
KV="ガギグゲゴザジズゼゾダヂヅデドバビブベボ"
P="ぱぴぷぺぽパピプペポ"
T={}
for i,c in enumerate("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"): T[0x20+i]=c
for i,c in enumerate(H): T[0x44+i]=c
for i,c in enumerate(K): T[0x7B+i]=c
for i,c in enumerate(HV): T[0xC0+i]=c
for i,c in enumerate(KV): T[0xD4+i]=c
for i,c in enumerate(P): T[0xE8+i]=c
T[0x1f]='　'; T[0xb4]='ー'
def dec(bs):
    return ''.join(T.get(b,'[%02x]'%b) for b in bs)
