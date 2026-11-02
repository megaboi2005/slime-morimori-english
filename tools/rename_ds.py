"""One-off: switch names to the official DS (Rocket Slime) localization. See issue #1.
Writes changed messages to script/fixes.json and updates names.json / glossary.json."""
import json, re
PLATES = {  # names.json: JA speaker -> new nameplate
 'グランじいさん':'Flanpa','しんぷ':'Curate Rollo','ドラお':'Swotsy','スラみ':'Bo','ドン・モジャール':'Don Clawleone',
 'シドもじゃ':'Ducktor Cid','トミー':'Tokyo Tom','スラまる':'Goosashi','スラかげ':'Gooshido','スクラテス':'Blingaling',
 'バブブ':'Mag Max','バブりん':'Soapia','スラッサー':'Goodith','スラげ':'Sliborg','スラネット':'Goozanna',
 'パパ':'Dad','ママ':'Mom','ホイミー':'Namby','ツリろう':'Flantenna','くろりん':'Count Dragoola','たまちゃん':'Gregg',
 'スーラ':'Gootrude','スラック':'Goolia','スラゾー':'Baron Blubba','スラックス':'Shelby','スラカンプ':'Merc',
 'ドラフィーユ':'Peewee','スラじろう':'Pebbles','スラのすけ':'Perry','モチャこ':'Plako','メカキチ':'Roboglop',
 'ホーミィ':'Pamby','スラのせき':'Duke Swellington','ぶちゴロウ':'Patch','ラスブーチン':'Splatrick','イワン':'Rocky',
 'バブルス':'Lord Lard','スラボックル':'Teeny','バットン':'Vladdy','バブすけ':'Bubbilly','ミニスラ':'Itsy',
 'ゴルド':'Jewelian','スラダーク':'Diablob','ミイホンパパ':'Mr. Hooly','ミイホンママ':'Mrs. Hooly','メテお':'Starthur',
 'アニキ':'Wiseguy','こぶん':'Taily','ホイスケ':'Dummy','ボーグル':'Slimechanic','スラや':'Dragory','タイオー':'Early Burly',
 'ぶちザベス':'Spot','バブルのやま':'Count Calories','ガブリエル':'Fangummy Bob','バブルーノ':'Sir Sudsy',
 'シルバ':'Crystal Chronicler','ドラゴーネ':'Dragorn','ブチじぃ':'Flopsy','ホイーチェ':'Tickled Pink','スラーリン':'Prince Pigummy',
 'ヒエール':'Blizzybody','モエール':'Flamethrower','テンシーラ':'Goobrielle','スラベル':'Curedon Bleu','ファンファン':'Clawdia',
 'スラト':'George','スラきち':'Splodgy Dave','おスラ':'Goopid','スラエル':'Rustle Sprout','ツリッキー':'Bud','グレン':'Drake',
 'マリン':'Winkles','ホイサッサ':'Curator','ホイップル':'Sheala','スライワー':'Stony','コンペー':'Plopstar','スライフ':'Cheruboing',
 'エッグル':'Eggbard','スラムリン':'Frankenslime','ボーグン':'Sliminator','ハガネンダー':'Earl Luminem','ブッチモンド':'Poxie',
 'ブチのすけ':'Speckles','オイスラー':'Michelle','マダラン':'Goochie','ゴールドベリー':'Flan Spinel','ぶっちい':'Patchy',
 'ミニー':'Weeny','エッグリーン':'Meggan','ホイミコ':'Tickles','ロック':'Kworry','スラワー':'Sliwer','ツムツム':'Stacky',
 'バブべえ':'Viscount Viscous','ファングリオ':'Clawrence','スラジョー':'Goofrey','ブッチーナ':'Patchina','モジャピン':'Plappin',
 'モジャオ':'Plajo','モジャラン':'Plakran','ロードン':'Wyrtoise','スラしょうりゅう':'Shoryuflan','スラフォード':'Flanford',
 'スラニオ':'Slanio',
}
TEXT = [  # dialogue: (regex, replacement), applied in order
 (r'King Slurrin VIII','Prince Pigummy'), (r"Hooly's Papa",'Mr. Hooly'), (r"Hooly's Mama",'Mrs. Hooly'),
 (r'\bPapa\b','Dad'), (r'\bMama\b','Mom'), (r'<c01>Gold</c>','<c01>Jewelian</c>'),
 (r'\bGrandpa\b','Flanpa'), (r'\bDraco\b','Swotsy'), (r'\bSlimey\b','Bo'), (r'\bDon Mojar\b','Don Clawleone'),
 (r'\bSidmoja\b','Ducktor Cid'), (r'\bTommy\b','Tokyo Tom'), (r'\bSlimaru\b','Goosashi'), (r'\bSlishadow\b','Gooshido'),
 (r'\bSlicrates\b','Blingaling'), (r'\bSlige\b','Sliborg'), (r'\bSlinette\b','Goozanna'), (r'\bFishro\b','Flantenna'),
 (r'\bSlizo\b','Baron Blubba'), (r'\bSlicamp\b','Merc'), (r'\bMochako\b','Plako'), (r'\bSlistone\b','Duke Swellington'),
 (r'\bBatton\b','Vladdy'), (r'\bSlidark\b','Diablob'), (r'\bMeteo\b','Starthur'), (r'\bHealsuke\b','Dummy'),
 (r'\bHiel\b','Blizzybody'), (r'\bMoell\b','Flamethrower'), (r'\bSlikichi\b','Splodgy Dave'), (r'\bKonpe\b','Plopstar'),
 (r'\bBogun\b','Sliminator'), (r'\bMojapin\b','Plappin'), (r'\bRoadon\b','Wyrtoise'),
 (r'\bthe Zoom Squad\b','the Goonin'), (r'\bZoom Squad\b','Goonin'),
 (r'\bNokke Forest\b','Nokke Woods'), (r'\bMt\. Melazoma\b','Mt. Merazoma'), (r'\bMelazoma\b','Merazoma'),
 (r'\bParched Spring\b','Cara-Cara Pool'), (r'\bWetotter\b','Ul-Otter'), (r'\bNikomiski\b','Nikomisky'),
 (r'\bSlurrington\b','Boingburg'), (r'\bMio Roshitaru\b','Mio Roshtar'), (r'\bTree of Happiness\b','Fortuitree'),
 (r'\bMonster Shop\b','Monster Mart'), (r'\bRoom of Heart\b','Mind Room'), (r'\bRoom of Skill\b','Skill Room'),
 (r'\bSlocker\b','Flanball'),
]
GLOSS = {'すっとび調査団':'Goonin','ノッケの森':'Nokke Woods','スーラン':'Boingburg','スーランビーチ':'Boingburg Beach',
 'メラゾマ火山':'Mt. Merazoma','カラカラ水源':'Cara-Cara Pool','ウルオッター川':'Ul-Otter River','ニコミスキー鉱山':'Nikomisky Mine',
 'ミオ・ロシタル':'Mio Roshtar','しあわせの木':'Fortuitree','まもの堂':'Monster Mart','心の部屋':'Mind Room','技の部屋':'Skill Room',
 'スッカー':'Flanball (the slime soccer game)','ドン・モジャール':'Don Clawleone','スラーリン8世':'Prince Pigummy'}

def sub(t):
    for a, b in TEXT: t = re.sub(a, b, t)
    return t

if __name__ == '__main__':
    en = json.load(open('script/en.json')); fx = json.load(open('script/fixes.json'))
    n = 0
    for k in sorted(set(en) | set(fx)):
        pages = fx[k] if k in fx else en[k]['pages']
        new = [sub(p) for p in pages]
        if new != pages: fx[k] = new; n += 1
    json.dump(fx, open('script/fixes.json', 'w'), ensure_ascii=False, indent=1)
    names = json.load(open('script/names.json'))
    for j, e in PLATES.items():
        assert j in names, j
        names[j] = e
    json.dump(names, open('script/names.json', 'w'), ensure_ascii=False, indent=1)
    g = json.load(open('script/glossary.json')); g.update(GLOSS)
    json.dump(g, open('script/glossary.json', 'w'), ensure_ascii=False, indent=1)
    print(n, 'messages changed')
