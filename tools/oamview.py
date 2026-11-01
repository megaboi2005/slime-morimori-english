"""Render sprites from OAM/VRAM/palette dumps with index labels: python tools/oamview.py DIR out.png"""
import sys, os, struct
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from oamdump import sprites
from PIL import Image, ImageDraw
d = sys.argv[1]
oam = open(d + 'oam.bin', 'rb').read(); vram = open(d + 'vram.bin', 'rb').read(); pal = open(d + 'pal.bin', 'rb').read()
Z = 3
im = Image.new('RGB', (240 * Z, 160 * Z), (40, 40, 40)); dr = ImageDraw.Draw(im)
for s in reversed(sprites(oam)):
    for ty in range(s['h'] // 8):
        for tx in range(s['w'] // 8):
            t = s['tile'] + ty * (s['w'] // 8) + tx
            for y in range(8):
                for x in range(8):
                    b = vram[0x10000 + t * 32 + y * 4 + x // 2]; v = (b >> 4) if x & 1 else b & 15
                    if not v: continue
                    c = struct.unpack_from('<H', pal, 0x200 + (s['pal'] * 16 + v) * 2)[0]
                    X = s['x'] + (s['w'] - 1 - (tx * 8 + x) if s['hf'] else tx * 8 + x)
                    Y = s['y'] + (s['h'] - 1 - (ty * 8 + y) if s['vf'] else ty * 8 + y)
                    if 0 <= X < 240 and 0 <= Y < 160:
                        dr.rectangle([X * Z, Y * Z, X * Z + Z - 1, Y * Z + Z - 1], fill=((c & 31) << 3, ((c >> 5) & 31) << 3, ((c >> 10) & 31) << 3))
for s in sprites(oam):
    dr.rectangle([s['x'] * Z, s['y'] * Z, (s['x'] + s['w']) * Z - 1, (s['y'] + s['h']) * Z - 1], outline=(255, 0, 0))
    dr.text((s['x'] * Z + 2, s['y'] * Z + 1), str(s['i']), fill=(255, 255, 0))
im.save(sys.argv[2])
