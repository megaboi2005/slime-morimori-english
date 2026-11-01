"""Create an IPS patch (supports ROMs up to 16 MB): python tools/make_ips.py orig.gba new.gba out.ips"""
import sys
a = open(sys.argv[1], 'rb').read(); b = open(sys.argv[2], 'rb').read()
out = bytearray(b'PATCH')
ORIG_LEN = len(a); last = 0
a = a + b'\x00' * max(0, len(b) - len(a))
i = 0
while i < len(b):
    if a[i] == b[i]: i += 1; continue
    j = i
    while j < len(b) and j - i < 0xffff and (a[j] != b[j] or (j + 1 < len(b) and a[j + 1] != b[j + 1])): j += 1
    if i == 0x454f46: i -= 1                     # offset 'EOF' would read as the terminator
    assert i < 0x1000000
    out += i.to_bytes(3, 'big') + (j - i).to_bytes(2, 'big') + b[i:j]
    i = j
    last = j
if len(b) > ORIG_LEN and last < len(b):
    out += (len(b) - 1).to_bytes(3, 'big') + (1).to_bytes(2, 'big') + b[-1:]   # pad patched ROM to full size
out += b'EOF'
open(sys.argv[3], 'wb').write(out)
print('%s: %d bytes' % (sys.argv[3], len(out)))
