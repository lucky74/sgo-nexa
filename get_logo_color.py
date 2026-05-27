#!/usr/bin/env python3
"""Ekstrak warna dominan dari logo SGO Resto"""
from PIL import Image
import collections

img = Image.open('sgo_resto.png').convert('RGB')
img = img.resize((100, 100))  # resize untuk speed

pixels = list(img.getdata())
# Filter out near-white and near-black
filtered = [(r,g,b) for r,g,b in pixels if not (r>200 and g>200 and b>200) and not (r<30 and g<30 and b<30)]

counter = collections.Counter(filtered)
top_colors = counter.most_common(5)

print("Warna dominan di logo:")
for color, count in top_colors:
    hex_color = '#{:02x}{:02x}{:02x}'.format(*color)
    print(f"  {hex_color} - RGB{color} ({count} pixels)")
