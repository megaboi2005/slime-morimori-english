"""Render dialog boxes of a (patched) ROM message as PNG, using the game's own font + decoder."""
import sys, os, struct, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from font import glyph
from PIL import Image

def boxes(rom, p):
    """Split raw message into boxes of lines of glyph codes (approximation of the interpreter)."""
    bx, lines, cur = [], [], []
    i = p
    while True:
        b = rom[i]
        if b == 0: break
        if b == 5: i = rom.index(b'\x05', i + 1) + 1; continue
        if b == 1: cur.append(0x100 + rom[i + 1]); i += 2; continue
        if b == 2: lines.append(cur); cur = []; i += 1; continue
        if b == 8:
            lines.append(cur); bx.append([l for l in lines if l]); lines, cur = [], []
            i += 1
            if rom[i] == 2: i += 1
            continue
        if b in (0x0e,): cur += [0x8c, 0xcd, 0x5f]; i += 1; continue   # "Ame" stand-in for hero
        if b < 0x10: i += 2 if b in (6, 0xa, 0xc, 0xd) else 1; continue
        cur.append(b); i += 1
    lines.append(cur); bx.append([l for l in lines if l])
    return [b for b in bx if b]

def render(rom, p, out):
    bs = boxes(rom, p)
    im = Image.new('RGB', (224, 60 * len(bs)), (0, 0, 64))
    for bi, box in enumerate(bs):
        for li, line in enumerate(box):
            x = 8
            for c in line:
                w, rows = glyph(rom, c)
                for y in range(16):
                    for dx in range(w):
                        v = rows[y][dx]
                        if v: im.putpixel((x + dx, bi * 60 + 4 + li * 17 + y), [(0,0,0), (90,90,90), (170,170,170), (255,255,255)][v])
                x += w
            if x > 224 - 8: print('  overflow line', li, 'width', x - 8)
    im.resize((im.width * 3, im.height * 3), Image.NEAREST).save(out)

if __name__ == '__main__':
    rom = open(sys.argv[1], 'rb').read()
    slot = int(sys.argv[2], 16)
    p = struct.unpack_from('<I', rom, slot)[0] - 0x08000000
    render(rom, p, sys.argv[3])
