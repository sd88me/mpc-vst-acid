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
