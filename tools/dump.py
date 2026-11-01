"""Dump all dialog to script/ja.json (one record per message pointer)."""
import sys, os, json, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from script import load_table, decode, messages
rom = open(sys.argv[1] if len(sys.argv) > 1 else 'rocketslime.gba', 'rb').read()
tbl = load_table()
out = []
unk = {}
for g, k, slot, p in messages(rom):
    text, end = decode(rom, p, tbl)
    credits = rom[p] < 0x10 and rom[p + 1] == 0xff
    for u in re.findall(r'\{([0-9a-f]{2,3})\}', text): unk[u] = unk.get(u, 0) + 1
    out.append({'id': '%03d-%03d' % (g, k), 'slot': hex(slot), 'offset': hex(p), 'size': end - p,
                'credits': credits, 'ja': text})
os.makedirs('script', exist_ok=True)
json.dump(out, open('script/ja.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
uniq = len({r['offset'] for r in out})
print('%d messages (%d unique), %d bytes; unknown codes: %s' % (len(out), uniq, sum(r['size'] for r in out if True), unk))
