"""Builds image1/image2 from the brand-free base photo in source/. Edits are synthetic overlays on a real product photo."""
from PIL import Image, ImageDraw, ImageFilter, ImageChops
import math, random
rng = random.Random(11)
base = Image.open('source/shaver_base_clean.png').convert('RGB')
headmask = Image.open('source/shaver_head_mask.png').convert('L')
FOILS = [((112,60),50,23), ((253,61),50,24), ((187,125),50,32)]   # centre, rx, ry (silver area seen in perspective)
BOX = (30,18,300,250); S = 4
SIZE = ((BOX[2]-BOX[0])*S, (BOX[3]-BOX[1])*S)
def tx(x, y): return ((x-BOX[0])*S, (y-BOX[1])*S)
def start(): return base.crop(BOX).resize(SIZE, Image.BICUBIC)
HM = headmask.crop(BOX).resize(SIZE, Image.BICUBIC).filter(ImageFilter.MinFilter(9))   # keep strokes inside the head
def ellipse_mask(scale):
    m = Image.new('L', SIZE, 0); d = ImageDraw.Draw(m)
    for (c, rx, ry) in FOILS:
        cx, cy = tx(*c); d.ellipse((cx-rx*S*scale, cy-ry*S*scale, cx+rx*S*scale, cy+ry*S*scale), fill=255)
    return m.filter(ImageFilter.GaussianBlur(2))
def finish(im, name):
    im = im.filter(ImageFilter.GaussianBlur(0.55))
    im = Image.blend(im, Image.effect_noise(im.size, 14).convert('RGB'), 0.045)
    im.save(name, quality=88); print('saved', name, im.size)

# ---- image 1: stray hair caught on the foils
im = start(); layer = Image.new('RGBA', SIZE, (0,0,0,0)); d = ImageDraw.Draw(layer)
def hair(x, y, length, heading):
    pts = [(x, y)]
    for _ in range(9):
        heading += rng.gauss(0, .22); x += length/9*math.cos(heading); y += length/9*math.sin(heading); pts.append((x, y))
    g = rng.randint(16, 52)
    d.line([tx(*p) for p in pts], fill=(g, g, max(0, g-3), rng.randint(175, 235)), width=rng.choice([1, 2, 2]), joint='curve')
for (c, rx, ry) in FOILS:
    for _ in range(70):                                        # loose strands over the silver surface
        t, k = rng.uniform(0, 6.28), rng.uniform(.15, 1.05)
        hair(c[0]+k*rx*math.cos(t), c[1]+k*ry*math.sin(t), rng.uniform(7, 22), rng.uniform(0, 6.28))
    for _ in range(5):                                         # clumps where hair collects, at the foil edge
        t = rng.uniform(0, 6.28); cx, cy = c[0]+rx*math.cos(t)*.98, c[1]+ry*math.sin(t)*.98
        for _ in range(16): hair(cx+rng.gauss(0, 2.5), cy+rng.gauss(0, 2), rng.uniform(5, 15), rng.uniform(0, 6.28))
layer = layer.filter(ImageFilter.GaussianBlur(0.5))
layer.putalpha(ImageChops.multiply(layer.getchannel('A'), HM))
finish(Image.alpha_composite(im.convert('RGBA'), layer).convert('RGB'), 'image1_hair_buildup_under_head.jpg')

# ---- image 2: dull, lightly scratched, worn foils
im = start().convert('RGBA'); wear = Image.new('RGBA', SIZE, (0,0,0,0)); wd = ImageDraw.Draw(wear)
for (c, rx, ry) in FOILS:
    cx, cy = tx(*c)
    wd.ellipse((cx-rx*S*.95, cy-ry*S*.95, cx+rx*S*.95, cy+ry*S*.95), fill=(112, 110, 106, 78))        # overall dulling
    for _ in range(13):                                        # patchy dull zones
        t, k = rng.uniform(0, 6.28), rng.uniform(0, .8); px, py = cx+k*rx*S*math.cos(t), cy+k*ry*S*math.sin(t); w = rng.uniform(9, 20)*S
        wd.ellipse((px-w, py-w*.45, px+w, py+w*.45), fill=(96, 94, 90, rng.randint(95, 160)))
    for _ in range(120):                                       # fine arc scratches following the foil rotation
        t0, k = rng.uniform(0, 6.28), rng.uniform(.2, .95); arc = rng.uniform(.15, .55); pts = []
        for i in range(7):
            t = t0 + arc*i/6; pts.append((cx+k*rx*S*math.cos(t), cy+k*ry*S*math.sin(t)))
        col = (245, 245, 242, rng.randint(130, 205)) if rng.random() < .6 else (50, 49, 47, rng.randint(110, 175))
        wd.line(pts, fill=col, width=rng.choice([1, 2]))
    for _ in range(16):                                        # a few pits
        t, k = rng.uniform(0, 6.28), rng.uniform(.1, .9); px, py = cx+k*rx*S*math.cos(t), cy+k*ry*S*math.sin(t)
        wd.ellipse((px-2.5, py-2.5, px+2.5, py+2.5), fill=(40, 38, 36, 210))
wear = wear.filter(ImageFilter.GaussianBlur(0.9))
wear.putalpha(ImageChops.multiply(wear.getchannel('A'), ellipse_mask(.96)))
finish(Image.alpha_composite(im, wear).convert('RGB'), 'image2_worn_blade_surface.jpg')
