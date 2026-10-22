#!/usr/bin/env python3
"""The Acid skin's "3D module" art, in the manner of the 303 circuit-model plugin's skin (mpc-vst-plugins SKIN_STUDIO
"Realistic hardware skins"), keeping Acid's layout and colours:

    images/module_bg.png       the yellow panel as a slab: painted grain, light from the top left, a bevelled rim, screws
    images/panel_<w>x<h>.png   each frame's charcoal panel recessed into it (frame img=; the title rule baked in)
    images/knob_strip.png      the knobs: 64 frames, lit from a fixed light (only the pointer and the cap's chamfer turn),
                               Acid's orange value arc round them, over the renderer's 270 degrees

    python3 vst/make_module_art.py          # from the repo root; needs Pillow

The layout uses them through art file=, frame img= and knob_strip= (layout.conf)."""
import math
import os
import re

from PIL import Image, ImageChops, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
IMG = os.path.join(HERE, "images")
SS = 3                           # drawn at 3x, saved at 1x (knobs: kept at 2x for the renderer to scale down)
W, H = 1280, 628
YELLOW = (245, 196, 0)
CHARCOAL = (31, 31, 31)
ARC = (214, 74, 40)              # the knobs' value arc (Acid's)
RED = (232, 52, 28)
LIGHT = -45                      # degrees from top: the top left
FRAMES = 64
TRAVEL = 270


def polar(cx, cy, r, deg):
    a = math.radians(deg)
    return cx + r * math.sin(a), cy - r * math.cos(a)


def diag(w, h, lo, hi):
    """A top-left (hi) to bottom-right (lo) gradient, L: (x + y) / 2 from two ramps (a rotated square leaves wedges)."""
    gy = Image.linear_gradient("L").resize((w, h))
    gx = Image.linear_gradient("L").transpose(Image.Transpose.TRANSPOSE).resize((w, h))
    return ImageChops.add(gx, gy, 2.0).point(lambda v: int(hi + (lo - hi) * v / 255))


def disc(size, box, fill_l):
    x0, y0, x1, y1 = [int(v) for v in box]
    im = Image.new("RGBA", size, (0, 0, 0, 0))
    m = Image.new("L", (x1 - x0, y1 - y0), 0)
    ImageDraw.Draw(m).ellipse((0, 0, x1 - x0 - 1, y1 - y0 - 1), fill=255)
    g = fill_l.resize((x1 - x0, y1 - y0))
    im.paste(Image.merge("RGB", (g, g, g.point(lambda v: min(255, v + 3)))).convert("RGBA"), (x0, y0), m)
    return im


def tinted(l, rgb):
    """A greyscale picture coloured by rgb (128 = rgb itself)."""
    return Image.merge("RGB", [l.point(lambda v, c=c: max(0, min(255, int(c * v / 128)))) for c in rgb])


# ---------------------------------------------------------------- the slab

