"""Python driver for the headless mGBA harness (tools/harness/harness, interactive mode).

    from gba import GBA
    g = GBA('build/rocketslime_en.gba')
    g.load('tests/states/bubble.st')
    g.inject_message(0x40, 0x13)      # next message start shows 064-019 instead
    g.run(60); g.shot().save('x.png')

Known RAM (see tools/README-testing.md):
    0x0200118C  u32  current dialogue text pointer
    0x020011A6  u8   dialogue box state: 1 = typing, 5 = waiting for A
    0x08095E18  fn   start message (r0 = group, r1 = index)
"""
import os, subprocess, tempfile
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
HARNESS = os.path.join(HERE, 'harness', 'harness')
MSG_START = 0x08095E18
TEXT_PTR = 0x0200118C
BOX_STATE = 0x020011A6
KEYS = {'A': 'A', 'B': 'B', 'start': 'S', 'select': 's', 'up': 'U', 'down': 'D', 'left': 'l', 'right': 'r', 'L': 'L', 'R': 'R'}


class GBA:
    def __init__(self, rom):
        self.p = subprocess.Popen([HARNESS, rom, '-'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
        self.tmp = tempfile.mkdtemp(prefix='gba')
        self.log = []

    def cmd(self, line):
        """Send one harness command, return any output lines before the 'ok' sync."""
        self.p.stdin.write(line + '\n'); self.p.stdin.flush()
        out = []
        while True:
            l = self.p.stdout.readline()
            if not l: raise RuntimeError('harness exited during: ' + line)
            l = l.rstrip('\n')
            if l == 'ok': return out
            out.append(l); self.log.append(l)

    def run(self, frames, keys='-'):
        """keys: harness letters ('A', 'AB', 'S'=start) or names joined by '+' ('start', 'up+A')."""
        if keys and keys != '-' and any(k in KEYS for k in keys.split('+')) and keys not in ('A', 'B', 'L', 'R'):
            keys = ''.join(KEYS[k] for k in keys.split('+'))
        self.cmd('run %d %s' % (frames, keys or '-'))

    def press(self, keys='A', hold=4, after=6):
        self.run(hold, keys); self.run(after)

    def load(self, path):
        """Load a state: harness raw state (tests/states/*.st) or an mGBA app state (*.ss0-9, *.ss)."""
        if path.rsplit('.', 1)[-1].startswith('ss'):
            out = self.cmd('loadss ' + path)
            if not any('ok' in l for l in out): raise RuntimeError('could not load ' + path)
        else:
            self.cmd('load ' + path)

    def save_ss(self, path): self.cmd('savess ' + path)        # state the mGBA app can open
    def load_sav(self, path): self.cmd('loadsav ' + path)      # battery save (.sav) + reset
    def save(self, path): self.cmd('save ' + path)
    def poke8(self, a, v): self.cmd('poke8 %x %x' % (a, v))
    def poke16(self, a, v): self.cmd('poke16 %x %x' % (a, v))
    def poke32(self, a, v): self.cmd('poke32 %x %x' % (a, v))

    def peek(self, addr, n):
        out = self.cmd('peek %x %x' % (addr, n))
        return bytes.fromhex(out[-1].split()[2])

    def u8(self, a): return self.peek(a, 1)[0]
    def u32(self, a): return int.from_bytes(self.peek(a, 4), 'little')

    def shot(self):
        f = os.path.join(self.tmp, 's.ppm')
        self.cmd('shot ' + f)
        return Image.open(f).convert('RGB')

    def inject_message(self, group, index, skip=0):
        """Replace the (skip+1)-th message the game starts with message group-index."""
        self.cmd('inject %x %d %x %x' % (MSG_START, skip, group, index))

    def until(self, addr, state_out, maxframes=20000):
        """Tap A until addr executes; core is left (and state saved) one frame before the hit."""
        out = self.cmd('until %x %s %d' % (addr, state_out, maxframes))
        return any('hit' in l for l in out)

    def close(self):
        try: self.cmd('quit')
        except Exception: pass
        self.p.wait(timeout=5)
