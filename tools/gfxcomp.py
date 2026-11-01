"""Slime MoriMori graphics compression (decompressor FUN_08098ac8, hand-written Thumb asm).

Layout: u32 header (size << 8), then an MSB-first bitstream read from little-endian u32 words.
First 8 bits: mode byte
  bits 0-2  LZ variant: 0,1,2 = byte LZ with 2/4/7 distance classes, 3 = halfword LZ, 4 = raw literals
  bits 3-4  literal coding: 1 = Huffman 4-bit pairs, 2 = Huffman 8-bit, else plain 8 bits
  bits 5-7  post filter: 1 nibble delta, 2 byte delta, 3 u16 running sum, 4 per-byte-lane running sum
encode_raw() produces mode 4 / plain literals / no filter, which the game decodes like any other.
"""
import struct


class Bits:
    def __init__(self, data, pos):
        self.d, self.p, self.buf, self.n = data, pos, 0, 0

    def get(self, k):
        if k == 0: return 0
        v = 0
        for _ in range(k):
            if self.n == 0:
                self.buf = struct.unpack_from('<I', self.d, self.p)[0]; self.p += 4; self.n = 32
            v = (v << 1) | (self.buf >> 31)
            self.buf = (self.buf << 1) & 0xffffffff; self.n -= 1
        return v


def _huff_tree(bits, symbits):
    """Port of FUN_08098b84: canonical-ish tree. Returns dict node->[child0, child1] (ints >=0 nodes, <0 leaves)."""
    tree = {0: [None, None]}
    nxt = 1
    code = 0
    depth = 0
    for _ in range(symbits * 2):          # r6 = sl << 1 iterations (code lengths 1..2*symbits)
        code <<= 1
        count = bits.get(symbits)
        for _ in range(count):
            node = 0
            for d in range(depth, 0, -1):
                b = (code >> d) & 1
                if tree[node][b] is None:
                    tree[node][b] = nxt; tree[nxt] = [None, None]; nxt += 1
                node = tree[node][b]
            tree[node][code & 1] = ~bits.get(symbits)
            code += 1
        depth += 1
    return tree


def _huff_read(bits, tree):
    node = 0
    while True:
        node = tree[node][bits.get(1)]
        if node < 0: return ~node


def decompress(rom, off):
    size = struct.unpack_from('<I', rom, off)[0] >> 8
    bits = Bits(rom, off + 4)
    mode = bits.get(8)
    lz, lit, filt = mode & 7, (mode >> 3) & 3, mode >> 5
    if lit == 1:
        tree = _huff_tree(bits, 4)
        literal = lambda: (_huff_read(bits, tree) << 4) | _huff_read(bits, tree)
    elif lit == 2:
        tree = _huff_tree(bits, 8)
        literal = lambda: _huff_read(bits, tree)
    else:
        literal = lambda: bits.get(8)
    out = bytearray()

    def dist_table(n):
        t, base = [], 1
        for _ in range(n):
            nb = bits.get(4) + 1
            t.append((base, nb)); base += 1 << nb
        return t

    def copy(d, n):
        for _ in range(n): out.append(out[-d])

    if lz == 0:
        t = dist_table(2)
        while len(out) < size:
            c = bits.get(2)
            if c < 2:
                b, nb = t[c]; d = b + bits.get(nb); copy(d, bits.get(6) + 3)
            elif c == 2:
                for _ in range(bits.get(6) + 1): out.append(literal())
            else:
                n = bits.get(6) + 1; out.append(bits.get(8)); copy(1, n)
    elif lz == 1:
        t = dist_table(4)
        while len(out) < size:
            if bits.get(1):
                b, nb = t[bits.get(2)]; d = b + bits.get(nb); copy(d, bits.get(4) + 3)
            else:
                out.append(literal())
    elif lz == 2:
        t = dist_table(7)
        while len(out) < size:
            if not bits.get(1):
                out.append(literal()); continue
            i = bits.get(3)
            if i != 7:
                b, nb = t[i]; d = b + bits.get(nb); copy(d, bits.get(4) + 3); continue
            r = 0
            while True:
                r = (r << 4) + bits.get(4); cont = r & 1; r >>= 1
                if not cont: break
            if bits.get(1):
                b, nb = t[bits.get(3)]; d = b + bits.get(nb); copy(d, (r << 4) + bits.get(4) + 3)
            else:
                for _ in range(r + 1): out.append(literal())
    elif lz == 3:
        t = dist_table(3)

        def hcopy(d, n):
            for _ in range(n): out.extend(out[len(out) - d:len(out) - d + 2])
        while len(out) < size:
            if not bits.get(1):
                lo = literal(); hi = literal(); out.extend((lo, hi)); continue
            i = bits.get(2)
            if i != 3:
                b, nb = t[i]; d = (b + bits.get(nb)) * 2; hcopy(d, bits.get(3) + 2); continue
            r = 0
            while True:
                r = (r << 3) + bits.get(3); cont = r & 1; r >>= 1
                if not cont: break
            if bits.get(1):
                b, nb = t[bits.get(2)]; d = (b + bits.get(nb)) * 2; hcopy(d, (r << 3) + bits.get(3) + 2)
            else:
                for _ in range(r + 1): lo = literal(); hi = literal(); out.extend((lo, hi))
    else:
        while len(out) < size: out.append(literal())
    out = out[:size]
    if filt: out = _filter(out, filt)
    return bytes(out), bits.p - off


def _filter(out, f):
    hw = list(struct.unpack('<%dH' % (len(out) // 2), bytes(out[:len(out) // 2 * 2])))
    if f == 1:
        r5 = 0
        for i, h in enumerate(hw):
            r1 = (h >> 4) + r5; r2 = h + r1; r3 = (h >> 12) + r2; r4 = h >> 8; r5 = r4 + r3
            r1 &= 15; r2 &= 15; r5 &= 15
            hw[i] = ((r1 << 4) | r2 | (r3 << 12) | (r5 << 8)) & 0xffff
    elif f == 2:
        r4 = 0
        for i, h in enumerate(hw):
            r2 = (h + r4) & 0xff; r4 = (h >> 8) + r2
            hw[i] = ((r4 << 8) | r2) & 0xffff
    elif f == 3:
        r4 = 0
        for i, h in enumerate(hw):
            r4 = (r4 + h) & 0xffffffff; hw[i] = r4 & 0xffff
    elif f == 4:
        r4 = r5 = 0
        for i, h in enumerate(hw):
            r4 = (r4 + h) & 0xff; r5 = (r5 + h) & 0xff00; hw[i] = r5 | r4
    return bytearray(struct.pack('<%dH' % len(hw), *hw)) + out[len(hw) * 2:]


def encode_raw(data):
    """Mode 4 (raw literals), plain 8-bit literals, no filter."""
    bitstr = '00000100' + ''.join('{:08b}'.format(b) for b in data)
    bitstr += '0' * (-len(bitstr) % 32)
    words = [int(bitstr[i:i + 32], 2) for i in range(0, len(bitstr), 32)]
    return struct.pack('<I', len(data) << 8) + struct.pack('<%dI' % len(words), *words)
