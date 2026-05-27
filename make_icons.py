#!/usr/bin/env python3
"""Generate PWA icons dan favicon dari sgo_resto.png"""
from PIL import Image
import os

src = 'sgo_resto.png'
img = Image.open(src).convert('RGBA')

# Buat icon-192.png
icon192 = img.resize((192, 192), Image.LANCZOS)
icon192.save('static/images/icon-192.png', 'PNG')
print("Created static/images/icon-192.png")

# Buat icon-512.png
icon512 = img.resize((512, 512), Image.LANCZOS)
icon512.save('static/images/icon-512.png', 'PNG')
print("Created static/images/icon-512.png")

# Buat favicon.ico (multi-size: 16, 32, 48)
favicon_sizes = [(16,16), (32,32), (48,48)]
favicon_imgs = [img.resize(s, Image.LANCZOS) for s in favicon_sizes]
favicon_imgs[0].save(
    'static/images/favicon.ico',
    format='ICO',
    sizes=favicon_sizes
)
print("Created static/images/favicon.ico")

# Buat apple-touch-icon.png (180x180)
apple = img.resize((180, 180), Image.LANCZOS)
apple.save('static/images/apple-touch-icon.png', 'PNG')
print("Created static/images/apple-touch-icon.png")

print("\nSemua icon berhasil dibuat!")
