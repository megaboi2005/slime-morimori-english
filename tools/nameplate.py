"""Speaker name plates: `05 <tile indices> 05`, tiles are 8x16 cells in sheet @0x73cae8 (FUN_08096580)."""
H = "あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよらりるれろわをんがぎぐげござじずぜぞだぢづでどばびぶべぼぱぴぷぺぽぁぃぅぇぉっゃゅょ"
K = "アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲンガギグゲゴザジズゼゾダヂヅデドバビブベボパピプペポァィゥェォッャュョ"
CH = {}
for i, c in enumerate(H): CH[0x10 + i] = c
for i, c in enumerate(K): CH[0x60 + i] = c
for i, c in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"): CH[0xb0 + i] = c
for c, k in zip(" ・?゛ー!♪♥.", range(0xd4, 0xdd)): CH[k] = c
for i, c in enumerate("abcdefghijklmnopqrstuvwxyz"): CH[0xdd + i] = c
ENC = {v: k for k, v in CH.items() if v.isascii()}

def decode(hexstr):
    return ''.join(CH.get(b, '[%02x]' % b) for b in bytes.fromhex(hexstr))

def encode(name):
    return bytes(ENC[c] for c in name)
