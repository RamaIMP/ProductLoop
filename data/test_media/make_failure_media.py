"""Builds video3_head_detaches.mp4 and image3_cracked_casing.jpg from the brand-free base photo in source/.
Run from data/test_media/: python3 make_failure_media.py   (needs ffmpeg). Motion, crack and sound are synthetic."""
import math, os, random, subprocess, tempfile
from PIL import Image, ImageChops, ImageDraw, ImageFilter

rng = random.Random(33)
base = Image.open('source/shaver_base_clean.png').convert('RGB'); W, H = base.size
mask = Image.open('source/shaver_head_mask.png').convert('L')
tmp = tempfile.mkdtemp()
def ff(*a): subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', *a], check=True)

# =============================== IMAGE: cracked casing ===============================
BOX, S = (60, 200, 300, 440), 5
SIZE = ((BOX[2] - BOX[0]) * S, (BOX[3] - BOX[1]) * S)
img = base.crop(BOX).resize(SIZE, Image.BICUBIC)
gray = img.convert('L')
casing = gray.point(lambda v: 255 if v < 150 else 0).filter(ImageFilter.MinFilter(9)).filter(ImageFilter.GaussianBlur(3))   # keep the crack on the plastic only

def crack_path(x, y, heading, length, wander=.22, step=10):
    pts, off = [(x, y)], 0.0
    for _ in range(int(length / step)):
        off = off * .8 + rng.gauss(0, wander)                      # mean-reverting, so the crack keeps its general direction
        x += step * math.cos(heading + off); y += step * math.sin(heading + off); pts.append((x, y))
    return pts
H0 = math.radians(62)
main = crack_path(350, 320, H0, 560)
branches = []
for k in (6, 12, 19, 27, 35, 44):
    if k < len(main):
        bx, by = main[k]; side = rng.choice([-1, 1])
        branches.append(crack_path(bx, by, H0 + side * rng.uniform(.55, 1.0), rng.uniform(70, 190), wander=.3, step=8))
halo = Image.new('L', SIZE, 0); lite = Image.new('RGBA', SIZE, (0, 0, 0, 0)); gap = Image.new('RGBA', SIZE, (0, 0, 0, 0))
hd, ld, gd = ImageDraw.Draw(halo), ImageDraw.Draw(lite), ImageDraw.Draw(gap)
for i, p in enumerate([main] + branches):
    w = 4 if i == 0 else 3
    for a_, b_ in zip(p, p[1:]):
        hd.line([a_, b_], fill=110, width=w * 5)
        gd.line([(a_[0] + 2, a_[1] + 1), (b_[0] + 2, b_[1] + 1)], fill=(0, 0, 0, 255), width=w)                   # the open gap
        ld.line([(a_[0] - 1, a_[1] - 1), (b_[0] - 1, b_[1] - 1)], fill=(214, 214, 208, 235), width=max(2, w - 1))  # lit broken edge
halo = halo.filter(ImageFilter.GaussianBlur(7))
img = Image.composite(Image.new('RGB', SIZE, (150, 150, 146)), img, ImageChops.multiply(halo, casing).point(lambda v: int(v * .5)))     # stress whitening
for layer in (gap, lite):
    img = Image.alpha_composite(img.convert('RGBA'), Image.composite(layer.filter(ImageFilter.GaussianBlur(.7)), Image.new('RGBA', SIZE, (0, 0, 0, 0)), casing)).convert('RGB')
img = Image.blend(img.filter(ImageFilter.GaussianBlur(.6)), Image.effect_noise(SIZE, 14).convert('RGB'), .045)
img.save('image3_cracked_casing.jpg', quality=88); print('image3_cracked_casing.jpg', img.size)

# =============================== VIDEO: head detaches ===============================
FPS, DUR, OW, OH = 24, 8, 720, 1280
T_ON, T_OFF = 1.5, 4.0                       # switched on; head comes off
ff('-f', 'lavfi', '-i', 'sine=f=110:d=2.6', '-f', 'lavfi', '-i', 'sine=f=220:d=2.6', '-f', 'lavfi', '-i', 'anoisesrc=d=2.6:c=pink:a=0.3',
   '-f', 'lavfi', '-i', 'anoisesrc=d=0.12:c=white:a=0.9', '-f', 'lavfi', '-i', 'sine=f=320:d=4.0', '-filter_complex',
   '[0][1]amix=inputs=2:normalize=0,tremolo=f=24:d=0.85[t];[2]highpass=f=1200,tremolo=f=11:d=1[n];[t][n]amix=inputs=2:normalize=0,volume=1.8,afade=t=in:d=2.0,adelay=1500|1500[r];'
   '[3]lowpass=f=2500,afade=t=out:d=0.1,adelay=4000|4000[c];[4]tremolo=f=6:d=0.2,volume=0.22,afade=t=in:d=0.2,adelay=4100|4100[w];'
   '[r][c][w]amix=inputs=3:normalize=0,apad=whole_dur=8', '-t', '8', f'{tmp}/a.wav')

vig = Image.radial_gradient('L').resize((OW, OH)).point(lambda v: int(max(0, v - 120) * .35)); dark = Image.new('RGB', (OW, OH), (10, 8, 6))
ph = [rng.uniform(0, 6.28) for _ in range(6)]
shake = lambda t: (1.1*math.sin(2*math.pi*.7*t + ph[0]) + .5*math.sin(2*math.pi*1.9*t + ph[1]), 1.3*math.sin(2*math.pi*.6*t + ph[2]) + .5*math.sin(2*math.pi*2.1*t + ph[3]))
look = lambda f: Image.blend(Image.composite(dark, f, vig), Image.effect_noise((OW, OH), 16).convert('RGB'), .05)
def window(im, cx, cy, z, t):
    sx, sy = shake(t); w, h = 280/z, 498/z
    x0 = min(max(cx - w/2 + sx, 0), im.width - w); y0 = min(max(cy - h/2 + sy, 0), im.height - h)
    return im.resize((OW, OH), Image.BICUBIC, box=(x0, y0, x0 + w, y0 + h))

