"""Dump / parse Slime MoriMori dialog script.

Message format (from decompiled interpreter FUN_08095f34 @ 0x08095f34):
  00        end of message
  01 xx     glyph 0x100+xx (kanji etc.)
  02        newline                 03  next line (scroll)
  04        clear window            05 t.. 05  speaker name plate (tile indices)
  06 xx     set text speed          07  wait for button
  08        end-of-page flag        09  wait + sound
  0A xx     window/choice mode      0B  insert variable (FUN_08099a04)
  0C xx     text color              0D xx  unknown param
  0E        unknown                 >=10 glyph (see dialog.tbl)
"""
import struct, os
HERE = os.path.dirname(os.path.abspath(__file__))
MASTER = 0x713cc4      # 125 x u32 -> per-scene message pointer tables
MASTER_COUNT = 125
SLOTS_START, SLOTS_END = 0x71181c, 0x713cc4
ARGS = {0x1: 1, 0x6: 1, 0xA: 1, 0xC: 1, 0xD: 1}
CTRL = {0x2: 'n', 0x3: 'line', 0x4: 'clear', 0x7: 'wait', 0x8: 'end', 0x9: 'waitsnd', 0xB: 'var', 0xE: 'e'}

def load_table(path=os.path.join(HERE, 'dialog.tbl')):
    t = {}
    for line in open(path, encoding='utf-8'):
        if line.startswith('#') or '=' not in line: continue
        k, v = line.rstrip('\n').split('=', 1)
        t[int(k, 16) if len(k) == 2 else 0x100 + int(k[2:], 16)] = v
    return t

def decode(rom, p, tbl):
    """Decode message at file offset p. Returns (text, end_offset)."""
    out = []
    i = p
    while True:
        b = rom[i]
        if b == 0: return ''.join(out), i + 1
        if b == 5:
            j = rom.index(b'\x05', i + 1)
            out.append('{name:%s}' % rom[i + 1:j].hex()); i = j + 1; continue
        if b == 1:
            c = 0x100 + rom[i + 1]
            out.append(tbl.get(c, '{%03x}' % c)); i += 2; continue
        if b < 0x10:
            if b in ARGS: out.append('{%02x:%02x}' % (b, rom[i + 1])); i += 2
            else: out.append('{%s}' % CTRL.get(b, '%02x' % b)) if b != 2 else out.append('\n'); i += 1
            continue
        out.append(tbl.get(b, '{%02x}' % b)); i += 1

def u32(rom, o): return struct.unpack_from('<I', rom, o)[0]

def messages(rom):
    """Yield (group, index, slot_offset, text_offset) for every non-null message pointer."""
    starts = [u32(rom, MASTER + 4 * g) - 0x08000000 for g in range(MASTER_COUNT)]
    bounds = sorted(set(starts + [SLOTS_END]))
    for g, st in enumerate(starts):
        end = bounds[bounds.index(st) + 1]
        for k, slot in enumerate(range(st, end, 4)):
            v = u32(rom, slot)
            if v: yield g, k, slot, v - 0x08000000
