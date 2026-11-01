"""List visible sprites from an OAM dump: python tools/oamdump.py oam.bin"""
import struct, sys
SZ = {(0,0):(8,8),(0,1):(16,16),(0,2):(32,32),(0,3):(64,64),(1,0):(16,8),(1,1):(32,8),(1,2):(32,16),(1,3):(64,32),
      (2,0):(8,16),(2,1):(8,32),(2,2):(16,32),(2,3):(32,64)}
def sprites(oam):
    out = []
    for i in range(128):
        a0, a1, a2 = struct.unpack_from('<HHH', oam, i * 8)
        if (a0 >> 8) & 3 == 2: continue
        y = a0 & 0xff; x = a1 & 0x1ff
        if y >= 160 or x >= 240: continue
        w, h = SZ[(a0 >> 14, a1 >> 14)]
        out.append(dict(i=i, x=x, y=y, w=w, h=h, tile=a2 & 0x3ff, pal=a2 >> 12, hf=(a1 >> 12) & 1, vf=(a1 >> 13) & 1))
    return out
if __name__ == '__main__':
    for s in sprites(open(sys.argv[1], 'rb').read()): print(s)
