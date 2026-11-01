import sys,struct
d=open(sys.argv[1],'rb').read()
G="あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよらりるれろわをん"
def idx_g(s): return [G.index(c) for c in s]
def idx_u(s): return [ord(c) for c in s]
words={'すらいむ':'gojuon','もりもり':'gojuon','ありがとう':None,'すらいむ ':None}
tests=[('すらいむ',idx_g),('もりもり',idx_g),('すらいむ',idx_u),('もりもり',idx_u),('しっぽ',idx_u),('ありがとう',idx_u),('ありかとう',idx_g),('ほいみ',idx_g),('たいほう',idx_g)]
import array
w16=array.array('H',d[:len(d)//2*2])
for word,f in tests:
    v=f(word); diffs=[v[i+1]-v[i] for i in range(len(v)-1)]
    hits=[]
    for i in range(len(d)-len(v)):
        if d[i+1]-d[i]==diffs[0] and all(d[i+k+1]-d[i+k]==diffs[k] for k in range(len(diffs))):
            hits.append(('b',i,d[i]-v[0]))
    for off in (0,1):
        w=array.array('H',d[off:off+(len(d)-off)//2*2])
        for i in range(len(w)-len(v)):
            if w[i+1]-w[i]==diffs[0] and all(w[i+k+1]-w[i+k]==diffs[k] for k in range(len(diffs))):
                hits.append(('w',off+2*i,w[i]-v[0]))
    from collections import Counter
    c=Counter((h[0],h[2]) for h in hits)
    print(word,f.__name__,len(hits),c.most_common(5))
