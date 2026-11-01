"""Human/Claude review of LLM translations, kept separate from en.json (the translator owns that file).

  rev.py show [N]          print the next N translated, unreviewed messages (JA pages vs EN pages)
  rev.py fix < fixes.json  validate {id: [pages]} against the Japanese and merge into script/fixes.json
  rev.py done ID1 ID2      mark the inclusive id range as reviewed
  rev.py stats
"""
import json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import translate as T
import nameplate

def load(p, d):
    return json.load(open(p, encoding='utf-8')) if os.path.exists(p) else d

def save(p, o):
    json.dump(o, open(p + '.tmp', 'w', encoding='utf-8'), ensure_ascii=False, indent=1); os.replace(p + '.tmp', p)

ja = {r['id']: r['ja'] for r in json.load(open('script/ja.json', encoding='utf-8')) if not r['credits']}
en = load('script/en.json', {})
fixes = load('script/fixes.json', {})
done = set(load('script/reviewed.json', []))
names = load('script/names.json', {})
cmd = sys.argv[1] if len(sys.argv) > 1 else 'show'

if cmd == 'show':
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 40
    for k in sorted(en):
        if k in done or not en[k]['pages']: continue
        m = re.match(r'\{name:([0-9a-f]+)\}', ja[k])
        spk = names.get(nameplate.decode(m.group(1)), '?') if m else ''
        print('#%s %s' % (k, spk))
        print(' JA: ' + ' | '.join(T.to_pages(ja[k])[1]))
        print(' EN: ' + ' | '.join(fixes.get(k, en[k]['pages'])))
        n -= 1
        if not n: break
elif cmd == 'fix':
    new = json.load(sys.stdin)
    bad = []
    for k, pages in new.items():
        pages = [T.clean(p) for p in pages]
        if T.valid(T.to_pages(ja[k])[1], pages): fixes[k] = pages
        else: bad.append(k)
    save('script/fixes.json', fixes)
    print('saved %d fixes%s' % (len(new) - len(bad), ('; INVALID: ' + ' '.join(bad)) if bad else ''))
elif cmd == 'done':
    a, b = sys.argv[2], sys.argv[3]
    done |= {k for k in en if a <= k <= b and en[k]['pages']}
    save('script/reviewed.json', sorted(done)); print('reviewed', len(done))
elif cmd == 'stats':
    print('translated %d, reviewed %d, fixes %d' % (sum(1 for v in en.values() if v['pages']), len(done), len(fixes)))
