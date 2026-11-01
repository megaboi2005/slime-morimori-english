"""Show every (or selected) dialogue message in the real game and check each text box.

    .venv/bin/python tools/msgtest.py                 # all messages
    .venv/bin/python tools/msgtest.py 064-019 010-*   # some messages (glob ok)
    .venv/bin/python tools/msgtest.py --failed        # re-run what failed last time

Each message is injected into Hooly's speech bubble in the opening scene (tests/states/bubble.st),
then the script waits for every box to finish typing (box state = 5), screenshots it, presses A.
Output: tests/out/msgs/<id>_<box>.png, tests/out/report.json, contact sheets tests/out/sheets/<group>.png.

Checks (flags in report.json):
  overflow    text pixels touch the edge of the bubble interior
  boxes       number of boxes shown != number of {wait} codes in the built message
  stuck       box never finished / message never ended (menu prompts are answered with A)
  no_start    the injected message never started
"""
import fnmatch, json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PIL import Image, ImageDraw
from gba import GBA, TEXT_PTR, BOX_STATE
import script

JA = '--ja' in sys.argv          # run against the original Japanese ROM (for comparison)
if JA: sys.argv.remove('--ja')
ROM = 'rocketslime.gba' if JA else 'build/rocketslime_en.gba'
STATE = 'tests/states/ja_bubble.st' if JA else 'tests/states/bubble.st'
OUT = 'tests/out_ja' if JA else 'tests/out'
TEXT = (49, 49, 99)


def built_messages():
    rom = open(ROM, 'rb').read(); tbl = script.load_table()
    msgs = {}
    for g, k, slot, off in script.messages(rom):
        text, end = script.decode(rom, off, tbl)
        msgs['%03d-%03d' % (g, k)] = dict(g=g, k=k, start=0x08000000 + off, end=0x08000000 + end, text=text,
                                          boxes=text.count('{wait}'))
    return msgs


def check_box(im):
    """Return list of problems seen in one screenshot of a speech bubble."""
    px = im.load(); w, h = im.size; probs = []
    for y in range(h):
        xs = [x for x in range(w) if px[x, y] == (255, 255, 255)]
        if len(xs) < 150: continue                 # not a bubble-interior row
        left, right = xs[0], xs[-1]
        txt = [x for x in range(left, right + 1) if px[x, y] == TEXT]
        if txt and txt[-1] >= right - 1:          # text reaching the right edge (left edge = nameplate)
            probs.append('overflow'); break
    return probs


ROMB = b''


def run_one(g, mid, m):
    g.load(STATE); g.inject_message(m['g'], m['k'])
    rec = dict(id=mid, flags=[], shots=[])
    for _ in range(100):                          # wait for the injected text to start
        g.run(2)
        if m['start'] <= g.u32(TEXT_PTR) <= m['end']: break
    else:
        rec['flags'].append('no_start'); return rec
    menu = '{0a:' in m['text'] or '{waitsnd}' in m['text']    # ends in a menu / Ok-No choice
    box = 0; last = None; stall = 0; prev = None
    for _ in range(4000):                           # hard cap: ~12000 frames per message
        g.run(3)
        ptr, st = g.u32(TEXT_PTR), g.u8(BOX_STATE)
        if not (m['start'] <= ptr <= m['end']): break          # message finished
        stall = stall + 1 if (ptr, st) == prev else 0
        prev = (ptr, st)
        if st == 5 and ROMB[ptr - 1 - 0x08000000] == 0x08 and ptr != last:
            # stopped on {end} (08) after a {wait}: the box is complete and waiting for A
            last = ptr
            im = g.shot(); f = '%s/msgs/%s_%d.png' % (OUT, mid, box)
            im.save(f); rec['shots'].append(f)
            for p in check_box(im):
                if p not in rec['flags']: rec['flags'].append(p)
            box += 1
            g.press('A')
        elif stall > 100:                           # waiting on something else (menu, choice): screenshot + A
            im = g.shot(); f = '%s/msgs/%s_%d_wait.png' % (OUT, mid, box); im.save(f); rec['shots'].append(f)
            g.press('A'); stall = 0
            if not menu and 'stuck' not in rec['flags']: rec['flags'].append('stuck')
    else:
        rec['flags'].append('timeout')
    if box != m['boxes'] and not menu: rec['flags'].append('boxes %d/%d' % (box, m['boxes']))
    return rec


def sheets(report):
    os.makedirs(OUT + '/sheets', exist_ok=True)
    groups = {}
    for r in report.values(): groups.setdefault(r['id'][:3], []).extend(r['shots'])
    for gname, shots in groups.items():
        if not shots: continue
        cols = 4; rows = (len(shots) + cols - 1) // cols
        sheet = Image.new('RGB', (cols * 244, rows * 176), (40, 40, 40)); d = ImageDraw.Draw(sheet)
        for i, f in enumerate(shots):
            x, y = (i % cols) * 244, (i // cols) * 176
            sheet.paste(Image.open(f), (x + 2, y + 14)); d.text((x + 4, y + 1), os.path.basename(f)[:-4], fill=(255, 255, 0))
        sheet.save('%s/sheets/%s.png' % (OUT, gname))


def main():
    args = sys.argv[1:]
    os.makedirs(OUT + '/msgs', exist_ok=True)
    global ROMB
    msgs = built_messages(); ROMB = open(ROM, 'rb').read()
    rep_path = OUT + '/report.json'
    report = json.load(open(rep_path)) if os.path.exists(rep_path) else {}
    if args == ['--failed']: ids = [k for k, r in report.items() if r['flags']]
    elif args: ids = [k for k in msgs if any(fnmatch.fnmatch(k, a) for a in args)]
    else: ids = sorted(msgs)
    g = GBA(ROM); t0 = time.time()
    for n, mid in enumerate(ids):
        for f in report.get(mid, {}).get('shots', []):
            if os.path.exists(f): os.remove(f)
        try:
            report[mid] = run_one(g, mid, msgs[mid])
        except RuntimeError as e:
            report[mid] = dict(id=mid, flags=['crash: %s' % e], shots=[]); g = GBA(ROM)
        if report[mid]['flags']: print(mid, report[mid]['flags'], flush=True)
        if n % 50 == 49:
            json.dump(report, open(rep_path, 'w'), indent=1)
            print('%d/%d  %.1f msg/s' % (n + 1, len(ids), (n + 1) / (time.time() - t0)), flush=True)
    g.close()
    json.dump(report, open(rep_path, 'w'), indent=1)
    sheets(report)
    bad = {k: r['flags'] for k, r in report.items() if r['flags']}
    print('done: %d messages, %d flagged' % (len(report), len(bad)))


if __name__ == '__main__':
    main()
