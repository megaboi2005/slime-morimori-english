"""Drive tools/harness/harness: python tools/emu.py rom out.png [--load st] [--save st] step...
step = FRAMES[:KEYS][!]   ('!' = screenshot after the step), e.g.  400 5:S 120! 5:A 200!"""
import os, subprocess, sys, tempfile
from PIL import Image

def main():
    args = sys.argv[1:]
    rom, out = args[0], args[1]
    rest = args[2:]
    tmp = tempfile.mkdtemp()
    lines, shots = [], []
    while rest:
        a = rest.pop(0)
        if a == '--load': lines.append('load ' + rest.pop(0)); continue
        if a == '--save': lines.append('save ' + rest.pop(0)); continue
        shot = a.endswith('!'); a = a.rstrip('!')
        n, _, keys = a.partition(':')
        lines.append('run %s %s' % (n, keys or '-'))
        if shot:
            f = os.path.join(tmp, '%d.ppm' % len(shots)); shots.append(f); lines.append('shot ' + f)
    script = os.path.join(tmp, 's.txt'); open(script, 'w').write('\n'.join(lines) + '\n')
    harness = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'harness', 'harness')
    subprocess.run([harness, rom, script], check=True)
    ims = [Image.open(f) for f in shots]
    cols = min(4, len(ims)); rows = (len(ims) + cols - 1) // cols
    sheet = Image.new('RGB', (cols * 244, rows * 164), (255, 0, 255))
    for i, im in enumerate(ims): sheet.paste(im, ((i % cols) * 244, (i // cols) * 164))
    sheet.resize((sheet.width * 2, sheet.height * 2), Image.NEAREST).save(out)

if __name__ == '__main__':
    main()
