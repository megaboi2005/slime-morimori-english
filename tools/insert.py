"""Build the English ROM: patch font glyphs, re-encode translated dialog, relocate it, fix pointers.

usage: python tools/insert.py [in.gba] [out.gba]
Inputs: script/ja.json (dump), script/en.json (translations), script/names.json (name plates).
Messages without a translation keep their original Japanese bytes and pointer.
"""
import json, os, re, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from script import load_table
from translate import PAGE_BREAK
from credits import parse as credits_parse, credit_messages
import nameplate
import gfxpatch
from font import ranges, LIMITS

MAX_W = 176          # px per line; speech bubble clips at ~180 (verified in emulator)
MAX_LINES = 2        # lines per speech box (verified in emulator)
HERO_W = 48          # assumed width of the player's name
FREE_START = 0x7d2000
GFX_START = 0xc00000   # graphics area in the expanded ROM

# Dialog-font slots that are Japanese-only and get redrawn as missing ASCII glyphs.
# 3 = ink, 2 = shade, 1 = light, ' ' = transparent. Rows not listed are blank.
NEW_GLYPHS = {
    ',': (0x12, {12: " @@ ", 13: " @@ ", 14: " #@ ", 15: " @  "}),
    "'": (0x13, {3: " @@ ", 4: " @@ ", 5: " #@ ", 6: " @  "}),
    ':': (0x15, {7: " @@  ", 8: " @@  ", 12: " @@  ", 13: " @@  "}),
    '-': (0x1e, {9: "@@@@@ ", 10: "##### "}),
    '/': (0x1f, {3: "    @#", 4: "    @ ", 5: "   #@ ", 6: "   @# ", 7: "   @  ", 8: "  #@  ",
                 9: "  @#  ", 10: "  @   ", 11: " #@   ", 12: " @#   ", 13: " @    ", 14: "#@    "}),
}
# (original offset, pointer locations, English). Leading spaces are where the game draws numbers.
MISC = [
    (0x713f08, [0x73840c], 'Ok\nNo'),        # choice lines are ~22px; 'Yes' overflows
    (0x713f0f, [0x738490], 'Easy\nNormal\nHard\nQuit'),
    (0x713f27, [0x7384f0], 'Match\nPractice\nQuit'),
    (0x713f35, [0xc5e04], " Hooly set\n  to beat!\n  Hurry!"),   # lines must stay under ~75px
    (0x713f52, [0xc6338], 'Best time\n    sec\nThis time\n    sec'),
    (0x713f73, [0xc67b4], 'New record!'),
    (0x713f8e, [0x98548], 'No adventure log.'),
]
STAFFROLL_TABLE, STAFFROLL_COUNT = 0x557a30, 20   # second pointer table to credits messages
DEFAULT_NAME_OFFS = [0x714091, 0x714096]   # two 4-glyph copies of the default hero name スラリン
PUNCT = {' ': 0x1d, '.': 0x10, '!': 0x17, '?': 0x94, '~': 0x95, '(': 0x22, ')': 0x23, '"': 0x16}
CTRL_BYTES = {'wait': b'\x07', 'end': b'\x08', 'clear': b'\x04', 'line': b'\x03', 'waitsnd': b'\x09',
              'var': b'\x0b', 'e': b'\x0e'}


def glyph_width(code, rom_ranges):
    i = next((k for k, l in enumerate(LIMITS) if code < l), 9)
    return rom_ranges[i][2]


def patch_font(rom):
    rs = ranges(rom)
    for ch, (code, rows) in NEW_GLYPHS.items():
        i = next((k for k, l in enumerate(LIMITS) if code < l), 9)
        p, first, w, bpg = rs[i]
        bits = []
        for r in range(16):
            row = rows.get(r, '').ljust(w)[:w]
            bits += [{' ': 0, '.': 1, '#': 2, '@': 3}[c] for c in row]
        data = bytes((bits[k] << 6) | (bits[k + 1] << 4) | (bits[k + 2] << 2) | bits[k + 3] for k in range(0, len(bits), 4))
        assert len(data) == bpg
        o = p + (code - first) * bpg
        rom[o:o + bpg] = data


