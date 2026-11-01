# Testing in the emulator

Every change to the script or graphics gets tested in mGBA before it's released.
Everything runs headless (no window) at ~40x real speed through `tools/harness/harness`
(libmgba) driven from Python by `tools/gba.py`.

## Quick reference

```sh
tools/build.sh                                   # build ROM + patch
.venv/bin/python tools/make_states.py            # regenerate start states (after any build)
.venv/bin/python tools/make_states.py --ja       #   ...and for the original ROM

.venv/bin/python tools/msgtest.py 064-019 010-*  # show messages in-game, check every box
.venv/bin/python tools/msgtest.py                # all 2,341 message slots (~25 min)
.venv/bin/python tools/msgtest.py --failed       # re-run only flagged ones
.venv/bin/python tools/msgtest.py --ja 049-001   # same message in the original ROM, to compare
```

Output: `tests/out/msgs/<id>_<box>.png` (one screenshot per text box), `tests/out/report.json`
(flags), `tests/out/sheets/<group>.png` (contact sheets). Japanese runs go to `tests/out_ja/`.

## How message testing works

Instead of playing to each line, the test loads `tests/states/bubble.st`, which is one frame before
Hooly's first speech bubble in the opening, and hijacks the call that starts it:

- `0x08095E18` starts a message (`r0` = group, `r1` = index). The harness `inject` command rewrites
  `r0`/`r1` the next time it runs, so any message plays in a real speech bubble.
- `0x0200118C` holds the current text pointer. The test knows a message has ended when this leaves the
  message's bytes.
- `0x020011A6` is the box state (1 = typing, 5 = paused). A box is complete when it is paused right
  after a `08` (end-of-box) code. That's when the screenshot is taken and A is pressed.

Flags in `report.json`:

| flag | meaning |
|---|---|
| `overflow` | text touches the right edge of the bubble |
| `boxes n/m` | n boxes shown, m expected from the `{wait}` codes |
| `stuck` | waited 300+ frames on something that isn't a menu prompt |
| `no_start` / `timeout` | message never started / never ended |

Some things only make sense in their real scene. For example, `{0d:00}` counters show blank when injected.
Compare with `--ja` before treating these as bugs.

## Starting anywhere: save states from the mGBA app

Play in the mGBA app (`/Applications/mGBA.app`), and press **Shift+F1..F9** to save a state wherever
you want a test to start, such as a dungeon, a shop or a minigame. Copy the `.ss1` file into
`tests/states/` and use it from Python:

```python
from gba import GBA
g = GBA('build/rocketslime_en.gba')
g.load('tests/states/nikomiski_mine.ss1')     # mGBA app states load directly
g.press('A'); g.run(120); g.shot().save('x.png')
g.save_ss('tests/states/x.ss2')               # and this one opens in the app
g.load_sav('my_game.sav')                     # or boot from a battery save (Adventure Log)
```

## Harness commands (`tools/harness/harness rom script|-`)

`run N keys` · `shot f.ppm` · `save/load f` (raw) · `savess/loadss f` (mGBA app format) · `loadsav f.sav` ·
`peek addr len` · `poke8/16/32 addr val` (RAM, or ROM patched in memory) · `brk addr` (log registers) ·
`watch addr` (log writes) · `inject addr skip r0 r1` · `until addr out.st` (tap A until addr runs; save the
frame before) · `quit`. With script `-` it reads commands from stdin and prints `ok` after each one.
