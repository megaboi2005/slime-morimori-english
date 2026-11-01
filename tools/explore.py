"""Run an input sequence from a save state; at every step record decompress calls (src->dst),
BG map tile usage (charbase-0 layers) and a screenshot. Output: dir/log.json + dir/NN.png"""
import json, os, struct, subprocess, sys, tempfile
from PIL import Image
rom, state, outdir = sys.argv[1], sys.argv[2], sys.argv[3]
steps = sys.argv[4:]
os.makedirs(outdir, exist_ok=True)
lines = ['load ' + state, 'brk 8098AC8']
for i, s in enumerate(steps):
    n, _, k = s.partition(':')
    lines += ['run %s %s' % (n, k or '-'), 'shot %s/%02d.ppm' % (outdir, i),
              'dump %s/%02d.vram 6000000:10000' % (outdir, i), 'dump %s/%02d.io 4000000:60' % (outdir, i)]
sc = os.path.join(outdir, 's.txt'); open(sc, 'w').write('\n'.join(lines) + '\n')
res = subprocess.run([os.path.join(os.path.dirname(os.path.abspath(__file__)), 'harness', 'harness'), rom, sc],
                     capture_output=True, text=True)
calls = sorted({(l.split()[2][3:], l.split()[3][3:]) for l in res.stdout.splitlines() if l.startswith('break')})
log = {'calls': calls, 'steps': []}
for i in range(len(steps)):
    vram = open('%s/%02d.vram' % (outdir, i), 'rb').read(); io = open('%s/%02d.io' % (outdir, i), 'rb').read()
    disp = struct.unpack_from('<H', io, 0)[0]; used = set()
    for b in range(4):
        if not disp & (0x100 << b): continue
        c = struct.unpack_from('<H', io, 8 + 2 * b)[0]
        if (c >> 2) & 3: continue
        sb = ((c >> 8) & 31) * 0x800; nblk = [1, 2, 2, 4][c >> 14]
        for e in struct.unpack_from('<%dH' % (1024 * nblk), vram, sb): used.add(e & 0x3ff)
    log['steps'].append(sorted(used))
    Image.open('%s/%02d.ppm' % (outdir, i)).save('%s/%02d.png' % (outdir, i)); os.remove('%s/%02d.ppm' % (outdir, i))
json.dump(log, open(outdir + '/log.json', 'w'))
print(len(calls), 'decompress calls:', calls)
