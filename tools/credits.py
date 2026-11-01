"""Staff roll (dialog group 065): lines are `<row> FF <glyphs> [02]`, message ends with 00."""
import json, os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from script import load_table, messages

def parse(rom, p, tbl):
    """Return (list of (row, text), end offset)."""
    lines, i = [], p
    while rom[i] != 0:
        assert rom[i] < 0x10 and rom[i + 1] == 0xff, hex(i)
        row = rom[i]; i += 2; txt = ''
        while rom[i] not in (0, 2):
            if rom[i] == 1: txt += tbl.get(0x100 + rom[i + 1], '?'); i += 2
            else: txt += tbl.get(rom[i], '{%02x}' % rom[i]); i += 1
        lines.append((row, txt))
        if rom[i] == 2: i += 1
    return lines, i + 1

def credit_messages(rom):
    for g, k, slot, p in messages(rom):
        if rom[p] < 0x10 and rom[p + 1] == 0xff: yield '%03d-%03d' % (g, k), slot, p

if __name__ == '__main__':
    rom = open('rocketslime.gba', 'rb').read(); tbl = load_table()
    for mid, slot, p in credit_messages(rom):
        lines, e = parse(rom, p, tbl)
        print(mid, hex(p), e - p, lines)
