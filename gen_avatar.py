from PIL import Image, ImageDraw
import os

size = 128
img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

for y in range(size):
    for x in range(size):
        cx, cy = x - size//2, y - size//2
        if cx*cx + cy*cy <= (size//2)*(size//2):
            r = int(112 + (168-112) * x / size)
            g = int(142 + (85-142) * x / size)
            b = int(234 + (247-234) * x / size)
            img.putpixel((x, y), (r, g, b, 255))

draw.ellipse([42, 22, 86, 66], fill=(255, 255, 255, 230))
draw.ellipse([26, 72, 102, 132], fill=(255, 255, 255, 230))

out = r'G:\gutaipan\易语言\易语言源码区\自己用的还有个动态图工具\DingDanGuanLi\app\static\img\avatar.png'
img.save(out, 'PNG')
print('OK')
