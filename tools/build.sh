#!/bin/zsh
# Build the English ROM + IPS patch from the current script/en.json.
cd "${0:A:h}/.."
set -e
.venv/bin/python tools/insert.py rocketslime.gba build/rocketslime_en.gba
.venv/bin/python tools/make_ips.py rocketslime.gba build/rocketslime_en.gba build/rocketslime_en.ips