PIV = (190, 235)
# plate: the shaver with the head area removed, so the head can be a separate moving layer
bm, gm, gmh = base.load(), mask.filter(ImageFilter.MaxFilter(9)).load(), mask.filter(ImageFilter.MaxFilter(17)).load()
plate = base.copy(); pp = plate.load()
for x in range(W):                                                       # below the head: continue the colour found just under it (body and sleeve)
    ys = [y for y in range(H) if gm[x, y] > 30]
    if not ys: continue
    ybot = max(ys)
    for y in ys: pp[x, y] = bm[x, min(ybot + 4, H - 1)]
def under(x):
    ys = [y for y in range(H) if gm[x, y] > 30]
    return bm[x, min(max(ys) + 6, H - 1)] if ys else None
def neutral_bright(px): return px is not None and max(px) - min(px) < 9 and sum(px) / 3 > 160     # white metal ring, not the tinted background
RX0 = RX1 = next(x for x in (150, 140, 160, 130, 170, 120, 180, 110) if neutral_bright(under(x)))
while neutral_bright(under(RX0 - 1)): RX0 -= 1                           # the unbroken run of white-ring columns around the head's centre
while neutral_bright(under(RX1 + 1)): RX1 += 1
CAP_Y = 192
print('sleeve columns', RX0, RX1)
hole = Image.new('L', (W, H), 0); hp = hole.load()
for x in range(W):
    for y in range(CAP_Y):
        if gmh[x, y] > 30: hp[x, y] = 255                                # everything the head covered above the sleeve top: background to rebuild
keep = hole.point(lambda v: 255 - v)
fill = plate.copy(); fp = fill.load()
mean = tuple(int(sum(bm[x, y][i] for x in range(0, 20) for y in range(10, 150)) / (20 * 140)) for i in range(3))
for x in range(W):
    for y in range(CAP_Y):
        if hp[x, y]: fp[x, y] = mean
for radius, rounds in ((30, 25), (12, 40), (5, 60), (2, 40)):          # diffuse the surroundings into the hole: big blur first, then finer
    for _ in range(rounds):
        fill = Image.composite(plate, fill.filter(ImageFilter.BoxBlur(radius)), keep)
grain = Image.blend(fill, Image.effect_noise((W, H), 30).convert('RGB'), .11)
plate = Image.composite(grain, plate, hole.filter(ImageFilter.GaussianBlur(1.2)))
pd = ImageDraw.Draw(plate)
pd.ellipse((RX0, CAP_Y - 15, RX1, CAP_Y + 15), fill=(214, 216, 220), outline=(120, 122, 128), width=2)   # top of the exposed shaft sleeve
cx = (RX0 + RX1) // 2; rw = (RX1 - RX0) // 2
pd.ellipse((cx - rw * .55, CAP_Y - 8, cx + rw * .55, CAP_Y + 8), fill=(150, 152, 158), outline=(80, 82, 88), width=1)
pd.ellipse((cx - rw * .18, CAP_Y - 4, cx + rw * .18, CAP_Y + 4), fill=(70, 72, 78))
plate = plate.filter(ImageFilter.GaussianBlur(.4))
head = base.convert('RGBA'); head.putalpha(mask); PIV = (190, 235)

def pose(t):
    """(angle, dx, dy): wobble that grows after switch-on, a lift-and-fling at T_OFF, then the head is gone."""
    if t < T_ON: return 0, 0, 0
    if t < T_OFF:
        g = ((t - T_ON) / (T_OFF - T_ON)) ** 1.6; a = .35 + 1.65 * g
        return a*(3.4*math.sin(2*math.pi*6.2*t) + 1.2*math.sin(2*math.pi*13*t + .7)), a*(3*math.sin(2*math.pi*6.1*t + .5)) + g*5, a*(2.2*math.sin(2*math.pi*6.2*t + 1.1)) - g*7
    s = t - T_OFF                                                                       # flight: lift, throw right, fall
    return 420*s*(1 + .6*s), 40*s*3.1 + 24*s*s, -60*s + 170*s*s
def scene(t):
    ang, dx, dy = pose(t); out = plate.convert('RGBA')
    if abs(dx) < 420 and dy < 600:
        hl = head.rotate(ang, center=PIV, resample=Image.BICUBIC).transform(head.size, Image.AFFINE, (1, 0, -dx, 0, 1, -dy), resample=Image.BICUBIC)
        out.alpha_composite(hl)
    return out.convert('RGB')
os.makedirs(f'{tmp}/f')
for i in range(FPS * DUR):
    t = i / FPS; z = 1 + .04 * t / DUR
    subs = [window(scene(t + d), 160, 235, z, t + d) for d in (-.012, 0, .012)]
    look(Image.blend(Image.blend(subs[0], subs[1], .5), subs[2], .33)).save(f'{tmp}/f/{i:04d}.jpg', quality=93)
ff('-framerate', str(FPS), '-i', f'{tmp}/f/%04d.jpg', '-i', f'{tmp}/a.wav', '-c:v', 'libx264', '-crf', '20', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '96k',
   '-map_metadata', '-1', '-movflags', '+faststart', '-shortest', 'video3_head_detaches.mp4')
print('video3_head_detaches.mp4 done')
