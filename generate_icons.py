"""Generate PWA icons untuk SGO"""
try:
    from PIL import Image, ImageDraw, ImageFont
    
    def create_icon(size):
        img = Image.new('RGB', (size, size), '#4A1D6E')
        draw = ImageDraw.Draw(img)
        
        # Background gradient effect
        for i in range(size):
            ratio = i / size
            r = int(74 + (45 - 74) * ratio)
            g = int(29 + (17 - 29) * ratio)
            b = int(110 + (66 - 110) * ratio)
            draw.line([(0, i), (size, i)], fill=(r, g, b))
        
        # Gold accent bar at top
        draw.rectangle([0, 0, size, size//16], fill='#F0A500')
        
        # Text "SGO"
        font_size = size // 4
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
        except:
            font = ImageFont.load_default()
        
        text = "SGO"
        bbox = draw.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        x = (size - text_w) // 2
        y = (size - text_h) // 2 - size//16
        
        draw.text((x, y), text, fill='#FFFFFF', font=font)
        
        # Subtitle
        sub_size = size // 10
        try:
            sub_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", sub_size)
        except:
            sub_font = ImageFont.load_default()
        
        sub_text = "Smart Guest Order"
        sub_bbox = draw.textbbox((0, 0), sub_text, font=sub_font)
        sub_w = sub_bbox[2] - sub_bbox[0]
        draw.text(((size - sub_w) // 2, y + text_h + size//20), sub_text, fill='#F0A500', font=sub_font)
        
        return img
    
    # Generate 192x192
    icon192 = create_icon(192)
    icon192.save('static/images/icon-192.png', 'PNG')
    print("Created icon-192.png")
    
    # Generate 512x512
    icon512 = create_icon(512)
    icon512.save('static/images/icon-512.png', 'PNG')
    print("Created icon-512.png")
    
except ImportError:
    print("Pillow tidak tersedia, buat icon manual")
    # Buat icon placeholder sederhana
    import struct, zlib
    
    def create_simple_png(size, color=(74, 29, 110)):
        """Buat PNG sederhana tanpa Pillow"""
        def png_chunk(chunk_type, data):
            c = chunk_type + data
            return struct.pack('>I', len(data)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)
        
        raw = b''
        for y in range(size):
            raw += b'\x00'
            for x in range(size):
                raw += bytes(color)
        
        compressed = zlib.compress(raw)
        
        png = b'\x89PNG\r\n\x1a\n'
        png += png_chunk(b'IHDR', struct.pack('>IIBBBBB', size, size, 8, 2, 0, 0, 0))
        png += png_chunk(b'IDAT', compressed)
        png += png_chunk(b'IEND', b'')
        return png
    
    with open('static/images/icon-192.png', 'wb') as f:
        f.write(create_simple_png(192))
    print("Created simple icon-192.png")
    
    with open('static/images/icon-512.png', 'wb') as f:
        f.write(create_simple_png(512))
    print("Created simple icon-512.png")
