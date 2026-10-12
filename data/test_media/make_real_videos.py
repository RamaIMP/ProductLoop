"""Builds video1/video2 from the brand-free base photo in source/ (portrait 720x1280, 24 fps, 8 s). Motion is synthetic. Needs ffmpeg."""
from PIL import Image, ImageDraw, ImageFilter, ImageChops
import math, random, os, subprocess, tempfile
rng = random.Random(21)
FPS, DUR, OW, OH = 24, 8, 720, 1280
tmp = tempfile.mkdtemp()
base = Image.open('source/shaver_base_clean.png').convert('RGB'); W, H = base.size
mask = Image.open('source/shaver_head_mask.png').convert('L')

# ---------- audio
def ff(*a): subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', *a], check=True)
ff('-f', 'lavfi', '-i', 'sine=f=110:d=6.5', '-f', 'lavfi', '-i', 'sine=f=220:d=6.5', '-f', 'lavfi', '-i', 'anoisesrc=d=6.5:c=pink:a=0.3', '-filter_complex',
   '[0][1]amix=inputs=2:normalize=0[h];[h]tremolo=f=24:d=0.85[t];[2]highpass=f=1200,tremolo=f=11:d=1[n];[t][n]amix=inputs=2:normalize=0,volume=1.8,afade=t=in:d=0.5,adelay=1500|1500,apad=whole_dur=8',
   '-t', '8', f'{tmp}/a1.wav')
ff('-f', 'lavfi', '-i', 'anoisesrc=d=8:c=pink:a=0.008', f'{tmp}/a2.wav')

# ---------- shared look: grain, vignette, handheld shake
vig = Image.new('L', (OW, OH), 0); vd = ImageDraw.Draw(vig)
for i in range(40):
    v = int(255 * (i / 40) ** 2.2 * 0.22); vd.ellipse((-OW*.3 + i*7, -OH*.2 + i*12, OW*1.3 - i*7, OH*1.2 - i*12), outline=None, fill=None)
vig = Image.radial_gradient('L').resize((OW, OH)).point(lambda v: int(max(0, v - 120) * 0.35))
dark = Image.new('RGB', (OW, OH), (10, 8, 6))
ph = [rng.uniform(0, 6.28) for _ in range(6)]
def shake(t): return (1.1*math.sin(2*math.pi*.7*t + ph[0]) + .5*math.sin(2*math.pi*1.9*t + ph[1]), 1.3*math.sin(2*math.pi*.6*t + ph[2]) + .5*math.sin(2*math.pi*2.1*t + ph[3]))
def look(frame):
    frame = Image.composite(dark, frame, vig)
    return Image.blend(frame, Image.effect_noise((OW, OH), 16).convert('RGB'), 0.05)
def window(im, cx, cy, z, t):
    sx, sy = shake(t); w, h = 280/z, 498/z
    x0 = min(max(cx - w/2 + sx, 0), im.width - w); y0 = min(max(cy - h/2 + sy, 0), im.height - h)
    return im.resize((OW, OH), Image.BICUBIC, box=(x0, y0, x0 + w, y0 + h))

# ---------- video 1: head wobbles once switched on
grown = mask.filter(ImageFilter.MaxFilter(7)); gm, bm = grown.load(), base.load()
plate = base.copy(); pp = plate.load()
Lc = {y: tuple(sum(base.getpixel((x, y))[i] for x in range(20, 33)) / 13 for i in range(3)) for y in range(0, 260)}
Rc = tuple(sum(base.getpixel((x, y))[i] for x in range(286, 299) for y in range(172, 179)) / 91 for i in range(3))
for x in range(W):
    ys = [y for y in range(H) if gm[x, y] > 30]
    if not ys: continue
    ybot = max(ys)
    for y in ys:
        if y < 170:
            u = (x - 30) / 270; l = Lc[y]; pp[x, y] = tuple(int(l[i]*(1-u) + Rc[i]*u + rng.uniform(-1.5, 1.5)) for i in range(3))
        else:
            pp[x, y] = bm[x, min(ybot + 4, H - 1)]
plate = plate.filter(ImageFilter.GaussianBlur(0.4))
head = base.convert('RGBA'); head.putalpha(mask)
PIV = (190, 235)
def wobble(t):
    a = min(1, max(0, (t - 1.5) / .6)) * min(1, max(0, (DUR - t) / .6))
    return (a * (3.2*math.sin(2*math.pi*6.2*t) + 1.2*math.sin(2*math.pi*13*t + .7)), a * 2.2*math.sin(2*math.pi*6.2*t + 1.1), a * 1.2*math.sin(2*math.pi*12.4*t))
def scene1(t):
    ang, dx, dy = wobble(t)
    hl = head.rotate(ang, center=PIV, resample=Image.BICUBIC).transform(head.size, Image.AFFINE, (1, 0, -dx, 0, 1, -dy), resample=Image.BICUBIC)
    out = plate.convert('RGBA'); out.alpha_composite(hl); return out.convert('RGB')
os.makedirs(f'{tmp}/f1'); os.makedirs(f'{tmp}/f2')
for i in range(FPS * DUR):
    t = i / FPS; z = 1 + .05 * t / DUR
    subs = [window(scene1(t + d), 160, 235, z, t + d) for d in (-.012, 0, .012)]
    f = Image.blend(Image.blend(subs[0], subs[1], .5), subs[2], .33)
    look(f).save(f'{tmp}/f1/{i:04d}.jpg', quality=93)

# ---------- video 2: cable plugged in, status lights stay dark
b2 = Image.open('source/shaver_base_leds_off.png').convert('RGB')
ext = Image.new('RGB', (W, H + 90)); ext.paste(b2, (0, 0))
strip = b2.crop((0, H - 30, W, H)); flip = strip.transpose(Image.FLIP_TOP_BOTTOM)
for j, piece in enumerate((flip, strip, flip)): ext.paste(piece, (0, H + 30 * j))
def scene2(t):
    k = min(1, max(0, (t - 1.0) / 1.3)); im = ext.copy(); d = ImageDraw.Draw(im)
    cy = 884 + (1 - k) * 60
    d.line([(178, cy + 14), (178, cy + 50), (186, 1010)], fill=(36, 36, 38), width=8)
    d.line([(176, cy + 14), (176, cy + 50), (184, 1010)], fill=(92, 92, 96), width=2)
    d.rounded_rectangle((167, cy + 2, 189, cy + 22), radius=3, fill=(46, 46, 49), outline=(96, 96, 100))
    return Image.blend(im.filter(ImageFilter.GaussianBlur(.4)), Image.effect_noise(im.size, 10).convert('RGB'), .03)
for i in range(FPS * DUR):
    t = i / FPS; s = min(1, max(0, (t - 2.5) / 3.0)); s = s*s*(3 - 2*s)
    z = 1 + .45 * s; cx = 160 + 18 * s; cy = 749 - 7 * s + 120 * (1 - s) * 0
    look(window(scene2(t), cx, cy, z, t)).save(f'{tmp}/f2/{i:04d}.jpg', quality=93)

for n, name, aud in (('f1', 'video1_loose_head_wobble.mp4', 'a1'), ('f2', 'video2_charging_led_off.mp4', 'a2')):
    ff('-framerate', str(FPS), '-i', f'{tmp}/{n}/%04d.jpg', '-i', f'{tmp}/{aud}.wav', '-c:v', 'libx264', '-crf', '20', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '96k', '-map_metadata', '-1', '-movflags', '+faststart', '-shortest', name)
print('done')
