"""(Re)create the save states the tests start from. Run after any build that changes RAM layout/graphics.

    .venv/bin/python tools/make_states.py            # English build  -> tests/states/*.st
    .venv/bin/python tools/make_states.py --ja       # original ROM   -> tests/states/ja_*.st

States:
  adventure_menu   file-select screen with a new save in slot 1 (hero "Rock"/default name)
  bubble           opening scene, one frame before Hooly's first speech bubble (message 009-000)
                   -> tools/msgtest.py injects any message here
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gba import GBA, MSG_START

ja = '--ja' in sys.argv
rom = 'rocketslime.gba' if ja else 'build/rocketslime_en.gba'
pre = 'tests/states/' + ('ja_' if ja else '')
os.makedirs('tests/states', exist_ok=True)

g = GBA(rom)
g.run(1500)                 # boot + intro logos; title accepts START after this
g.press('start', 5, 200)
g.press('A', 5, 300)        # slot 1 -> name entry
g.press('start', 5, 60)     # jump to OK
g.press('A', 5, 1100)       # accept default name, "Is ... OK?" -> Ok, back to file select
g.save(pre + 'adventure_menu.st')
g.press('A', 5, 30)         # Adventure
assert g.until(MSG_START, '/dev/null'), 'intro narration never started'
g.run(2)
assert g.until(MSG_START, pre + 'bubble.st'), 'first speech bubble never started'
g.close()
print('states written:', pre + 'adventure_menu.st', pre + 'bubble.st')
