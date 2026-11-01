import sys
from PIL import Image
d=open(sys.argv[1],'rb').read()
off=int(sys.argv[2],16); size=int(sys.argv[3],16); bpp=int(sys.argv[4]); out=sys.argv[5]
mode=sys.argv[6] if len(sys.argv)>6 else 'tile'
TW=32
data=d[off:off+size]
if bpp==4:
    ntiles=len(data)//32
    rows=(ntiles+TW-1)//TW
    im=Image.new('L',(TW*8,rows*8))
    px=im.load()
    for t in range(ntiles):
        tx,ty=(t%TW)*8,(t//TW)*8
        for y in range(8):
            for x in range(8):
                b=data[t*32+y*4+x//2]; v=(b>>4) if x&1 else b&15
                px[tx+x,ty+y]=v*17
elif bpp==1:
    w=int(mode) if mode.isdigit() else 8  # glyph width in bits (8 or 16)
    bpr=w//8; gh=int(sys.argv[7]) if len(sys.argv)>7 else 16
    gs=bpr*gh; n=len(data)//gs; GW=32
    rows=(n+GW-1)//GW
    im=Image.new('L',(GW*w,rows*gh))
    px=im.load()
    for g in range(n):
        gx,gy=(g%GW)*w,(g//GW)*gh
        for y in range(gh):
            for xb in range(bpr):
                b=data[g*gs+y*bpr+xb]
                for x in range(8):
                    px[gx+xb*8+x,gy+y]=255 if b&(0x80>>x) else 0
im=im.resize((im.width*2,im.height*2),Image.NEAREST)
im.save(out)
