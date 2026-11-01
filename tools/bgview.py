"""Render GBA BG layers from VRAM/palette/IO dumps (text mode, 4bpp, 256x256 maps)."""
import struct, sys
from PIL import Image

def render_bg(vram, pal, io, n):
    c = struct.unpack_from('<H', io, 8 + 2 * n)[0]
    cb = ((c >> 2) & 3) * 0x4000; sb = ((c >> 8) & 31) * 0x800
    size = c >> 14
    w, h = [(32, 32), (64, 32), (32, 64), (64, 64)][size]
    im = Image.new('RGB', (w * 8, h * 8), (255, 0, 255))
    px = im.load()
    for ty in range(h):
        for tx in range(w):
            blk = (tx // 32) + (ty // 32) * (w // 32)
            e = struct.unpack_from('<H', vram, sb + blk * 0x800 + ((ty % 32) * 32 + tx % 32) * 2)[0]
            tile, hf, vf, pb = e & 0x3ff, (e >> 10) & 1, (e >> 11) & 1, e >> 12
            for y in range(8):
                for x in range(8):
                    b = vram[cb + tile * 32 + y * 4 + x // 2]
                    v = (b >> 4) if x & 1 else b & 15
                    if not v: continue
                    col = struct.unpack_from('<H', pal, (pb * 16 + v) * 2)[0]
                    rgb = ((col & 31) << 3, ((col >> 5) & 31) << 3, ((col >> 10) & 31) << 3)
                    px[tx * 8 + (7 - x if hf else x), ty * 8 + (7 - y if vf else y)] = rgb
    return im

if __name__ == '__main__':
    d = sys.argv[1]
    vram = open(d + 'vram.bin', 'rb').read(); pal = open(d + 'pal.bin', 'rb').read(); io = open(d + 'io.bin', 'rb').read()
    ims = [render_bg(vram, pal, io, n) for n in range(4)]
    sheet = Image.new('RGB', (sum(i.width for i in ims) + 30, max(i.height for i in ims)), 'white')
    x = 0
    for i in ims: sheet.paste(i, (x, 0)); x += i.width + 10
    sheet.save(d + 'bgs.png')