def module_bg():
    w, h = W * SS, H * SS
    light = diag(w, h, 116, 140)                                    # paint lit from the top left
    grain = Image.effect_noise((w // 2, h // 2), 4).resize((w, h), Image.BILINEAR)     # a fine, faint paint texture
    l = ImageChops.add(light, grain, 1.0, -128)
    vig = Image.radial_gradient("L").resize((w, h)).point(lambda v: max(0, v - 150) * 22 // 105)
    l = ImageChops.subtract(l, vig)
    im = tinted(l, YELLOW).convert("RGBA")
    # the rim: a bevel band lit by the same diagonal, a dark outer edge
    R = 18 * SS
    fm = Image.new("L", (w, h), 0)
    ImageDraw.Draw(fm).rounded_rectangle((0, 0, w - 1, h - 1), radius=R, fill=255)
    inner = Image.new("L", (w, h), 0)
    ImageDraw.Draw(inner).rounded_rectangle((6 * SS, 6 * SS, w - 1 - 6 * SS, h - 1 - 6 * SS), radius=R - 6 * SS, fill=255)
    band = ImageChops.subtract(fm, inner).filter(ImageFilter.GaussianBlur(1.5 * SS))
    lit = diag(w, h, 0, 255)
    for col, f in (((255, 250, 220), lambda v: max(0, v - 128) * 2), ((60, 40, 0), lambda v: max(0, 128 - v) * 2)):
        layer = Image.new("RGBA", (w, h), col + (0,))
        layer.putalpha(ImageChops.multiply(band, lit.point(f)))
        im.alpha_composite(layer)
    page = Image.new("RGBA", (w, h), (12, 12, 12, 255))           # outside the rounded corners
    page.paste(im, (0, 0), fm)
    ImageDraw.Draw(page).rounded_rectangle((0, 0, w - 1, h - 1), radius=R, outline=(70, 50, 0, 255), width=SS)
    for cx, cy in ((18, 16), (1262, 16), (18, 612), (1262, 612)):
        screw(page, cx, cy)
    page.convert("RGB").resize((W, H), Image.LANCZOS).save(os.path.join(IMG, "module_bg.png"), optimize=True)


def screw(page, cx, cy, r=7):
    R = r * SS
    s = 2 * R + 12 * SS
    c = s / 2
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    sh = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    ImageDraw.Draw(sh).ellipse((c - R + 2 * SS, c - R + 3 * SS, c + R + 2 * SS, c + R + 3 * SS), fill=(40, 25, 0, 150))
    im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(1.5 * SS)))
    im.alpha_composite(disc((s, s), (c - R, c - R, c + R, c + R), diag(64, 64, 110, 238)))
    d = ImageDraw.Draw(im)
    d.ellipse((c - R, c - R, c + R, c + R), outline=(80, 80, 84, 255), width=SS)
    for a in (35, 125):
        x0, y0 = polar(c, c, R * 0.62, a)
        x1, y1 = polar(c, c, R * 0.62, a + 180)
        d.line([(x0, y0), (x1, y1)], fill=(54, 54, 58, 255), width=2 * SS)
    page.alpha_composite(im, (int(cx * SS - c), int(cy * SS - c)))


# ---------------------------------------------------------------- recessed charcoal panels

def panel(w, h, rx=10):
    """A frame's charcoal panel set into the slab: its floor a little lighter toward the light, an inner shadow along
    the top and left, a yellow lip lit along the bottom-right edge, and the title rule (the td3 frame's) baked in."""
    W2, H2 = w * SS, h * SS
    m = Image.new("L", (W2, H2), 0)
    ImageDraw.Draw(m).rounded_rectangle((2 * SS, 2 * SS, W2 - 1 - 2 * SS, H2 - 1 - 2 * SS), radius=rx * SS, fill=255)
    floor = tinted(diag(W2, H2, 116, 140), CHARCOAL).convert("RGBA")
    out = Image.new("RGBA", (W2, H2), (0, 0, 0, 0))
    out.paste(floor, (0, 0), m)
    sh = ImageChops.offset(m, 4 * SS, 5 * SS).filter(ImageFilter.GaussianBlur(6 * SS))
    inner = ImageChops.subtract(m, sh)
    dark = Image.new("RGBA", (W2, H2), (0, 0, 0, 0))
    dark.putalpha(inner.point(lambda v: v * 190 // 255))
    out.alpha_composite(dark)
    # the slab's lit lip below and right of the opening
    lip = Image.new("L", (W2, H2), 0)
    ImageDraw.Draw(lip).rounded_rectangle((2 * SS + 2 * SS, 2 * SS + 2 * SS, W2 - 1, H2 - 1), radius=rx * SS, outline=255, width=2 * SS)
    lip = ImageChops.subtract(lip, m)
    hl = Image.new("RGBA", (W2, H2), (255, 236, 150, 0))
    hl.putalpha(lip.point(lambda v: v * 170 // 255))
    out.alpha_composite(hl)
    d = ImageDraw.Draw(out)
    d.rounded_rectangle((2 * SS, 2 * SS, W2 - 1 - 2 * SS, H2 - 1 - 2 * SS), radius=rx * SS, outline=(6, 6, 6, 255), width=SS)
    y = 38.5 * SS
    d.line([(18 * SS, y), (W2 - 18 * SS, y)], fill=(70, 70, 72, 255), width=SS)
    d.line([(18 * SS, y + SS), (W2 - 18 * SS, y + SS)], fill=(10, 10, 10, 255), width=SS)
    out.resize((w, h), Image.LANCZOS).save(os.path.join(IMG, "panel_%dx%d.png" % (w, h)), optimize=True)


# ---------------------------------------------------------------- knobs

def knob_frame(r, deg, t, k):
    """One knob position in the renderer's 2r+8 box at scale k: the arc to t, then the fixed body (skirt, step, dome,
    sheen) and what turns (the chamfer, shaded by how it faces the light, and the red pointer)."""
    box = (2 * r + 8) * k
    c = box / 2
    R = r * k
    im = Image.new("RGBA", (box, box), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    # the value arc and its track (as Acid's: radius r + 2.5)
    ra = (r + 2.5) * k
    aw = max(2, r / 10) * k
    d.arc((c - ra, c - ra, c + ra, c + ra), start=-90 - 135, end=-90 + 135, fill=(10, 10, 10, 255), width=int(aw))
    if t > 0:
        d.arc((c - ra, c - ra, c + ra, c + ra), start=-90 - 135, end=-90 - 135 + TRAVEL * t, fill=ARC + (255,), width=int(aw))
    # shadow, skirt
    sh = Image.new("RGBA", (box, box), (0, 0, 0, 0))
    ImageDraw.Draw(sh).ellipse((c - R + 1.5 * k, c - R + 2.5 * k, c + R + 1.5 * k, c + R + 2.5 * k), fill=(0, 0, 0, 200))
    im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(2 * k)))
    R2 = R - 1.5 * k
    im.alpha_composite(disc((box, box), (c - R2, c - R2, c + R2, c + R2), diag(64, 64, 14, 70)))
    d = ImageDraw.Draw(im)
    for i in range(60):
        a = 360 * i / 60
        v = int(30 + 50 * (0.5 + 0.5 * math.cos(math.radians(a - LIGHT))))
        x0, y0 = polar(c, c, R2 * 0.78, a)
        x1, y1 = polar(c, c, R2 * 0.97, a)
        d.line([(x0, y0), (x1, y1)], fill=(v, v, v + 3, 255), width=max(1, int(1.2 * k)))
    rim = Image.new("RGBA", (box, box), (0, 0, 0, 0))
    ImageDraw.Draw(rim).arc((c - R2 + k, c - R2 + k, c + R2 - k, c + R2 - k), start=180, end=300, fill=(230, 230, 236, 170), width=int(1.5 * k))
    im.alpha_composite(rim.filter(ImageFilter.GaussianBlur(0.8 * k)))
    rt = R2 * 0.68
    st = Image.new("RGBA", (box, box), (0, 0, 0, 0))
    ImageDraw.Draw(st).ellipse((c - rt + 1.5 * k, c - rt + 3 * k, c + rt + 1.5 * k, c + rt + 3 * k), fill=(0, 0, 0, 200))
    im.alpha_composite(st.filter(ImageFilter.GaussianBlur(2 * k)))
    im.alpha_composite(disc((box, box), (c - rt, c - rt, c + rt, c + rt), diag(64, 64, 34, 104)))
    sheen = Image.new("RGBA", (box, box), (0, 0, 0, 0))
    ImageDraw.Draw(sheen).ellipse((c - rt * 0.72, c - rt * 0.8, c + rt * 0.02, c - rt * 0.16), fill=(255, 255, 255, 70))
    im.alpha_composite(sheen.filter(ImageFilter.GaussianBlur(4 * k)))
    # what turns: the chamfer, then the pointer
    facing = math.cos(math.radians(deg - LIGHT))
    half = math.degrees(math.acos(-0.08))
    pts = [polar(c, c, rt - 0.5 * k, deg - half + 2 * half * i / 40) for i in range(41)]
    mask = Image.new("L", (box, box), 0)
    ImageDraw.Draw(mask).polygon(pts, fill=255)
    v = int(66 + 34 * facing)
    facet = Image.new("RGBA", (box, box), (0, 0, 0, 0))
    facet.paste(Image.new("RGBA", (box, box), (v, v, v + 3, 255)), (0, 0), mask.filter(ImageFilter.GaussianBlur(0.5 * k)))
    im.alpha_composite(facet)
    d = ImageDraw.Draw(im)
    ax, ay = polar(c, c, rt - k, deg - half)
    bx, by = polar(c, c, rt - k, deg + half)
    d.line([(ax, ay), (bx, by)], fill=(150, 150, 156, 200) if facing < 0 else (20, 20, 22, 220), width=max(1, int(1.1 * k)))
    x0, y0 = polar(c, c, R2 * 0.73, deg)
    x1, y1 = polar(c, c, R2 * 0.97, deg)
    pw = int(max(2.4, r * 0.085) * k)
    d.line([(x0, y0), (x1, y1)], fill=(90, 10, 8, 255), width=pw + k)
    d.line([(x0, y0), (x1, y1)], fill=RED + (255,), width=pw)
    return im


def knob_strip(r=46, k=2):
    box = (2 * r + 8) * k
    strip = Image.new("RGBA", (box, box * FRAMES), (0, 0, 0, 0))
    for i in range(FRAMES):
        t = i / (FRAMES - 1)
        strip.paste(knob_frame(r, -TRAVEL / 2 + TRAVEL * t, t, k), (0, i * box))
    strip.save(os.path.join(IMG, "knob_strip.png"), optimize=True)


def main():
    module_bg()
    sizes = set()
    for line in open(os.path.join(HERE, "layout.conf")):
        if line.startswith("frame "):
            w = int(re.search(r"\bw=(\d+)", line).group(1))
            h = int(re.search(r"\bh=(\d+)", line).group(1))
            sizes.add((w, h))
    for w, h in sorted(sizes):
        panel(w, h)
    knob_strip()


if __name__ == "__main__":
    main()


# ---------------------------------------------------------------- the top band (art file=images/acid_top.png)

from PIL import ImageFont   # noqa: E402

FONTS = os.path.join(HERE, "fonts")
INK = (31, 31, 31)


def smiley_sticker(r, tilt, seed=303):
    """The acid smiley as an old vinyl sticker: the yellow face melting into drips that run and bead at their ends,
    a white die-cut border that follows them, then wear: faded print, scuffs through the ink to the vinyl, grime
    along the edges, a lifted corner's shadow."""
    import random
    rnd = random.Random(seed)
    k = SS
    R = r * k
    s = int(3.4 * R)
    c = s / 2
    cy = c - 0.35 * R
    art = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(art)
    y = (255, 222, 96, 255)
    # drips: a run from the face's lower edge, narrowing, ending in a round bead
    for ang, length, wd in ((-38, 0.42, 0.19), (-12, 0.7, 0.24), (14, 0.6, 0.21), (36, 0.32, 0.17)):
        x0, y0 = polar(c, cy, R * 0.92, 180 + ang)
        top_w, neck = wd * R, wd * R * 0.62
        yb = y0 + length * R
        d.polygon([(x0 - top_w, y0 - 0.15 * R), (x0 + top_w, y0 - 0.15 * R), (x0 + neck, yb), (x0 - neck, yb)], fill=y)
        bead = wd * R * 0.95
        d.ellipse((x0 - bead, yb - bead * 0.9, x0 + bead, yb + bead * 1.1), fill=y)
    d.ellipse((c - R, cy - R, c + R, cy + R), fill=y)
    sil = art.getchannel("A")
    # outline the whole melted shape, then the face
    edge = ImageChops.subtract(sil, sil.filter(ImageFilter.MinFilter(int(0.16 * R) | 1)))   # an ink line inside the edge
    ink = Image.new("RGBA", (s, s), INK + (0,))
    ink.putalpha(edge)
    art.alpha_composite(ink)
    d = ImageDraw.Draw(art)
    for ex in (-0.38, 0.38):
        d.ellipse((c + ex * R - 0.14 * R, cy - 0.36 * R, c + ex * R + 0.14 * R, cy - 0.06 * R), fill=INK + (255,))
    d.arc((c - 0.52 * R, cy - 0.35 * R, c + 0.52 * R, cy + 0.6 * R), start=18, end=162, fill=INK + (255,), width=int(0.08 * R))
    # die-cut vinyl border following the drips
    full = art.getchannel("A").point(lambda v: 255 if v > 20 else 0)
    border = full.filter(ImageFilter.MaxFilter(int(0.16 * R) | 1)).filter(ImageFilter.GaussianBlur(0.7 * k))
    # wear: print faded in patches, scuffs through to the white vinyl
    fade = Image.effect_noise((s // 24, s // 24), 60).resize((s, s), Image.BICUBIC).point(lambda v: 255 - max(0, v - 128) // 2)
    worn = art.getchannel("A")
    scuffs = Image.new("L", (s, s), 0)
    sd = ImageDraw.Draw(scuffs)
    for _ in range(26):
        x, yy = rnd.uniform(0.2, 0.8) * s, rnd.uniform(0.1, 0.8) * s
        L = rnd.uniform(0.05, 0.22) * R
        a2 = rnd.uniform(0, 180)
        x1, y1 = polar(x, yy, L, a2)
        sd.line([(x, yy), (x1, y1)], fill=255, width=max(1, int(rnd.uniform(0.5, 1.6) * k)))
    for _ in range(120):
        x, yy = rnd.uniform(0, s), rnd.uniform(0, s)
        rr = rnd.uniform(0.3, 1.2) * k
        sd.ellipse((x - rr, yy - rr, x + rr, yy + rr), fill=255)
    worn = ImageChops.multiply(ImageChops.subtract(worn, scuffs), fade)
    art.putalpha(worn)
    st = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    sh = Image.new("RGBA", (s, s), (40, 28, 0, 0))
    moved = Image.new("L", (s, s), 0)                 # shifted down-right (ImageChops.offset would wrap round)
    moved.paste(border, (int(2 * k), int(3 * k)))
    sh.putalpha(moved.filter(ImageFilter.GaussianBlur(2.5 * k)).point(lambda v: v * 150 // 255))
    st.alpha_composite(sh)
    vinyl = Image.new("RGBA", (s, s), (238, 234, 218, 0))
    vinyl.putalpha(border)
    st.alpha_composite(vinyl)
    st.alpha_composite(art)
    # grime collected along the edge, and a soft gloss
    rim = ImageChops.subtract(border, border.filter(ImageFilter.MinFilter(int(0.07 * R) | 1))).filter(ImageFilter.GaussianBlur(1.2 * k))
    grime = Image.new("RGBA", (s, s), (110, 92, 50, 0))
    grime.putalpha(ImageChops.multiply(rim, Image.effect_noise((s, s), 70).point(lambda v: min(255, v + 40))).point(lambda v: v * 150 // 255))
    st.alpha_composite(grime)
    gloss = Image.new("L", (s, s), 0)
    ImageDraw.Draw(gloss).ellipse((c - 0.8 * R, cy - 0.95 * R, c + 0.3 * R, cy - 0.2 * R), fill=55)
    gl = Image.new("RGBA", (s, s), (255, 255, 255, 0))
    gl.putalpha(ImageChops.multiply(gloss.filter(ImageFilter.GaussianBlur(5 * k)), border))
    st.alpha_composite(gl)
    return st.rotate(tilt, resample=Image.BICUBIC)


def top_band():
    """The wordmark printed on the yellow in charcoal (silk screen: flat ink, a faint light edge under it), the
    tagline, and the smiley stuck on over the D as an old sticker. 1208 x 122, placed at x=36 y=88."""
    w, h = 1208 * SS, 122 * SS
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    logo = ImageFont.truetype(os.path.join(FONTS, "Earth_Normal.ttf"), 72 * SS)
    d.text((60 * SS, (84 + 1.2) * SS), "ACID", font=logo, fill=(255, 236, 140, 150), anchor="ls")
    d.text((60 * SS, 84 * SS), "ACID", font=logo, fill=INK + (255,), anchor="ls")
    tag = ImageFont.truetype(os.path.join(FONTS, "Univers_53_Extended_Regular.otf"), 15 * SS)
    for i, ln in enumerate(("GENERATIVE ACID", "BASSLINE SEQUENCER")):
        y = (52 + 22 * i) * SS
        d.text((480 * SS, y + SS), ln, font=tag, fill=(255, 236, 140, 150), anchor="lm", stroke_width=SS // 2, stroke_fill=(255, 236, 140, 150))
        d.text((480 * SS, y), ln, font=tag, fill=INK + (255,), anchor="lm", stroke_width=SS // 2, stroke_fill=INK + (255,))
    # the one sticker, stuck over the end of the D, its drips running down past the band
    end = 60 + logo.getlength("ACID") / SS
    r = 36
    st = smiley_sticker(r, -9)
    cx, cy = end + 14, 50
    im.alpha_composite(st, (int(cx * SS - st.width / 2), int((cy + 0.35 * r) * SS - st.height / 2)))
    im.resize((1208, 122), Image.LANCZOS).save(os.path.join(IMG, "acid_top.png"), optimize=True)


if __name__ == "__main__":
    top_band()
