# -*- coding: utf-8 -*-
#!/usr/bin/env python3
"""
Restore semua emoji yang hilang di main.py
Jalankan di WSL: python restore_all_emoji.py
"""

filepath = '/mnt/c/Users/user/Desktop/SGO_Nexa/main.py'

with open(filepath, 'r', encoding='utf-8-sig') as f:
    src = f.read()

print("File loaded, chars: {}".format(len(src)))

# Gunakan unicode escape agar tidak ada masalah encoding file ini
FIXES = [
    # Emoji yang rusak (mojibake) -> emoji benar (unicode escape)
    ('\u00f0\u009f\u008d\u00bd\u00ef\u00b8\u008f', '\U0001F37D\uFE0F'),  # dish with cutlery
    ('\u00f0\u009f\u009b\u00b5', '\U0001F6B5'),   # scooter
    ('\u00f0\u009f\u0093\u0088', '\U0001F4C8'),   # chart up
    ('\u00f0\u009f\u0093\u0089', '\U0001F4C9'),   # chart down
    ('\u00f0\u009f\u0093\u0085', '\U0001F4C5'),   # calendar
    ('\u00f0\u009f\u0094\u00a5', '\U0001F525'),   # fire
    ('\u00f0\u009f\u0091\u008d', '\U0001F44D'),   # thumbs up
    ('\u00f0\u009f\u0092\u00aa', '\U0001F4AA'),   # muscle
    ('\u00f0\u009f\u0098\u00b4', '\U0001F634'),   # sleeping
    ('\u00f0\u009f\u008f\u00aa', '\U0001F3EA'),   # convenience store
    ('\u00f0\u009f\u0097\u0091\u00ef\u00b8\u008f', '\U0001F5D1\uFE0F'),  # wastebasket
    ('\u00f0\u009f\u0093\u00a6', '\U0001F4E6'),   # package
    ('\u00f0\u009f\u0097\u00ba\u00ef\u00b8\u008f', '\U0001F5FA\uFE0F'),  # world map
    ('\u00f0\u009f\u0093\u00b1', '\U0001F4F1'),   # mobile phone
    ('\u00f0\u009f\u0093\u008d', '\U0001F4CD'),   # round pushpin
    ('\u00f0\u009f\u00a5\u0087', '\U0001F947'),   # gold medal
    ('\u00f0\u009f\u00a5\u0088', '\U0001F948'),   # silver medal
    ('\u00f0\u009f\u00a5\u0089', '\U0001F949'),   # bronze medal
    ('\u00e2\u009c\u0085', '\u2705'),             # check mark
    ('\u00e2\u009d\u008c', '\u274C'),             # cross mark
    ('\u00e2\u009a\u00a0\u00ef\u00b8\u008f', '\u26A0\uFE0F'),  # warning
    ('\u00e2\u009a\u00a0', '\u26A0'),             # warning (no variation)
    ('\u00e2\u0094\u0080', '\u2500'),             # box drawing light horizontal
    ('\u00e2\u0094\u0082', '\u2502'),             # box drawing light vertical
    ('\u00f0\u009f\u0094\u0094', '\U0001F514'),   # bell
    ('\u00f0\u009f\u008d\u00b3', '\U0001F373'),   # cooking
    ('\u00f0\u009f\u009a\u00b4', '\U0001F6B4'),   # cyclist
    ('\u00e2\u00ad\u0090', '\u2B50'),             # star (already fixed but just in case)
    ('\u00e2\u0084\u00b9\u00ef\u00b8\u008f', '\u2139\uFE0F'),  # info
    ('\u00e2\u0084\u00b9', '\u2139'),             # info (no variation)
    ('\u00e2\u00b3\u00a3', '\u2B50'),             # another star variant
    ('\u00f0\u009f\u0093\u00a3', '\U0001F4E3'),   # megaphone
    ('\u00f0\u009f\u0094\u0094', '\U0001F514'),   # bell
    ('\u00f0\u009f\u0093\u008a', '\U0001F4CA'),   # bar chart
    ('\u00f0\u009f\u0093\u009d', '\U0001F4DD'),   # memo
    ('\u00f0\u009f\u0097\u0082\u00ef\u00b8\u008f', '\U0001F5C2\uFE0F'),  # card index dividers
    ('\u00f0\u009f\u0093\u00b0', '\U0001F4F0'),   # newspaper
    ('\u00f0\u009f\u0094\u00a7', '\U0001F527'),   # wrench
    ('\u00f0\u009f\u0094\u00a8', '\U0001F528'),   # hammer
    ('\u00f0\u009f\u0094\u00b0', '\U0001F530'),   # Japanese symbol
    ('\u00f0\u009f\u0094\u00b1', '\U0001F531'),   # trident
    ('\u00f0\u009f\u0094\u00b2', '\U0001F532'),   # black square button
    ('\u00f0\u009f\u0094\u00b3', '\U0001F533'),   # white square button
    ('\u00f0\u009f\u0094\u00b4', '\U0001F534'),   # red circle
    ('\u00f0\u009f\u0094\u00b5', '\U0001F535'),   # blue circle
    ('\u00f0\u009f\u0094\u00b6', '\U0001F536'),   # large orange diamond
    ('\u00f0\u009f\u0094\u00b7', '\U0001F537'),   # large blue diamond
    ('\u00f0\u009f\u0094\u00b8', '\U0001F538'),   # small orange diamond
    ('\u00f0\u009f\u0094\u00b9', '\U0001F539'),   # small blue diamond
    ('\u00f0\u009f\u0094\u00ba', '\U0001F53A'),   # red triangle up
    ('\u00f0\u009f\u0094\u00bb', '\U0001F53B'),   # red triangle down
    ('\u00f0\u009f\u0094\u00bc', '\U0001F53C'),   # up button
    ('\u00f0\u009f\u0094\u00bd', '\U0001F53D'),   # down button
    ('\u00f0\u009f\u0094\u00be', '\U0001F53E'),   # keycap
    ('\u00f0\u009f\u0094\u00bf', '\U0001F53F'),   # keycap
    ('\u00f0\u009f\u0094\u0080', '\U0001F500'),   # shuffle
    ('\u00f0\u009f\u0094\u0081', '\U0001F501'),   # repeat
    ('\u00f0\u009f\u0094\u0082', '\U0001F502'),   # repeat once
    ('\u00f0\u009f\u0094\u0083', '\U0001F503'),   # clockwise
    ('\u00f0\u009f\u0094\u0084', '\U0001F504'),   # counterclockwise
    ('\u00f0\u009f\u0094\u0085', '\U0001F505'),   # dim button
    ('\u00f0\u009f\u0094\u0086', '\U0001F506'),   # bright button
    ('\u00f0\u009f\u0094\u0087', '\U0001F507'),   # muted speaker
    ('\u00f0\u009f\u0094\u0088', '\U0001F508'),   # speaker low
    ('\u00f0\u009f\u0094\u0089', '\U0001F509'),   # speaker medium
    ('\u00f0\u009f\u0094\u008a', '\U0001F50A'),   # speaker high
    ('\u00f0\u009f\u0094\u008b', '\U0001F50B'),   # battery
    ('\u00f0\u009f\u0094\u008c', '\U0001F50C'),   # electric plug
    ('\u00f0\u009f\u0094\u008d', '\U0001F50D'),   # magnifying glass left
    ('\u00f0\u009f\u0094\u008e', '\U0001F50E'),   # magnifying glass right
    ('\u00f0\u009f\u0094\u008f', '\U0001F50F'),   # locked with pen
    ('\u00f0\u009f\u0094\u0090', '\U0001F510'),   # locked with key
    ('\u00f0\u009f\u0094\u0091', '\U0001F511'),   # key
    ('\u00f0\u009f\u0094\u0092', '\U0001F512'),   # locked
    ('\u00f0\u009f\u0094\u0093', '\U0001F513'),   # unlocked
    ('\u00f0\u009f\u0094\u0094', '\U0001F514'),   # bell
    ('\u00f0\u009f\u0094\u0095', '\U0001F515'),   # no bell
    ('\u00f0\u009f\u0094\u0096', '\U0001F516'),   # bookmark
    ('\u00f0\u009f\u0094\u0097', '\U0001F517'),   # link
    ('\u00f0\u009f\u0094\u0098', '\U0001F518'),   # radio button
    ('\u00f0\u009f\u0094\u0099', '\U0001F519'),   # back arrow
    ('\u00f0\u009f\u0094\u009a', '\U0001F51A'),   # end arrow
    ('\u00f0\u009f\u0094\u009b', '\U0001F51B'),   # on arrow
    ('\u00f0\u009f\u0094\u009c', '\U0001F51C'),   # soon arrow
    ('\u00f0\u009f\u0094\u009d', '\U0001F51D'),   # top arrow
    ('\u00f0\u009f\u0094\u009e', '\U0001F51E'),   # no one under 18
    ('\u00f0\u009f\u0094\u009f', '\U0001F51F'),   # keycap 10
]

total = 0
for old, new in FIXES:
    if old in src:
        count = src.count(old)
        src = src.replace(old, new)
        total += count
        print("Fixed {}x: {} -> {}".format(count, repr(old[:8]), new))

print("\nTotal: {} fixes".format(total))

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(src)

print("Saved!")

# Verifikasi syntax
import ast
try:
    ast.parse(src)
    print("Syntax OK")
except SyntaxError as e:
    print("Syntax ERROR: {}".format(e))

# Cek emoji penting
print("\n=== Verifikasi ===")
important = [
    ('\U0001F37D', 'dish'),
    ('\U0001F4F1', 'phone'),
    ('\U0001F4CD', 'pin'),
    ('\U0001F3EA', 'store'),
    ('\U0001F4C5', 'calendar'),
    ('\u274C', 'cross'),
    ('\u26A0', 'warning'),
    ('\U0001F514', 'bell'),
    ('\U0001F947', 'gold'),
    ('\U0001F948', 'silver'),
    ('\U0001F949', 'bronze'),
    ('\u2705', 'check'),
    ('\u2B50', 'star'),
]
for emoji, name in important:
    count = src.count(emoji)
    print("  {}: {} {}x".format(name, emoji, count))
