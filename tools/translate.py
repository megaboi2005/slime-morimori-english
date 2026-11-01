"""Translate script/ja.json -> script/en.json with a local Ollama model.

Resumable: already-translated ids in en.json are skipped. Each message is split into
pages (text between {wait}/{clear}/{line}/{end}); the model only sees page text with
placeholders, never raw control codes, and output is validated before it is kept.

usage: python tools/translate.py [--model qwen3:8b] [--limit N] [--batch 8]
"""
import argparse, json, os, re, sys, time, urllib.request

OLLAMA = 'http://localhost:11434/api/chat'
PAGE_BREAK = re.compile(r'(\{wait\}|\{clear\}|\{line\}|\{end\}|\{waitsnd\})')

SYSTEM = """You are localizing the Japanese Game Boy Advance game "Slime MoriMori Dragon Quest"
(the prequel of the DS game "Dragon Quest Heroes: Rocket Slime") into English.
Style: like the official Dragon Quest / Rocket Slime English localization: natural, playful, concise.
Translate faithfully: keep the meaning, do not add or drop information.
Characters have verbal tics (スラ, でゴワス, でござる, っス, モジャ, でちゅ). スラ is just a cute slime ending: usually drop it.
Give other quirks a light English flavor (e.g. でござる -> old-fashioned samurai speech). Never append "slime" or "goo" to lines.
Glossary (official Dragon Quest names): スラリン=Rocket, しっぽ団=the Plob, スライム=slime, ゴールド=gold,\nスラ・ストライク=Elasto Blast, ばくだんいわ=Rockbomb, おおみみず=giant earthworm, ドラキー=Dracky,\nスーランの町=Slurrington, へんげのつえ=Morph Staff, おにいちゃん=mister (a kid addressing the hero).
Rules:
- Keep every placeholder exactly: [HERO] is the player's name; <cNN> ... </c> marks colored text — keep the tags around the translated words.
- Each input page becomes exactly one output page. Never merge or split pages.
- Keep each page short: at most about 100 characters (the text box is small).
- Plain ASCII only: no Japanese, no curly quotes, no em dashes, no markdown or asterisks, no new tags.
Return JSON: {"items":[{"id":"...","pages":["...", ...]}, ...]} with the same ids and page counts as the input."""


def to_pages(ja):
    """Split a decoded message into (skeleton, pages). Skeleton holds controls + page slots."""
    name = re.match(r'^\{name:[0-9a-f]+\}', ja)
    body = ja[name.end():] if name else ja
    parts = PAGE_BREAK.split(body)
    skel, pages = [], []
    if name: skel.append(name.group())
    for p in parts:
        if PAGE_BREAK.fullmatch(p) or p == '':
            if p: skel.append(p)
            continue
        txt = p.replace('\n', ' ').replace('「', '').replace('」', '')
        txt = txt.replace('{e}', '[HERO]')
        txt = re.sub(r'\{0c:00\}', '</c>', txt)
        txt = re.sub(r'\{0c:([0-9a-f]{2})\}', r'<c\1>', txt)
        txt = re.sub(r'\s+', ' ', txt).strip()
        if not txt or re.fullmatch(r'(\{[^}]*\}|\s)*', txt):
            skel.append(p)          # control-only chunk, keep verbatim
            continue
        skel.append('{page:%d}' % len(pages))
        pages.append(txt)
    return skel, pages


def placeholders(s):
    return sorted(re.findall(r'\[HERO\]|<c[0-9a-f]{2}>|</c>|\{[^}]*\}', s))


ASCII_FIX = {'…': '...', '‥': '..', '’': "'", '‘': "'", '“': '"', '”': '"', '—': '-', '–': '-',
             '。': '.', '、': ',', '！': '!', '？': '?', '～': '~', '〜': '~', '○': 'o', '♪': '~', '「': '', '」': ''}
# Common romaji leftovers that mean the model transliterated instead of translating.
ROMAJI = re.compile(r"\b(desu|masu|mashita|arigatou?|sugoi|nani|dake|shite|kudasai|janai|yatta|nanda|"
                    r"ze|zo|wa|yo|ne|ga|wo|ni|da|sa|kara|demo)\b(?![\w'])", re.I)


def clean(s):
    for k, v in ASCII_FIX.items(): s = s.replace(k, v)
    return re.sub(r'\s+', ' ', s).strip()


def repair(src, dst):
    """Drop colour tags the model invented on pages whose source has none."""
    if not isinstance(dst, list) or len(src) != len(dst): return dst
    return [re.sub(r'</?c[^>]*>', '', b) if isinstance(b, str) and '<c' not in a else b for a, b in zip(src, dst)]


