"""Render a decompressed 4bpp tileset as a labeled grayscale sheet: python tools/sheet.py SRC_HEX out_prefix [rows_per_image]"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gfxcomp import decompress
from PIL import Image, ImageDraw
rom = open('rocketslime.gba', 'rb').read()
out, _ = decompress(rom, int(sys.argv[1], 16))
per = int(sys.argv[3]) if len(sys.argv) > 3 else 16
W, Z = 32, 3
n = len(out) // 32
rows = n // W
for part in range(0, rows, per):
    im = Image.new('RGB', (40 + W * 8 * Z, per * 8 * Z), 'white'); dr = ImageDraw.Draw(im)
    for t in range(part * W, min(n, (part + per) * W)):
        r, c = t // W - part, t % W
        for y in range(8):
            for x in range(8):
                b = out[t * 32 + y * 4 + x // 2]; v = (b >> 4) if x & 1 else b & 15
                g = 255 - v * 16
                dr.rectangle([40 + (c * 8 + x) * Z, (r * 8 + y) * Z, 40 + (c * 8 + x) * Z + Z - 1, (r * 8 + y) * Z + Z - 1], fill=(g, g, g) if v else (255, 230, 230))
        if c == 0: dr.text((2, r * 8 * Z + 6), str(t // W), fill=(0, 0, 255))
    for c in range(0, W + 1, 4): dr.line([40 + c * 8 * Z, 0, 40 + c * 8 * Z, im.height], fill=(0, 160, 0))
    im.save('%s_%02d.png' % (sys.argv[2], part // per))
