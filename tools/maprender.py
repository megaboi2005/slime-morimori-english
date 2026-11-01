"""Render compressed tilemaps with a compressed tileset: python tools/maprender.py TILES_HEX PAL_BIN out_prefix MAP_HEX..."""
import sys, os, struct
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gfxcomp import decompress
from PIL import Image, ImageDraw
rom = open('rocketslime.gba', 'rb').read()
tiles, _ = decompress(rom, int(sys.argv[1], 16))
pal = open(sys.argv[2], 'rb').read()
def col(i, p):
    c = struct.unpack_from('<H', pal, (p * 16 + i) * 2)[0]; return ((c & 31) << 3, ((c >> 5) & 31) << 3, ((c >> 10) & 31) << 3)
for mh in sys.argv[4:]:
    m, _ = decompress(rom, int(mh, 16))
    hw = struct.unpack('<%dH' % (len(m) // 2), m)
    rows = (len(hw) + 31) // 32; Z = 3
    im = Image.new('RGB', (32 * 8 * Z + 24, rows * 8 * Z), (40, 40, 40)); dr = ImageDraw.Draw(im)
    for i, e in enumerate(hw):
        t, hf, vf, p = e & 0x3ff, (e >> 10) & 1, (e >> 11) & 1, e >> 12
        if t * 32 + 32 > len(tiles): continue
        for y in range(8):
            for x in range(8):
                b = tiles[t * 32 + y * 4 + x // 2]; v = (b >> 4) if x & 1 else b & 15
                if not v: continue
                X = (i % 32) * 8 + (7 - x if hf else x); Y = (i // 32) * 8 + (7 - y if vf else y)
                dr.rectangle([24 + X * Z, Y * Z, 24 + X * Z + Z - 1, Y * Z + Z - 1], fill=col(v, p))
    for r in range(rows): dr.text((2, r * 8 * Z + 4), str(r), fill=(255, 255, 0))
    for c in range(0, 33, 4): dr.line([24 + c * 8 * Z, 0, 24 + c * 8 * Z, im.height], fill=(0, 120, 0))
    im.save('%s_%s.png' % (sys.argv[3], mh))