def valid(src, dst):
    if not isinstance(dst, list) or len(src) != len(dst): return False
    for a, b in zip(src, dst):
        if not isinstance(b, str) or not b.strip(): return False
        b = clean(b)
        if placeholders(a) != placeholders(b): return False
        if not b.isascii(): return False
        if re.search(r'[<>*\[\]{}]', re.sub(r'\[HERO\]|<c[0-9a-f]{2}>|</c>', '', b)): return False
        if len(ROMAJI.findall(b)) >= 2: return False
    return True


def ask(model, items, glossary=None):
    user = json.dumps({'items': items}, ensure_ascii=False)
    if glossary:
        user = 'Names and terms in this batch (use exactly): ' + ', '.join('%s=%s' % kv for kv in glossary.items()) + '\n' + user
    body = {'model': model, 'stream': False, 'format': 'json',
            'options': {'temperature': 0.3, 'num_ctx': 4096, 'num_predict': 120 + 160 * len(items)},
            'messages': [{'role': 'system', 'content': SYSTEM},
                         {'role': 'user', 'content': user}]}
    if 'qwen3' in model: body['think'] = False
    req = urllib.request.Request(OLLAMA, json.dumps(body).encode(), {'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=600) as r:
        content = json.load(r)['message']['content']
    src = {it['id']: it['pages'] for it in items}
    return {it['id']: repair(src.get(it['id'], []), it.get('pages')) for it in json.loads(content).get('items', []) if 'id' in it}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--model', default='gemma3:12b')
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--batch', type=int, default=8)
    ap.add_argument('--out', default='script/en.json')
    ap.add_argument('--start', type=int, default=0)
    a = ap.parse_args()
    ja = json.load(open('script/ja.json', encoding='utf-8'))
    en_path = a.out
    en = json.load(open(en_path, encoding='utf-8')) if os.path.exists(en_path) else {}
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import nameplate
    names = json.load(open('script/names.json', encoding='utf-8'))
    terms = dict(names)
    if os.path.exists('script/glossary.json'): terms.update(json.load(open('script/glossary.json', encoding='utf-8')))
    def speaker(skel):
        m = re.match(r'\{name:([0-9a-f]+)\}', skel[0]) if skel else None
        return names.get(nameplate.decode(m.group(1))) if m else None
    def gloss(items):
        text = json.dumps(items, ensure_ascii=False)
        return {k: v for k, v in terms.items() if len(k) > 1 and k in text}
    todo = []
    for r in ja:
        if r['credits'] or r['id'] in en: continue
        skel, pages = to_pages(r['ja'])
        if not pages:
            en[r['id']] = {'skel': skel, 'pages': [], 'model': None}
            continue
        todo.append((r['id'], skel, pages))
    todo = todo[a.start:]
    if a.limit: todo = todo[:a.limit]
    print('%d messages to translate with %s' % (len(todo), a.model), flush=True)
    t0 = time.time(); done = 0
    for i in range(0, len(todo), a.batch):
        chunk = todo[i:i + a.batch]
        pending = {mid: (skel, pages) for mid, skel, pages in chunk}
        for attempt in range(3):
            if not pending: break
            items = [dict({'id': mid, 'pages': pages}, **({'speaker': speaker(skel)} if speaker(skel) else {}))
                     for mid, (skel, pages) in pending.items()]
            g = gloss([it['pages'] for it in items])
            if attempt == 2:   # last resort: one message per request
                for it in items:
                    try: res = ask(a.model, [it], g)
                    except Exception as e: print('  error', it['id'], e, flush=True); continue
                    if valid(it['pages'], res.get(it['id'])):
                        en[it['id']] = {'skel': pending[it['id']][0], 'pages': [clean(x) for x in res[it['id']]], 'model': a.model}
                        pending.pop(it['id'])
                break
            try: res = ask(a.model, items, g)
            except Exception as e: print('  error', e, flush=True); continue
            for mid in list(pending):
                if valid(pending[mid][1], res.get(mid)):
                    en[mid] = {'skel': pending[mid][0], 'pages': [clean(x) for x in res[mid]], 'model': a.model}
                    pending.pop(mid)
        for mid in pending: print('  FAILED', mid, flush=True)
        done += len(chunk)
        json.dump(en, open(en_path + '.tmp', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        os.replace(en_path + '.tmp', en_path)
        rate = done / (time.time() - t0)
        print('%d/%d  %.2f msg/s  eta %.0f min' % (done, len(todo), rate, (len(todo) - done) / rate / 60), flush=True)


if __name__ == '__main__':
    main()
