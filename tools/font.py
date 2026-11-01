"""Dialog VWF font: glyph ranges grouped by pixel width (see FUN_080971ec / FUN_08096cdc)."""
import struct
RANGES_OFF = 0x713eb8   # 10 x {u32 ptr, u16 first_code, u8 width, u8 bytes_per_glyph}
LIMITS = [0x14,0x19,0x24,0x3e,0x67,0x98,0xcf,0x10d,0x142]

def ranges(rom):
    out=[]
    for i in range(10):
        p,first,w,bpg=struct.unpack_from('<IHBB',rom,RANGES_OFF+8*i)
        out.append((p-0x08000000,first,w,bpg))
    return out

def glyph(rom,code):
    """Return (width, 16 rows of pixel values 0-3)."""
    rs=ranges(rom)
    i=next((k for k,l in enumerate(LIMITS) if code<l),9)
    p,first,w,bpg=rs[i]
    o=p+(code-first)*bpg
    px=[]
    bits=[]
    for b in rom[o:o+bpg]:
        for s in (6,4,2,0): bits.append((b>>s)&3)
    rows=[bits[r*w:(r+1)*w] for r in range(16)]
    return w,rows
