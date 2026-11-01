# Slime MoriMori Dragon Quest – English Translation
## SLOP CODED!!!!!!!

Fan translation patch for **Slime MoriMori Dragon Quest: Shōgeki no Shippo Dan** (Game Boy Advance, Japan, 2003).

Friend wanted a translation patch for it and so I deployed claude and local LLMS on it on my m4 mac mini. I am not a fan of vibe coding and vibe coders piss me off with how tech illiterate they are but I am all for this kind of thing because some games get locked behind localization and it's not cool. This seriously took like 15-24 hours of claude pro. Issues will go straight to claude and claude will push out a fix and test it whenever my m4 is running.

## Download & patching

1. Download `rocketslime_en.ips` from the [Releases](../../releases) page.
2. Apply it to your own dump of the Japanese ROM with any IPS patcher (e.g. [Rom Patcher JS](https://www.marcrobledo.com/RomPatcher.js/), Floating IPS, Lunar IPS).

Required ROM:

| | |
|---|---|
| Game code | `A9KJ` |
| SHA-1 | `2aed7c064911cd726cbfccf0131da69caa27f48f` |
| Size | 8 MB (patched ROM is 16 MB) |

This repository does **not** contain or link to any ROMs.

## What's translated

- [x] All dialogue: 2,162 messages, including NPCs, story, tutorials, shops, minigames, letters and the monster/item encyclopedia
- [x] Speaker nameplates
- [x] Staff credits
- [x] Title logo: "SLIME / MORI MORI / DRAGON QUEST / THE PLOB ATTACK!"
- [x] File select / Adventure Log screens and save dialogs
- [x] Name entry buttons (default hero name: **Rock**)
- [x] Elasto Blast tutorial screen
- [x] Pot Crash minigame logo
- [x] Yes/No choice boxes (shown as **Ok/No**; the box is too narrow for "Yes")
- [ ] Name entry hint ticker (still Japanese; the name entry keyboard has an English page)

## Translation rules

These are the conventions used across the script. Please follow them in fixes and suggestions.

**Names**
- Character, place and item names follow the official English localization (*Rocket Slime*, DS) where it exists: Slurrington, Plob, Hooly, Drahart Jr, Don Mojar, Elasto Blast, Mt. Melazoma, and so on.
- The hero's default name is **Rock**. The NPC ロック is **Rocco**.
- Full lists are in [`script/names.json`](script/names.json) (speakers) and [`script/glossary.json`](script/glossary.json) (terms).

**Style**
- Write natural English for a Western reader, not a literal translation.
- Drop Japanese verbal tics and honorifics (〜モジャ, 〜ンテス, 〜ギャ, 〜タコ, 〜どの, せんぱい…).
- Keep tics that already work as English sound effects ("clank", "swish", "stinky", "hop").
- Keep personalities distinct: baby-talk kids, Bubsuke's country drawl, Slikichi's salesman patter, Golemus's ALL-CAPS robot voice, the Mummy's ALL-CAPS broken speech, slurred drunk lines.
- Localize jokes and puns rather than footnoting them, e.g. しっぽ団 "Tail Gang" → the **Plob**, who wear tails.
- Keep it kid-friendly.

**Technical limits**
- Speech bubbles hold **2 lines of ~176 px**. Longer text automatically continues in a new box.
- Prompts that open a menu (`{0a:xx}` at the end) must fit in **one** box.
- Keep every code exactly as it appears on each page: `[HERO]`, `<c01>…</c>` (colour), `{0d:00}` (number), `{name:…}` (speaker change).
- ASCII only. The font has no curly quotes, `;`, `*` or `&`.

## Reporting a problem

Open an issue with:
- a screenshot or photo of the text,
- what's wrong (typo, mistranslation, confusing, overflowing box…),
- roughly where in the game you are.

## Building from source

Requires Python 3, Pillow, and your own Japanese ROM saved as `rocketslime.gba` in the repo root.

```sh
python3 -m venv .venv && .venv/bin/pip install pillow capstone
.venv/bin/python tools/dump.py          # extracts script/ja.json from your ROM
tools/build.sh                          # writes build/rocketslime_en.gba + .ips
```

Corrections go in [`script/fixes.json`](script/fixes.json), which overrides the base translation in `script/en.json`.

This is an unofficial fan project and is not affiliated with Square Enix. Dragon Quest is a trademark of Square Enix.
