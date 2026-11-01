"""Contact sheet of compressed tile sets: python tools/contact.py ranked.json start count out.png"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gfxcomp import decompress
from PIL import Image, ImageDraw
rom = open('rocketslime.gba', 'rb').read()
lst = json.load(open(sys.argv[1]))[int(sys.argv[2]):int(sys.argv[2]) + int(sys.argv[3])]
COLS, TW, MAXR = 2, 32, 12
cells = []
for o, sz in lst:
    out, _ = decompress(rom, o); n = min(len(out) // 32, TW * MAXR)
    im = Image.new('L', (TW * 8, MAXR * 8), 255)
    for t in range(n):
        for i in range(64):
            v = (out[t * 32 + i // 2] >> (4 * (i & 1))) & 15
            if v: im.putpixel(((t % TW) * 8 + i % 8, (t // TW) * 8 + i // 8), 255 - 12 - v * 14)
    cells.append((o, im))
W, H = TW * 8 + 10, MAXR * 8 + 14
sheet = Image.new('RGB', (COLS * W, ((len(cells) + COLS - 1) // COLS) * H), 'white'); dr = ImageDraw.Draw(sheet)
for k, (o, im) in enumerate(cells):
    x, y = (k % COLS) * W, (k // COLS) * H
    sheet.paste(im, (x, y + 12)); dr.text((x + 2, y), hex(o), fill=(255, 0, 0))
sheet.resize((sheet.width * 2, sheet.height * 2), Image.NEAREST).save(sys.argv[4])
