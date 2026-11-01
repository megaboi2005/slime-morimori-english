"""Graphics translation patches.

* Decompressor redirect hook: FUN_08098ac8(src, dst) is entered through an 8-byte trampoline that
  jumps to a hook in free space; the hook swaps `src` using a (old, new) table, replays the four
  overwritten instructions and returns. Any compressed block can then be replaced by a raw one.
* Save-menu command sprites (sheet 0x7a58dc, metasprite frames @0x7a64e8): English words are drawn
  with the dialog font in the game's outlined gradient style and the frames are re-laid out.
"""
import json, struct, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gfxcomp import decompress, encode_raw
from font import glyph

DECOMP = 0x098ac8
DECOMP_RESUME = 0x08098ad1          # 'mov r7, fp' after the replayed prologue (Thumb)


class Thumb:
    """Tiny Thumb assembler: raw halfwords plus label-resolved branches and literal loads."""
    def __init__(self, base): self.base, self.ops, self.labels, self.lits = base, [], {}, []
    def label(self, n): self.labels[n] = len(self.ops) * 2
    def h(self, *hw): self.ops += [('h', x) for x in hw]
    def b(self, cond, n): self.ops.append(('b', cond, n))       # cond None = always, 0 = EQ
    def bl(self, n): self.ops += [('blh', n), ('bll', n)]
    def ldr(self, rd, value): self.ops.append(('ldr', rd, value))
    def assemble(self):
        code_len = len(self.ops) * 2
        pool = (self.base + code_len + 3) & ~3
        lits = []
        out = []
        for i, op in enumerate(self.ops):
            pc = self.base + i * 2 + 4
            if op[0] == 'h': out.append(op[1])
            elif op[0] == 'b':
                off = (self.labels[op[2]] - (i * 2 + 4)) // 2
                out.append(0xE000 | (off & 0x7ff) if op[1] is None else 0xD000 | (op[1] << 8) | (off & 0xff))
            elif op[0] in ('blh', 'bll'):
                j = i if op[0] == 'blh' else i - 1
                off = self.labels[op[1]] - (j * 2 + 4)
                out.append(0xF000 | ((off >> 12) & 0x7ff) if op[0] == 'blh' else 0xF800 | ((off >> 1) & 0x7ff))
            else:
                if op[2] not in lits: lits.append(op[2])
                lit = pool + 4 * lits.index(op[2])
                out.append(0x4800 | (op[1] << 8) | ((lit - (pc & ~3)) // 4))
        code = struct.pack('<%dH' % len(out), *out)
        code += b'\0' * (pool - self.base - len(code))
        return code + b''.join(struct.pack('<I', v) for v in lits)


def build_hook(addr, redirect_table, side_table):
    """Hook entered from the trampoline with r0=src, r1=dst, lr=caller.
    side_table: (trigger_src, side_src, side_dst) u32 triples - decompress an extra block first.
    redirect_table: (old_src, new_src) pairs. Both 0-terminated."""
    a = Thumb(addr)
    a.ldr(2, 0x08000000 + side_table)
    a.label('side'); a.h(0x6813, 0x2B00); a.b(0, 'redir'); a.h(0x4283); a.b(0, 'doside'); a.h(0x320C); a.b(None, 'side')
    a.label('doside')
    a.h(0xB503, 0x6850, 0x6891)                 # push {r0,r1,lr}; ldr r0,[r2,#4]; ldr r1,[r2,#8]
    a.bl('redir')                               # decompress side block (returns here)
    a.h(0xBC07, 0x4696)                         # pop {r0,r1,r2}; mov lr,r2
    a.label('redir')
    a.h(0xB5F0, 0x4644, 0x464D, 0x4656)         # replayed prologue: push {r4-r7,lr}; mov r4-r6, r8-r10
    a.ldr(2, 0x08000000 + redirect_table)
    a.label('loop'); a.h(0x6813, 0x2B00); a.b(0, 'done'); a.h(0x4283); a.b(0, 'found'); a.h(0x3208); a.b(None, 'loop')
    a.label('found'); a.h(0x6850)               # ldr r0,[r2,#4]
    a.label('done'); a.ldr(2, DECOMP_RESUME); a.h(0x4710)
    return a.assemble()


def install_hook(rom, alloc, redirects, sideloads=()):
    """redirects: {old_offset: new_offset}; sideloads: [(trigger_offset, side_offset, vram_addr)]."""
    rt = b''.join(struct.pack('<II', 0x08000000 + o, 0x08000000 + n) for o, n in redirects.items()) + b'\0' * 8
    st = b''.join(struct.pack('<III', 0x08000000 + t, 0x08000000 + s_, d) for t, s_, d in sideloads) + b'\0' * 12
    r_off, s_off = alloc(rt), alloc(st)
    h_off = alloc(b'\0' * 160)
    hook = build_hook(h_off, r_off, s_off)
    assert len(hook) <= 160
    rom[h_off:h_off + len(hook)] = hook
    assert bytes(rom[DECOMP:DECOMP + 8]) == bytes.fromhex('f0b544464d465646'), 'unexpected decompressor prologue'
    rom[DECOMP:DECOMP + 8] = struct.pack('<HHI', 0x4A00, 0x4710, 0x08000000 + h_off + 1)


# ---------------------------------------------------------------- outlined sprite text

GRADIENT = [9, 9, 10, 10, 11, 11, 12, 12, 13, 13]   # body colour by row (top -> bottom), palettes 6/9
OUTLINE = 14


def render_word(rom, cmap, text):
    """Return (width, 16 rows of palette indices) for `text` in outlined gradient style."""
    cols = []
    for ch in text:
        w, g = glyph(rom, cmap[ch])
        ink = [[1 if g[y][x] >= 2 else 0 for x in range(w)] for y in range(16)]
        # trim glyph's right padding to 1px so words stay compact
        used = [x for x in range(w) if any(ink[y][x] for y in range(16))]
        right = (max(used) + 1) if used else 3
        for x in range(right): cols.append([ink[y][x] for y in range(16)])
        cols.append([0] * 16)
    width = len(cols) + 2
    mask = [[0] * width for _ in range(16)]
    for x, col in enumerate(cols):
        for y in range(16): mask[y][x + 1] = col[y]
    rows_used = [y for y in range(16) if any(mask[y])]
    top, bot = min(rows_used), max(rows_used)
    out = [[0] * width for _ in range(16)]
    for y in range(16):
        for x in range(width):
            if mask[y][x]:
                k = (y - top) * len(GRADIENT) // (bot - top + 1)
                out[y][x] = GRADIENT[k]
            elif any(0 <= y + dy < 16 and 0 <= x + dx < width and mask[y + dy][x + dx]
                     for dy in (-1, 0, 1) for dx in (-1, 0, 1)):
                out[y][x] = OUTLINE
    return width, out


SHEET = 0x7a58dc
FRAMES = 0x7a64e8
BLANK_TILE = 252
SIZE_BITS = {(32, 16): (1, 2), (16, 16): (0, 1), (8, 8): (0, 0), (64, 32): (1, 3)}
# frame ids per word (plain / highlighted animation frames), English text, and line-2 words in the same frame
SAVE_MENU_WORDS = {
    'Yes':       [1, 2, 3, 4, 5, 6, 7, 8],
    'No':        [9, 10, 11, 12, 13, 14, 15, 16],
    'Adventure': [17, 18, 19, 20, 21],
    'Copy':      [22, 23, 24, 25, 26],
    'Link':      [37, 38, 39, 40, 41],
    'Erase':     [42, 43, 44, 45, 46],
    'Help':      [47, 48, 49, 50, 51],
}
# two-line frames: Sleep Mode / Off and Sleep Mode / On
SAVE_MENU_TWO_LINE = {('Sleep Mode', 'On'): [27, 28, 29, 30, 31], ('Sleep Mode', 'Off'): [32, 33, 34, 35, 36]}


def patch_save_menu(rom, cmap, alloc):
    """Redraw the save-menu command sprites in English. Returns {old_src: new_src} redirects."""
    sheet = bytearray(decompress(rom, SHEET)[0])
    next_tile = [0]

    def put_word(text, single=False):
        """Draw text into fresh sprite cells; return (width, [(x_offset, cell_w, cell_h, tile)]).
        single=True puts the whole word in one 64x32 cell (for frames with a single piece)."""
        w, px = render_word(rom, cmap, text)
        cells, x = [], 0
        while x < w:
            cw, ch = (64, 32) if single else ((32 if w - x > 16 else 16), 16)
            t = next_tile[0]; next_tile[0] += cw // 8 * ch // 8
            assert next_tile[0] <= 220, 'sprite sheet full'
            for i in range(t, next_tile[0]): sheet[i * 32:i * 32 + 32] = b'\0' * 32
            for ty in range(2):
                for tx in range(cw // 8):
                    tile = t + ty * (cw // 8) + tx      # 1D mapping: row-major cells
                    for yy in range(8):
                        for xx in range(0, 8, 2):
                            def p(xo):
                                X = x + tx * 8 + xo
                                return px[ty * 8 + yy][X] if X < w else 0
                            sheet[tile * 32 + yy * 4 + xx // 2] = p(xx) | (p(xx + 1) << 4)
            cells.append((x, cw, ch, t)); x += cw
        return w, cells

    def write_frame(fid, lines):
        """lines: list of (width, cells, y_offset). Re-lays the frame's pieces; extra pieces -> blank."""
        f = FRAMES + (struct.unpack_from('<H', rom, FRAMES + fid * 2)[0] & ~1)
        cnt = rom[f]
        old_y = [struct.unpack_from('<H', rom, f + 2 + 6 * k)[0] & 0xff for k in range(cnt)]
        pal = struct.unpack_from('<H', rom, f + 6)[0] >> 12
        pieces = []
        for w, cells, y in lines:
            for x, cw, ch, t in cells: pieces.append((x - w // 2, y, cw, ch, t))
        assert len(pieces) <= cnt, 'frame %d has only %d pieces' % (fid, cnt)
        for k in range(cnt):
            if k < len(pieces):
                x, y, cw, ch, t = pieces[k]
                shape, size = SIZE_BITS[(cw, ch)]
                d = ((old_y[k] + 8 + 128) & 0xff) - 128       # original bounce offset of this piece
                wob = d if len(lines) == 1 and abs(d) <= 2 else 0
                a0 = ((y + wob) & 0xff) | (shape << 14)
            else:
                x, t, size = 0, BLANK_TILE, 0; a0 = 0xf8
            a1 = (x & 0xff) | (size << 14)
            struct.pack_into('<3H', rom, f + 2 + 6 * k, a0, a1, t | (pal << 12))

    for text, fids in SAVE_MENU_WORDS.items():
        min_pieces = min(rom[FRAMES + (struct.unpack_from('<H', rom, FRAMES + f * 2)[0] & ~1)] for f in fids)
        w, cells = put_word(text)
        if len(cells) > min_pieces:
            next_tile[0] -= sum(c[1] * c[2] // 64 for c in cells)
            w, cells = put_word(text, single=True)
        for fid in fids: write_frame(fid, [(w, cells, -8)])
    sleep = put_word('Sleep Mode')
    for (l1, l2), fids in SAVE_MENU_TWO_LINE.items():
        second = put_word(l2)
        for fid in fids: write_frame(fid, [(sleep[0], sleep[1], -15), (second[0], second[1], -1)])
    for t in range(BLANK_TILE, BLANK_TILE + 4): sheet[t * 32:t * 32 + 32] = b'\0' * 32
    return {SHEET: alloc(encode_raw(bytes(sheet)))}


# ---------------------------------------------------------------- save-menu dialog boxes (BG text)

SAVE_TILES = 0x751b90          # 1024-tile BG set of the file-select module (loaded to VRAM 0x06000000)
SAVE_PALS = 0x751ab0           # palette block: entry k -> BG palette k+4
BOX_BG = 0x0f5 | (0xb << 12)   # plain green interior cell
# map -> class (tile pool), title?, lines: (row, first_col, last_col, palette, background_index, text)
# {braces} mark highlighted (yellow, palette 7) words.
SAVE_DIALOGS = {
    0x7565bc: ('box', 'Warning!', [
        (3, 3, 26, 6, 8, "You're about to {erase}"),
        (5, 3, 26, 6, 8, 'an Adventure Log!'),
        (7, 3, 26, 6, 8, '{It can never be undone!}')]),
    0x756770: ('box', 'Warning!', [
        (3, 3, 26, 6, 8, 'Erase it anyway?')]),
    0x756a58: ('box', None, [
        (7, 3, 26, 6, 8, 'Sleep Mode {pauses the}'),
        (9, 3, 26, 6, 8, '{game to save power.}'),
        (11, 3, 26, 6, 8, 'Handy when you need'),
        (13, 3, 26, 6, 8, 'a short break.')]),
    0x756c58: ('box', None, [
        (7, 3, 26, 6, 8, 'With the setting {On},'),
        (9, 3, 26, 6, 8, 'Sleep Mode is always'),
        (11, 3, 26, 6, 8, 'available. {The screen}'),
        (13, 3, 26, 6, 8, "{goes dark}, but that's OK.")]),
    0x756e70: ('box', None, [
        (7, 3, 26, 6, 8, 'The Sleep Mode command:'),
        (9, 21, 26, 6, 8, ''),                        # SELECT+L+R icons stay in cols 5-20
        (11, 3, 26, 6, 8, '{Wake up} with the'),
        (13, 3, 26, 6, 8, '{same command}.')]),
    0x757030: ('box', None, [
        (7, 3, 26, 6, 8, "{Sleep Mode isn't a save!}"),
        (9, 3, 26, 6, 8, 'Power off while asleep'),
        (11, 3, 26, 6, 8, "and you'll {go back to}"),
        (13, 3, 26, 6, 8, '{your last save}. Careful!')]),
    0x756890: ('prompt', None, [
        (1, 4, 26, 9, 0, '<Sleep Mode command:'),
        (3, 4, 8, 9, 0, '>Turn'),
        (3, 9, 12, 9, 0, '>{On}'),                    # cols 9-12 are overwritten by piece 0x757778 when ON
        (3, 13, 14, 9, 0, '<?'),
        (3, 15, 24, 9, 0, ''),
        (11, 5, 14, 6, 8, 'Command'),
        (13, 3, 16, 6, 8, '(and to wake)')]),
    0x75651c: ('copy', None, [
        (2, 6, 15, 9, 0, '>Copy Log'),               # '>' = right-align; slot digit stays in cols 16-17
        (2, 18, 19, 9, 0, '?'),
        (4, 6, 17, 9, 0, '')]),
}


def _pal(rom, p):
    blk = decompress(rom, SAVE_PALS)[0]
    raw = blk[(p - 4) * 32:(p - 4) * 32 + 32]
    return [((c & 31), (c >> 5) & 31, (c >> 10) & 31) for c in struct.unpack('<16H', raw)]


def render_line(rom, cmap, text, bg):
    """Like render_word but keeps spaces, supports {highlight}; returns (width, rows, hl_columns)."""
    cols, hl, on = [], [], False
    for ch in text:
        if ch in '{}': on = ch == '{'; continue
        w, g = glyph(rom, cmap[ch])
        ink = [[1 if g[y][x] >= 2 else 0 for x in range(w)] for y in range(16)]
        used = [x for x in range(w) if any(ink[y][x] for y in range(16))]
        right = (max(used) + 1) if used else 3
        for x in range(right): cols.append([ink[y][x] for y in range(16)]); hl.append(on)
        cols.append([0] * 16); hl.append(on)
    width = len(cols) + 2
    mask = [[0] * width for _ in range(16)]
    for x, col in enumerate(cols):
        for y in range(16): mask[y][x + 1] = col[y]
    out = [[bg] * width for _ in range(16)]
    for y in range(16):
        for x in range(width):
            if mask[y][x]:
                out[y][x] = GRADIENT[min(len(GRADIENT) - 1, max(0, (y - 3) * len(GRADIENT) // 11))]
            elif any(0 <= y + dy < 16 and 0 <= x + dx < width and mask[y + dy][x + dx]
                     for dy in (-1, 0, 1) for dx in (-1, 0, 1)):
                out[y][x] = OUTLINE
    return width, out, [False] + hl + [False]


def _tile_pool(rom):
    """Tiles referenced only by text cells of the dialog maps (safe to overwrite per page)."""
    def mp(o):
        m = decompress(rom, o)[0]; return struct.unpack('<%dH' % (len(m) // 2), m)
    intext, outside = set(), set()
    for o, (_, title, lines) in SAVE_DIALOGS.items():
        rects = [(r, r + 1, c0, c1) for r, c0, c1, *_ in lines] + ([(0, 2, 10, 20), (3, 8, 3, 26)] if o in (0x7565bc, 0x756770) else [])
        rects += {0x756a58: [(7, 14, 3, 26)], 0x756c58: [(7, 14, 3, 26)], 0x757030: [(7, 14, 3, 26)],
                  0x756e70: [(7, 8, 3, 26), (9, 10, 21, 26), (11, 14, 3, 26)], 0x756890: [(1, 4, 4, 26), (11, 14, 3, 18)],
                  0x75651c: [(2, 3, 6, 15), (2, 3, 18, 19), (4, 5, 6, 17)]}.get(o, [])
        for i, e in enumerate(mp(o)):
            y, x = i // 32, i % 32
            (intext if any(a <= y <= b and c <= x <= d for a, b, c, d in rects) else outside).add(e & 0x3ff)
    for o in (0x74fe54, 0x751718, 0x751840, 0x751968, 0x745afc, 0x757788):
        outside |= {e & 0x3ff for e in mp(o)}
    # raw map pieces drawn by code (header sign, slot panels) and tiles seen on non-dialog screens in the emulator
    outside |= {e & 0x3ff for e in struct.unpack_from('<56H', rom, HEADER_PIECE)}
    outside |= {e & 0x3ff for e in struct.unpack_from('<196H', rom, EMPTY_PANEL)}
    prot = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'script', 'gfx_protected.json')
    if os.path.exists(prot): outside |= set(json.load(open(prot)))
    return sorted(intext - outside - {0x0f5, 0})


def patch_save_dialogs(rom, cmap, alloc):
    """Returns (redirects, sideloads)."""
    tiles = decompress(rom, SAVE_TILES)[0]
    pool = _tile_pool(rom)
    pools = {'box': pool[:178], 'copy': pool[178:202], 'prompt': pool[202:330]}
    base = bytearray(tiles)                      # permanent labels go into the remaining pool tiles
    patch_save_static(rom, cmap, base, pool[330:])
    pal7, palb = _pal(rom, 7), _pal(rom, 0xb)
    remap_b7 = [min(range(16), key=lambda j: sum((a - b) ** 2 for a, b in zip(palb[i], pal7[j])) + (99 if j == 0 and i else 0))
                for i in range(16)]
    redirects, sideloads = {}, []

    def tile_px(t):
        return [[(tiles[t * 32 + y * 4 + x // 2] >> (4 * (x & 1))) & 15 for x in range(8)] for y in range(8)]

    def tile_bytes(px):
        return bytes(px[y][x] | (px[y][x + 1] << 4) for y in range(8) for x in range(0, 8, 2))

    for mo, (cls, title, lines) in SAVE_DIALOGS.items():
        m = list(struct.unpack('<%dH' % (len(decompress(rom, mo)[0]) // 2), decompress(rom, mo)[0]))
        free = list(pools[cls]); new = {}

        def place(row, c0, c1, pal, bg, text, base=None, m=m):
            right = text.startswith('>'); left = text.startswith('<'); text = text.lstrip('<>')
            ncols = c1 - c0 + 1
            for r in (row, row + 1):
                for c in range(c0, c1 + 1): m[r * 32 + c] = BOX_BG if bg == 8 and base is None else 0
            if not text: return
            w, px, hl = render_line(rom, cmap, text, bg)
            ncell = (w + 7) // 8
            assert ncell <= ncols, 'text too wide: %r (%d px > %d)' % (text, w, ncols * 8)
            start = c0 + (ncols - ncell if right else 0 if left else (ncols - ncell) // 2)
            off = ncell * 8 - w if right else 0 if left else (ncell * 8 - w) // 2
            for k in range(ncell):
                cellhl = sum(hl[x - off] for x in range(k * 8, k * 8 + 8) if 0 <= x - off < len(hl)) > 3
                for ty in range(2):
                    cell = [[bg] * 8 for _ in range(8)]
                    if base is not None:
                        bt = base(row + ty, start + k)
                        cell = [[remap_b7[v] if v else 0 for v in rw] for rw in tile_px(bt)]
                    for y in range(8):
                        for x in range(8):
                            X = k * 8 + x - off
                            if 0 <= X < w:
                                v = px[ty * 8 + y][X]
                                if v != bg: cell[y][x] = v
                    t = free.pop(0)
                    new[t] = tile_bytes(cell)
                    m[(row + ty) * 32 + start + k] = t | ((7 if (cellhl or base) else pal) << 12)

        if title:
            orig = list(m)
            # frame tiles to draw the title over: same-parity column just left of the original title
            frame = lambda r, c: orig[r * 32 + (8 + (c % 2))] & 0x3ff if r else 0
            for r in (0, 1, 2):
                for c in range(10, 21): m[r * 32 + c] = orig[r * 32 + (8 + (c % 2))] if r else 0
            place(0, 10, 20, 7, 0, title, base=frame)
        for line in lines: place(*line)
        if mo == 0x756890:      # 4x2 raw piece the game pastes over cols 9-12 when Sleep Mode is ON
            tmp = [0] * (32 * 5)
            place(3, 9, 12, 9, 0, '>{Off}', m=tmp)
            for r in range(2):
                for c in range(4): struct.pack_into('<H', rom, 0x757778 + 2 * (r * 4 + c), tmp[(3 + r) * 32 + 9 + c])
        if cls == 'box':        # Japanese text spilled into frame columns 2/27; restore them (frame repeats every 4 rows)
            ref = struct.unpack('<%dH' % (len(decompress(rom, 0x756a58)[0]) // 2), decompress(rom, 0x756a58)[0])
            for r0, *_ in lines:
                for r in (r0, r0 + 1):
                    for c in (2, 27): m[r * 32 + c] = ref[(7 + (r - 7) % 4) * 32 + c]
        assert len(new) <= len(pools[cls])
        # side-load: contiguous tile range covering this class's pool, original data + this page's tiles
        lo, hi = min(pools[cls]), max(pools[cls]) + 1
        blob = bytearray(tiles[lo * 32:hi * 32])
        for t, data in new.items(): blob[(t - lo) * 32:(t - lo + 1) * 32] = data
        side = alloc(encode_raw(bytes(blob)))
        sideloads.append((mo, side, 0x06000000 + lo * 32))
        redirects[mo] = alloc(encode_raw(struct.pack('<%dH' % len(m), *m)))
    redirects[SAVE_TILES] = alloc(encode_raw(bytes(base)))
    return redirects, sideloads


# ---------------------------------------------------------------- always-visible save-screen labels

HEADER_PIECE = 0x755344     # 14x4 raw map entries: "ぼうけんのしょ" wooden sign
EMPTY_PANEL = 0x756140      # 28x7 raw map entries: "ぼうけんのきろくが ありません。"


def _ink_mask(rom, cmap, text):
    """1-bit text mask (16 rows) using the dialog font, glyphs packed with 1px spacing."""
    cols = []
    for ch in text:
        w, g = glyph(rom, cmap[ch])
        ink = [[1 if g[y][x] >= 2 else 0 for x in range(w)] for y in range(16)]
        used = [x for x in range(w) if any(ink[y][x] for y in range(16))]
        for x in range((max(used) + 1) if used else 3): cols.append([ink[y][x] for y in range(16)])
        cols.append([0] * 16)
    return len(cols) - 1, [[c[y] for c in cols[:-1]] for y in range(16)]


def patch_save_static(rom, cmap, tiles, pool):
    """Draw English into the header sign and the empty-slot panel; tiles from `pool` are overwritten
    in `tiles` (bytearray of the BG set) and the raw map pieces are edited in place."""
    pool = list(pool)

    def get_px(e):
        t, hf, vf = e & 0x3ff, (e >> 10) & 1, (e >> 11) & 1
        px = [[(tiles[t * 32 + y * 4 + x // 2] >> (4 * (x & 1))) & 15 for x in range(8)] for y in range(8)]
        if hf: px = [r[::-1] for r in px]
        if vf: px = px[::-1]
        return px

    def put(piece, w, r, c, px, pal):
        t = pool.pop(0)
        tiles[t * 32:t * 32 + 32] = bytes(px[y][x] | (px[y][x + 1] << 4) for y in range(8) for x in range(0, 8, 2))
        struct.pack_into('<H', rom, piece + 2 * (r * w + c), t | (pal << 12))

    # header sign: whiten the badges, draw blue text with a white halo
    W = 14
    hw = list(struct.unpack_from('<%dH' % (W * 4), rom, HEADER_PIECE))
    img = [[0] * (W * 8) for _ in range(16)]
    for r in range(2):
        for c in range(W):
            px = get_px(hw[r * W + c])
            for y in range(8): img[r * 8 + y][c * 8:c * 8 + 8] = px[y]
    for y in range(2, 16):
        for x in range(W * 8):
            if img[y][x] in (0xa, 0xb, 0xc): img[y][x] = 9
    tw, mask = _ink_mask(rom, cmap, 'Adventure Log')
    x0 = (W * 8 - tw) // 2
    for y in range(16):
        for x in range(-1, tw + 1):
            near = any(0 <= y + dy < 16 and 0 <= x + dx < tw and mask[y + dy][x + dx] for dy in (-1, 0, 1) for dx in (-1, 0, 1))
            if 0 <= x < tw and mask[y][x]: img[y][x0 + x] = 0xc if y < 10 else 0xb
            elif near: img[y][x0 + x] = 9
    pal = hw[0] >> 12
    for r in range(2):
        for c in range(W):
            put(HEADER_PIECE, W, r, c, [img[r * 8 + y][c * 8:c * 8 + 8] for y in range(8)], pal)

    # empty-slot panel: white text (4, shadow 3) on lime (1), cols 3-25 of rows 3-4
    W = 28
    tw, mask = _ink_mask(rom, cmap, 'No Adventure Log yet.')
    span = 23 * 8; x0 = (span - tw) // 2
    img = [[1] * span for _ in range(16)]
    for y in range(16):
        for x in range(tw):
            if mask[y][x]:
                img[y][x0 + x] = 4
                if y + 1 < 16 and not mask[y + 1][x] and img[y + 1][x0 + x] == 1: img[y + 1][x0 + x] = 3
    for r in range(2):
        for c in range(23):
            put(EMPTY_PANEL, W, 3 + r, 3 + c, [img[r * 8 + y][c * 8:c * 8 + 8] for y in range(8)], 5)
    # "ひき" (slimes rescued) and "しょう" (wins) unit labels: the numbers already sit next to a slime /
    # VS icon, so the labels are simply erased to the panel background (colour 6).
    for t in (0x37f, 0x39e, 0x39f, 0x37d, 0x39c, 0x39d):
        tiles[t * 32:t * 32 + 32] = b'\x66' * 32
    return len(pool)


# ---------------------------------------------------------------- tiny 3x5 font for small labels

TINY = {
 'A': ['010', '101', '111', '101', '101'], 'B': ['110', '101', '110', '101', '110'], 'C': ['011', '100', '100', '100', '011'],
 'D': ['110', '101', '101', '101', '110'], 'E': ['111', '100', '110', '100', '111'], 'F': ['111', '100', '110', '100', '100'],
 'G': ['011', '100', '101', '101', '011'], 'H': ['101', '101', '111', '101', '101'], 'I': ['111', '010', '010', '010', '111'],
 'J': ['001', '001', '001', '101', '010'], 'K': ['101', '101', '110', '101', '101'], 'L': ['100', '100', '100', '100', '111'],
 'M': ['101', '111', '111', '101', '101'], 'N': ['110', '101', '101', '101', '101'], 'O': ['010', '101', '101', '101', '010'],
 'P': ['110', '101', '110', '100', '100'], 'Q': ['010', '101', '101', '110', '011'], 'R': ['110', '101', '110', '101', '101'],
 'S': ['011', '100', '010', '001', '110'], 'T': ['111', '010', '010', '010', '010'], 'U': ['101', '101', '101', '101', '111'],
 'V': ['101', '101', '101', '101', '010'], 'W': ['101', '101', '111', '111', '101'], 'X': ['101', '101', '010', '101', '101'],
 'Y': ['101', '101', '010', '010', '010'], 'Z': ['111', '001', '010', '100', '111'], ' ': ['0', '0', '0', '0', '0'],
 '.': ['0', '0', '0', '0', '1'], '!': ['1', '1', '1', '0', '1'], '/': ['001', '001', '010', '100', '100'],
}


def tiny_mask(text):
    """1-bit mask, 5 rows tall, 1px spacing."""
    cols = []
    for ch in text:
        g = TINY[ch]
        for x in range(len(g[0])): cols.append([int(g[y][x]) for y in range(5)])
        cols.append([0] * 5)
    cols = cols[:-1]
    return len(cols), [[c[y] for c in cols] for y in range(5)]


# ---------------------------------------------------------------- name-entry buttons (BG0, tiles 0x74f90c, map 0x74fe74)

NAME_TILES = 0x74f90c
NAME_MAP = 0x74fe74
NAME_BUTTONS = [  # (rows, cols, lines) ; line = ('big'|'tiny', text)
    ((3, 7), (23, 29), [('tiny', 'CHANGE'), ('tiny', 'CHARS')]),
    ((13, 16), (23, 29), [('big', 'OK')]),
]


def patch_name_entry(rom, cmap, alloc):
    tiles = bytearray(decompress(rom, NAME_TILES)[0])
    m = struct.unpack('<%dH' % (len(decompress(rom, NAME_MAP)[0]) // 2), decompress(rom, NAME_MAP)[0])
    for (r0, r1), (c0, c1), lines in NAME_BUTTONS:
        W, H = (c1 - c0) * 8, (r1 - r0) * 8
        img = [[0] * W for _ in range(H)]
        cells = {}
        for r in range(r0, r1):
            for c in range(c0, c1):
                e = m[r * 32 + c]; t = e & 0x3ff
                assert not (e >> 10) & 3, 'flipped cell'
                cells[(r, c)] = t
                for y in range(8):
                    for x in range(8):
                        img[(r - r0) * 8 + y][(c - c0) * 8 + x] = (tiles[t * 32 + y * 4 + x // 2] >> (4 * (x & 1))) & 15
        # interior = bounding box of fill colour 'b'; clear old text inside it
        ys = [y for y in range(H) if 0xb in img[y]]; y0, y1 = min(ys), max(ys)
        xs = [x for x in range(W) for y in range(y0, y1 + 1) if img[y][x] == 0xb]; x0, x1 = min(xs), max(xs)
        for y in range(y0, y1 + 1):          # text colours (c-f) appear only in the label; clear across the full width
            for x in range(W):
                if img[y][x] in (0xc, 0xd, 0xe, 0xf): img[y][x] = 0xb
        masks = [(_ink_mask(rom, cmap, t) if kind == 'big' else tiny_mask(t)) for kind, t in lines]
        masks = [(w, [r for r in mk if any(r)] if kind == 'big' else mk) for (w, mk), (kind, _) in zip(masks, lines)]
        total_h = sum(len(mk) for _, mk in masks) + 3 * (len(masks) - 1)
        ty = y0 + ((y1 - y0 + 1) - total_h) // 2
        for w, mk in masks:
            tx = x0 + ((x1 - x0 + 1) - w) // 2
            h = len(mk)
            for y in range(-1, h + 1):
                for x in range(-1, w + 1):
                    ink = 0 <= y < h and 0 <= x < w and mk[y][x]
                    near = any(0 <= y + dy < h and 0 <= x + dx < w and mk[y + dy][x + dx] for dy in (-1, 0, 1) for dx in (-1, 0, 1))
                    if ink: img[ty + y][tx + x] = (0xc, 0xd, 0xe)[min(2, y * 3 // h)]
                    elif near and img[ty + y][tx + x] == 0xb: img[ty + y][tx + x] = 0xf
            ty += h + 3
        for (r, c), t in cells.items():
            for y in range(8):
                for x in range(0, 8, 2):
                    a = img[(r - r0) * 8 + y][(c - c0) * 8 + x]; b = img[(r - r0) * 8 + y][(c - c0) * 8 + x + 1]
                    tiles[t * 32 + y * 4 + x // 2] = a | (b << 4)
    return {NAME_TILES: alloc(encode_raw(bytes(tiles)))}


# ---------------------------------------------------------------- medium 4x7 uppercase font

_MED = """
A .##. #..# #..# #### #..# #..# #..#
B ###. #..# #..# ###. #..# #..# ###.
C .### #... #... #... #... #... .###
D ###. #..# #..# #..# #..# #..# ###.
E #### #... #... ###. #... #... ####
F #### #... #... ###. #... #... #...
G .### #... #... #.## #..# #..# .###
H #..# #..# #..# #### #..# #..# #..#
I ### .#. .#. .#. .#. .#. ###
J ..## ...# ...# ...# ...# #..# .##.
K #..# #.#. ##.. ##.. #.#. #..# #..#
L #... #... #... #... #... #... ####
M #...# ##.## #.#.# #.#.# #...# #...# #...#
N #..# ##.# ##.# #.## #.## #..# #..#
O .##. #..# #..# #..# #..# #..# .##.
P ###. #..# #..# ###. #... #... #...
Q .##. #..# #..# #..# #.## #..# .##.
R ###. #..# #..# ###. #.#. #..# #..#
S .### #... #... .##. ...# ...# ###.
T ##### ..#.. ..#.. ..#.. ..#.. ..#.. ..#..
U #..# #..# #..# #..# #..# #..# .##.
V #..# #..# #..# #..# .##. .##. .##.
W #...# #...# #...# #.#.# #.#.# ##.## #...#
X #..# #..# .##. .##. .##. #..# #..#
Y #...# #...# .#.#. ..#.. ..#.. ..#.. ..#..
Z #### ...# ..#. .#.. #... #... ####
! # # # # # . #
. . . . . . . #
? .##. #..# ...# ..#. .#.. .... .#..
"""
MED = {}
for _ln in _MED.strip().splitlines():
    _k, *_rows = _ln.split(' ')
    MED[_k] = _rows
MED[' '] = ['..'] * 7


def med_mask(text):
    cols = []
    for ch in text.upper():
        g = MED[ch]
        for x in range(len(g[0])): cols.append([1 if g[y][x] == '#' else 0 for y in range(7)])
        cols.append([0] * 7)
    cols = cols[:-1]
    return len(cols), [[c[y] for c in cols] for y in range(7)]


def redraw_regions(tiles, m, regions):
    """Generic in-place label redraw on a decompressed tileset (bytearray) + map (list of u16).
    region: dict(rows=(r0,r1), cols=(c0,c1), clear=set, bg=int, ink=int, shade=int|None,
                 lines=[(font, text)], align='center'|'left')  font: 'med' | 'tiny'"""
    import collections
    use = collections.Counter(e & 0x3ff for e in m)
    for rg in regions:
        (r0, r1), (c0, c1) = rg['rows'], rg['cols']
        W, H = (c1 - c0) * 8, (r1 - r0) * 8
        img = [[0] * W for _ in range(H)]
        for r in range(r0, r1):
            for c in range(c0, c1):
                e = m[r * 32 + c]; t = e & 0x3ff
                assert use[t] == 1 and not (e >> 10) & 3, 'shared/flipped tile at %d,%d' % (r, c)
                for y in range(8):
                    for x in range(8):
                        img[(r - r0) * 8 + y][(c - c0) * 8 + x] = (tiles[t * 32 + y * 4 + x // 2] >> (4 * (x & 1))) & 15
        for y in range(H):
            for x in range(W):
                if x < rg.get('xmin', 0): continue
                if rg.get('wipe') or img[y][x] in rg['clear']: img[y][x] = rg['bg']
        masks = [(med_mask(t) if f == 'med' else tiny_mask(t)) for f, t in rg['lines']]
        gap = rg.get('gap', 3)
        total = sum(len(mk) for _, mk in masks) + gap * (len(masks) - 1)
        ty = rg.get('top', (H - total) // 2)
        for w, mk in masks:
            tx = (W - w) // 2 if rg.get('align', 'center') == 'center' else rg.get('left', 0)
            for y in range(len(mk)):
                for x in range(w):
                    if mk[y][x]:
                        img[ty + y][tx + x] = rg['ink']
                        if rg.get('shade') is not None and ty + y + 1 < H and (y + 1 >= len(mk) or not mk[y + 1][x]):
                            if img[ty + y + 1][tx + x] == rg['bg']: img[ty + y + 1][tx + x] = rg['shade']
            ty += len(mk) + gap
        for r in range(r0, r1):
            for c in range(c0, c1):
                t = m[r * 32 + c] & 0x3ff
                for y in range(8):
                    for x in range(0, 8, 2):
                        tiles[t * 32 + y * 4 + x // 2] = img[(r - r0) * 8 + y][(c - c0) * 8 + x] | (img[(r - r0) * 8 + y][(c - c0) * 8 + x + 1] << 4)


TUTORIAL_TILES, TUTORIAL_MAP = 0x558bcc, 0x5597d4     # Elasto Blast tutorial (loaded by FUN_08081160)
PARCH = dict(clear={3, 4, 5}, bg=2, ink=5, shade=4)
TUTORIAL = [
    dict(rows=(1, 3), cols=(0, 9), clear={6, 7}, bg=1, ink=7, shade=6, lines=[('med', 'ELASTO BLAST')], align='left', left=10),
    dict(rows=(5, 7), cols=(3, 9), lines=[('med', 'HOLD IT')], **PARCH),
    dict(rows=(7, 9), cols=(6, 9), lines=[], **PARCH),
    dict(rows=(5, 7), cols=(18, 19), lines=[], wipe=True, **PARCH),
    dict(rows=(7, 9), cols=(16, 21), lines=[('med', 'STRETCH')], **PARCH),
    dict(rows=(14, 16), cols=(26, 27), lines=[], wipe=True, **PARCH),
    dict(rows=(5, 7), cols=(17, 18), lines=[], xmin=6, **PARCH),     # で started inside the + icon cell
    dict(rows=(14, 16), cols=(25, 26), lines=[], xmin=6, **PARCH),   # を started inside the A icon cell
    dict(rows=(16, 18), cols=(24, 29), lines=[('med', 'LET GO')], **PARCH),
    dict(rows=(16, 17), cols=(2, 9), clear={1, 6}, bg=0xb, ink=1, shade=None, lines=[('tiny', 'PRESS START')]),
    dict(rows=(18, 19), cols=(3, 9), clear={1, 6}, bg=0xb, ink=1, shade=None, lines=[('tiny', 'TO BEGIN!')]),
]


def patch_tutorial(rom, alloc):
    tiles = bytearray(decompress(rom, TUTORIAL_TILES)[0])
    m = list(struct.unpack('<%dH' % (len(decompress(rom, TUTORIAL_MAP)[0]) // 2), decompress(rom, TUTORIAL_MAP)[0]))
    redraw_regions(tiles, m, TUTORIAL)
    return {TUTORIAL_TILES: alloc(encode_raw(bytes(tiles)))}


# ---------------------------------------------------------------- "ドキドキ ツボくらっしゅ" minigame logo (sprites)

POT_SHEET = 0x1f6d98          # OBJ tiles, loaded at tile 288
POT_BASE = 288
POT_PIECES = [  # settled OAM layout (x, y, w, h, tile), in OAM priority order
    (39, 84, 32, 32, 365), (69, 82, 32, 32, 381), (104, 82, 16, 32, 397), (117, 82, 16, 32, 405),
    (133, 82, 8, 32, 413), (140, 91, 16, 16, 417), (157, 80, 16, 32, 421), (173, 80, 8, 32, 429),
    (177, 90, 16, 16, 433), (177, 106, 16, 8, 437), (193, 98, 8, 16, 439)]
POT_DOKI = 363                 # 16x8 piece used twice ("ドキ" + "ドキ")


def _scale2(mask):
    return [[v for v in row for _ in (0, 1)] for row in mask for _ in (0, 1)]


def patch_pot_logo(rom, alloc):
    sheet = bytearray(decompress(rom, POT_SHEET)[0])
    W, H = 240, 160
    cover = [[None] * W for _ in range(H)]
    for k, (x, y, w, h, t) in enumerate(POT_PIECES):
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                if cover[yy][xx] is None: cover[yy][xx] = k
    img = [[0] * W for _ in range(H)]
    # letters: 2x-scaled 4x7 font, placed left to right; nudge right until the outlined glyph is fully covered
    # each word starts at a fixed x so the 3px gap between pieces (x=101-103) falls between the words
    for word, x in (('POT', 66), ('CRASH!', 105)):
        for ch in word:
            gw, gm = med_mask(ch)
            m2 = _scale2(gm); gw2, gh2 = gw * 2, len(m2)
            y0 = 92
            def fits(x0):
                for yy in range(-1, gh2 + 1):
                    for xx in range(-1, gw2 + 1):
                        if cover[y0 + yy][x0 + xx] is None:
                            near = any(0 <= yy + dy < gh2 and 0 <= xx + dx < gw2 and m2[yy + dy][xx + dx]
                                       for dy in (-1, 0, 1) for dx in (-1, 0, 1))
                            if near: return False
                return True
            while not fits(x): x += 1
            for yy in range(-1, gh2 + 1):
                for xx in range(-1, gw2 + 1):
                    ink = 0 <= yy < gh2 and 0 <= xx < gw2 and m2[yy][xx]
                    near = any(0 <= yy + dy < gh2 and 0 <= xx + dx < gw2 and m2[yy + dy][xx + dx] for dy in (-1, 0, 1) for dx in (-1, 0, 1))
                    if ink:
                        top = yy == 0 or not m2[yy - 1][xx]
                        img[y0 + yy][x + xx] = 5 if top else (1 if yy < 4 and xx < 3 else 6)
                    elif near and img[y0 + yy][x + xx] == 0:
                        img[y0 + yy][x + xx] = 7
            x += gw2 + 2
        assert x < 205, 'logo too wide'
    for k, (px0, py0, w, h, t) in enumerate(POT_PIECES):
        for ty in range(h // 8):
            for tx in range(w // 8):
                tile = t - POT_BASE + ty * (w // 8) + tx
                for yy in range(8):
                    for xx in range(0, 8, 2):
                        def v(dx):
                            X, Y = px0 + tx * 8 + xx + dx, py0 + ty * 8 + yy
                            return img[Y][X] if cover[Y][X] == k else 0
                        sheet[tile * 32 + yy * 4 + xx // 2] = v(0) | (v(1) << 4)
    # "ドキ" piece (16x8, shown twice): tiny "DOKI" in white with blue outline
    tw, tm = tiny_mask('DOKI')
    cell = [[0] * 16 for _ in range(8)]
    ox, oy = (16 - tw) // 2, 1
    for yy in range(-1, 6):
        for xx in range(-1, tw + 1):
            ink = 0 <= yy < 5 and 0 <= xx < tw and tm[yy][xx]
            near = any(0 <= yy + dy < 5 and 0 <= xx + dx < tw and tm[yy + dy][xx + dx] for dy in (-1, 0, 1) for dx in (-1, 0, 1))
            if ink: cell[oy + yy][ox + xx] = 1
            elif near: cell[oy + yy][ox + xx] = 6
    for tx in range(2):
        tile = POT_DOKI - POT_BASE + tx
        for yy in range(8):
            for xx in range(0, 8, 2):
                sheet[tile * 32 + yy * 4 + xx // 2] = cell[yy][tx * 8 + xx] | (cell[yy][tx * 8 + xx + 1] << 4)
    return {POT_SHEET: alloc(encode_raw(bytes(sheet)))}


# ---------------------------------------------------------------- title screen logo (sprites, sheet 0x7c5624, frames 0x7c7084)

TITLE_SHEET = 0x7c5624
TITLE_FRAMES = 0x7c7084
_TSZ = {(0, 0): (8, 8), (0, 1): (16, 16), (0, 2): (32, 32), (0, 3): (64, 64), (1, 0): (16, 8), (1, 1): (32, 8),
        (1, 2): (32, 16), (1, 3): (64, 32), (2, 0): (8, 16), (2, 1): (8, 32), (2, 2): (16, 32), (2, 3): (32, 64)}


def _frame(rom, base, fid):
    f = base + (struct.unpack_from('<H', rom, base + 2 * fid)[0] & ~1)
    out = []
    for k in range(rom[f]):
        a0, a1, a2 = struct.unpack_from('<3H', rom, f + 2 + 6 * k)
        y = (a0 & 0xff) - (256 if a0 & 0x80 else 0); x = (a1 & 0xff) - (256 if a1 & 0x80 else 0)
        w, h = _TSZ[(a0 >> 14, a1 >> 14)]
        out.append((x, y, w, h, a2 & 0x3ff))
    return f, out


def _scale_to(mask, tw, th):
    h, w = len(mask), len(mask[0])
    return [[mask[y * h // th][x * w // tw] for x in range(tw)] for y in range(th)]


def draw_cluster(sheet, pieces, mask, grad, outline, pad=1, bold=False):
    """Scale `mask` into the pieces' bounding box, style it (outline + vertical gradient) and write each
    pixel into the first piece that covers it (sprites earlier in the list are drawn on top)."""
    x0 = min(p[0] for p in pieces); y0 = min(p[1] for p in pieces)
    x1 = max(p[0] + p[2] for p in pieces); y1 = max(p[1] + p[3] for p in pieces)
    W, H = x1 - x0, y1 - y0
    own = [[None] * W for _ in range(H)]
    for k, (x, y, w, h, t) in enumerate(pieces):
        for yy in range(y - y0, y - y0 + h):
            for xx in range(x - x0, x - x0 + w):
                if own[yy][xx] is None: own[yy][xx] = k
    rows = [y for y in range(H) if any(o is not None for o in own[y])]
    cy0, cy1 = rows[0], rows[-1]
    tw, th = W - 2 * pad - 2, (cy1 - cy0 + 1) - 2 * pad - 2
    m = _scale_to(mask, max(1, tw), max(1, th))
    if bold:   # thicken vertical strokes by one pixel
        m = [[1 if r[x] or (x > 0 and r[x - 1]) else 0 for x in range(len(r))] for r in m]
    img = [[0] * W for _ in range(H)]
    ox, oy = pad + 1, cy0 + pad + 1
    for y in range(-1, th + 1):
        for x in range(-1, tw + 1):
            ink = 0 <= y < th and 0 <= x < tw and m[y][x]
            near = any(0 <= y + dy < th and 0 <= x + dx < tw and m[y + dy][x + dx] for dy in (-1, 0, 1) for dx in (-1, 0, 1))
            if ink: img[oy + y][ox + x] = grad[min(len(grad) - 1, y * len(grad) // th)]
            elif near: img[oy + y][ox + x] = outline
    for k, (x, y, w, h, t) in enumerate(pieces):
        for ty in range(h // 8):
            for tx in range(w // 8):
                tile = t + ty * (w // 8) + tx
                for yy in range(8):
                    for xx in range(0, 8, 2):
                        def v(dx):
                            X, Y = x - x0 + tx * 8 + xx + dx, y - y0 + ty * 8 + yy
                            return img[Y][X] if own[Y][X] == k else 0
                        sheet[tile * 32 + yy * 4 + xx // 2] = v(0) | (v(1) << 4)


def _letters(text, gap=1):
    w, m = med_mask(text)
    return m


SLIME_GRAD, MORI_GRAD, SUB_GRAD = [0xe, 0xd, 0xc, 0xb, 0xa, 0x9, 0x8], [7, 6, 5, 4, 3], [5, 6, 7, 4]


def patch_title(rom, alloc):
    sheet = bytearray(decompress(rom, TITLE_SHEET)[0])
    _, f5 = _frame(rom, TITLE_FRAMES, 5)
    clusters = [(f5[0:4], 'S'), (f5[4:9], 'LI'), (f5[9:14], 'M'), (f5[14:18], 'E')]
    for fid, sl, text in ((20, slice(0, 5), 'S'), (21, slice(0, 7), 'SLI'), (22, slice(4, 11), 'LIM'),
                          (23, slice(9, 16), 'ME'), (24, slice(14, 17), 'E')):
        clusters.append((_frame(rom, TITLE_FRAMES, fid)[1][sl], text))
    for pieces, text in clusters:
        draw_cluster(sheet, pieces, _letters(text), SLIME_GRAD, 1, bold=True)
    # もり pair (tiles 150/154, shown twice) and its squish variants
    _, f4 = _frame(rom, TITLE_FRAMES, 4)
    for pieces in (f4[0:2], _frame(rom, TITLE_FRAMES, 25)[1][0:3], _frame(rom, TITLE_FRAMES, 26)[1][0:4]):
        draw_cluster(sheet, pieces, _letters('MORI'), MORI_GRAD, 1)
    # ドラゴンクエスト under the English logo: erase
    for t in range(121, 135): sheet[t * 32:t * 32 + 32] = b'\0' * 32
    # subtitle 衝撃のしっぽ団: re-lay frame 30 (and its copy in composite frame 6) as 32x16 + 32x16 + 16x16
    lay = [(-40, 20, 32, 16, 197), (-8, 20, 32, 16, 205), (24, 20, 16, 16, 213)]
    draw_cluster(sheet, lay, _letters('THE PLOB ATTACK!'), SUB_GRAD, 1, pad=0)
    bits = {(32, 16): (1, 2), (16, 16): (0, 1), (8, 8): (0, 0)}
    for fid, first in ((30, 0), (6, 46)):
        f, ps = _frame(rom, TITLE_FRAMES, fid)
        for k in range(5):
            o = f + 2 + 6 * (first + k)
            pal = struct.unpack_from('<H', rom, o + 4)[0] >> 12
            if k < len(lay):
                x, y, w, h, t = lay[k]; sh, sz = bits[(w, h)]
            else:
                x, y, t, sh, sz = 0, -100, 217, 0, 0
            struct.pack_into('<3H', rom, o, (y & 0xff) | (sh << 14), (x & 0xff) | (sz << 14), t | (pal << 12))
    sheet[217 * 32:218 * 32] = b'\0' * 32
    return {TITLE_SHEET: alloc(encode_raw(bytes(sheet)))}