def char_map(tbl):
    m = {}
    for code, s in sorted(tbl.items()):
        if len(s) == 1 and s.isascii() and s.isalnum() and s not in m: m[s] = code
    m.update(PUNCT)
    for ch, (code, _) in NEW_GLYPHS.items(): m[ch] = code
    return m


def code_bytes(code):
    return bytes([code]) if code < 0x100 else bytes([1, code - 0x100])


NUM_W = 14   # room left for an inline {0d:xx} number (up to 3 digits)


class Encoder:
    def __init__(self, rom, tbl, names):
        self.rs = ranges(rom)
        self.cmap = char_map(tbl)
        self.inv = {}
        for code, s in tbl.items(): self.inv.setdefault(s, code)
        self.names = names
        self.plate_len = 0

    def width(self, word):
        w = 0
        for t in re.findall(r'\[HERO\]|<c[0-9a-f]{2}>|</c>|\{[^}]*\}|.', word):
            if t == '[HERO]': w += HERO_W
            elif t.startswith('{'): w += NUM_W if t.startswith('{0d:') else 0
            elif t.startswith('<'): continue
            elif t in self.cmap: w += glyph_width(self.cmap[t], self.rs)
        return w

    def text_bytes(self, s):
        out = bytearray()
        for t in re.findall(r'\[HERO\]|<c[0-9a-f]{2}>|</c>|\{[^}]*\}|.', s):
            if t == '[HERO]': out += b'\x0e'
            elif t.startswith('{'): out += self.raw_bytes(t)   # inline control code, e.g. {0d:00} counter
            elif t == '</c>': out += b'\x0c\x00'
            elif t.startswith('<c'): out += bytes([0x0c, int(t[2:4], 16)])
            elif t in self.cmap: out += code_bytes(self.cmap[t])
        return bytes(out)

    def wrap(self, text):
        """Word-wrap into boxes of MAX_LINES lines. Returns list of boxes (list of lines)."""
        text = text.replace('...', '…').replace('&', 'and')
        words = text.split(' ')
        lines, cur = [], ''
        space = glyph_width(0x1d, self.rs)
        for w in words:
            w = w.replace('…', '...')
            if not w: continue
            trial = (cur + ' ' + w) if cur else w
            if cur and self.width(trial) > MAX_W:
                lines.append(cur); cur = w
            else:
                cur = trial
        if cur: lines.append(cur)
        return [lines[i:i + MAX_LINES] for i in range(0, len(lines), MAX_LINES)] or [['']]

    def page_bytes(self, text):
        # control codes kept at the start/end of a page ({name:..} speaker switches, {0a:xx} menus)
        m = re.fullmatch(r'((?:\{[^}]*\})*)(.*?)((?:\{[^}]*\})*)', text, re.S)
        if m.group(1) or m.group(3):
            if '{0a:' in m.group(3) and len(self.wrap(m.group(2))) > 1:
                print('  WARNING: menu prompt overflows one box:', m.group(2)[:60])
            return self.raw_bytes(m.group(1)) + self.page_bytes(m.group(2)) + self.raw_bytes(m.group(3))
        boxes = self.wrap(text)
        out = bytearray()
        for bi, box in enumerate(boxes):
            if bi: out += b'\x07\x08\x02'          # wait for button, then start a fresh box
            out += b'\x02'.join(self.text_bytes(l) for l in box)
        return bytes(out)

    def raw_bytes(self, s):
        """Encode a decoded control/Japanese chunk back to bytes (round-trips dump output)."""
        out = bytearray()
        for t in re.findall(r'\{[^}]*\}|St|Jr|.', s, re.S):   # St/Jr are single glyphs
            if t == '\n': out += b'\x02'
            elif t.startswith('{name:'):
                hx = t[6:-1]
                en = self.names.get(nameplate.decode(hx))
                plate = nameplate.encode(en) if en else bytes.fromhex(hx)
                # a mid-message speaker change only redraws as many tiles as the new name has:
                # pad with spaces so a longer previous name doesn't leave letters behind ("Big Bron")
                plate += nameplate.encode(' ') * (self.plate_len - len(plate))
                self.plate_len = max(self.plate_len, len(plate))
                out += b'\x05' + plate + b'\x05'
            elif t.startswith('{') and t[1:-1] in CTRL_BYTES: out += CTRL_BYTES[t[1:-1]]
            elif re.fullmatch(r'\{[0-9a-f]{2}:[0-9a-f]{2}\}', t): out += bytes([int(t[1:3], 16), int(t[4:6], 16)])
            elif re.fullmatch(r'\{[0-9a-f]{2,3}\}', t): out += code_bytes(int(t[1:-1], 16))
            elif t == ' ': out += b'\x1d'
            else: out += code_bytes(self.inv[t])
        return bytes(out)

    def message(self, ja, tr):
        """Rebuild one message from its Japanese source layout and the English pages."""
        self.plate_len = 0
        name = re.match(r'^\{name:[0-9a-f]+\}', ja)
        out = bytearray(self.raw_bytes(name.group()) if name else b'')
        body = ja[name.end():] if name else ja
        page = 0
        for part in PAGE_BREAK.split(body):
            if not part: continue
            if PAGE_BREAK.fullmatch(part):
                out += self.raw_bytes(part); continue
            txt = re.sub(r'\{0c:[0-9a-f]{2}\}|\{e\}', 'X', part).replace('\n', ' ').replace('「', '').replace('」', '')
            if not txt.strip() or re.fullmatch(r'(\{[^}]*\}|\s)*', txt):
                out += self.raw_bytes(part); continue
            lead = re.match(r'^[\n 「]*', part).group().count('\n')
            trail = re.search(r'[\n 」]*$', part).group().count('\n')
            out += b'\x02' * lead + self.page_bytes(tr['pages'][page]) + b'\x02' * trail
            page += 1
        assert page == len(tr['pages']), 'page count mismatch'
        return bytes(out) + b'\x00'


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else 'rocketslime.gba'
    dst = sys.argv[2] if len(sys.argv) > 2 else 'build/rocketslime_en.gba'
    rom = bytearray(open(src, 'rb').read())
    ja = json.load(open('script/ja.json', encoding='utf-8'))
    en_path = os.environ.get('EN_JSON', 'script/en.json')
    en = json.load(open(en_path, encoding='utf-8')) if os.path.exists(en_path) else {}
    names = json.load(open('script/names.json', encoding='utf-8')) if os.path.exists('script/names.json') else {}
    # reviewed corrections (tools/rev.py) override the machine translation
    from translate import to_pages
    ja_skel = {r['id']: to_pages(r['ja'])[0] for r in ja if not r['credits']}
    if os.path.exists('script/fixes.json'):
        for k, pages in json.load(open('script/fixes.json', encoding='utf-8')).items():
            if k in en: en[k] = dict(en[k], pages=pages)
            elif k in ja_skel: en[k] = {'skel': ja_skel[k], 'pages': pages, 'model': 'review'}
    tbl = load_table()
    patch_font(rom)
    enc = Encoder(rom, tbl, names)
    cur = FREE_START
    done = 0
    for r in ja:
        tr = en.get(r['id'])
        if r['credits'] or not tr or not tr['pages']: continue
        data = enc.message(r['ja'], tr)
        if cur + len(data) > len(rom):
            if len(rom) >= 0x1000000: sys.exit('out of space')
            rom += b'\x00' * (0x1000000 - len(rom))       # expand to 16 MB
            cur = max(cur, 0x800000)
        rom[cur:cur + len(data)] = data
        struct.pack_into('<I', rom, int(r['slot'], 16), 0x08000000 + cur)
        cur += len(data)
        done += 1
    # Graphics: raw re-encoded blocks live at 12 MB+, the game is redirected to them by a decompressor hook.
    if len(rom) < 0x1000000: rom += b'\x00' * (0x1000000 - len(rom))
    gcur = [GFX_START]
    def galloc(data):
        o = gcur[0]; rom[o:o + len(data)] = data; gcur[0] = (o + len(data) + 3) & ~3; return o
    redirects = {}
    redirects.update(gfxpatch.patch_save_menu(rom, enc.cmap, galloc))
    r2, sideloads = gfxpatch.patch_save_dialogs(rom, enc.cmap, galloc)
    redirects.update(r2)
    redirects.update(gfxpatch.patch_name_entry(rom, enc.cmap, galloc))
    redirects.update(gfxpatch.patch_tutorial(rom, galloc))
    redirects.update(gfxpatch.patch_pot_logo(rom, galloc))
    redirects.update(gfxpatch.patch_title(rom, galloc))
    gfxpatch.install_hook(rom, galloc, redirects, sideloads)
    # Small UI strings stored next to the font table, each with its pointer location(s).
    for src_off, refs, text in MISC:
        # These boxes render lines into consecutive tiles: each line must span as many 8px tiles
        # as the Japanese line did, so pad with spaces up to the original tile count.
        from script import decode
        jp_lines = decode(rom, src_off, tbl)[0].split('\n')
        en_lines = text.split('\n')
        space = glyph_width(0x1d, enc.rs)
        for i, l in enumerate(en_lines):
            jw = sum(glyph_width(enc.inv[c], enc.rs) for c in jp_lines[i] if c in enc.inv) if i < len(jp_lines) else 0
            jt = -(-jw // 8)
            while -(-enc.width(l) // 8) < jt: l += ' '
            en_lines[i] = l
        data = b'\x02'.join(enc.text_bytes(l) for l in en_lines) + b'\x00'
        rom[cur:cur + len(data)] = data
        for ref in refs:
            assert struct.unpack_from('<I', rom, ref)[0] == 0x08000000 + src_off
            struct.pack_into('<I', rom, ref, 0x08000000 + cur)
        cur += len(data)
    # Staff roll: keep each line's row marker, swap the text.
    if os.path.exists('script/credits_en.json'):
        cred = json.load(open('script/credits_en.json', encoding='utf-8'))
        for mid, slot, p in credit_messages(rom):
            if mid not in cred: continue
            lines, _ = credits_parse(rom, p, tbl)
            assert len(lines) == len(cred[mid]), mid
            data = b'\x02'.join(bytes([row, 0xff]) + enc.text_bytes(t) for (row, _), t in zip(lines, cred[mid])) + b'\x00'
            rom[cur:cur + len(data)] = data
            struct.pack_into('<I', rom, slot, 0x08000000 + cur)
            # the staff-roll routine (0x0807fc..) reads its own copy of these pointers
            for o in range(STAFFROLL_TABLE, STAFFROLL_TABLE + STAFFROLL_COUNT * 4, 4):
                if struct.unpack_from('<I', rom, o)[0] == 0x08000000 + p:
                    struct.pack_into('<I', rom, o, 0x08000000 + cur)
            cur += len(data)
    # Default hero name, replaced in place (same length).
    for o in DEFAULT_NAME_OFFS:
        assert rom[o:o + 4] == bytes([0x7c, 0x82, 0x49, 0x87])
        rom[o:o + 4] = enc.text_bytes('Rock')
    # header complement check
    rom[0xbd] = (-(sum(rom[0xa0:0xbd]) + 0x19)) & 0xff
    os.makedirs(os.path.dirname(dst) or '.', exist_ok=True)
    open(dst, 'wb').write(rom)
    print('inserted %d messages, script ends at 0x%x, rom %d MB -> %s' % (done, cur, len(rom) >> 20, dst))


if __name__ == '__main__':
    main()
