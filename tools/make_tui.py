#!/usr/bin/env python3
"""Acid's native MPC skin: skins/TUI.json + skins/Q-Links.json + the PNGs they use (the SDK method, docs/SDK-PORTING.md).
Six pages (SEQ A, EDIT A, SEQ B, EDIT B, MOD, GLOBAL) at the layout.conf positions, on the 2.1 "module look" art (vst/images).
    python3 tools/make_tui.py        # -> skins/   (build-sdk.sh copies it to Plugin Skins/)"""
import hashlib, json, os, re, shutil
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "skins")
IMG = os.path.join(ROOT, "vst", "images")
FONTS = os.path.join(ROOT, "vst", "fonts")
LOCK = [l.strip() for l in open(os.path.join(ROOT, "vst", "params.lock")) if l.strip()]
PARAMS = json.load(open(os.path.join(ROOT, "vst", "params.json")))
LOCK.append("ui_open")   # UI-only param appended by the plugin (src/sdk/params_gen.h kUiParam)
UI_STEPS = 97            # ui_open is 0..96: 0 closed, k+1 = pick-list k open
OPTIONS = {p["key"]: p.get("options") for p in PARAMS["params"]}
LOCKSET = set(LOCK)
GESTURE = os.environ.get("ACID_GESTURE", "Instant")


def P(key):
    return "Parameter %d" % LOCK.index(key)


# ---- a JSON writer that keeps key order and allows the overlay widgets' duplicate "version" key ------------------
class Obj:
    """An ordered JSON object that may repeat a key: Obj(("version", 2), ("version", 1), ...)."""
    def __init__(self, *pairs):
        self.pairs = list(pairs)


def dump(v, ind=0):
    sp = "  " * ind
    if hasattr(v, "pairs"):   # Obj from either copy of this module (it is also imported by skin_pages)
        pairs = v.pairs
    elif isinstance(v, dict):
        pairs = list(v.items())
    else:
        pairs = None
    if pairs is not None:
        if not pairs:
            return "{}"
        inner = (",\n").join("%s  %s: %s" % (sp, dump(k), dump(x, ind + 1)) for k, x in pairs)
        return "{\n%s\n%s}" % (inner, sp)
    if isinstance(v, list):
        if not v:
            return "[]"
        return "[\n%s\n%s]" % (",\n".join(sp + "  " + dump(x, ind + 1) for x in v), sp)
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        return repr(v)
    if isinstance(v, int):
        return str(v)
    s = str(v).replace("\\", "\\\\").replace('"', '\\"')
    return '"%s"' % s


# ---- building blocks -----------------------------------------------------------------------------------------------
def bounds(b, focus="No", visible="Always", invalid="Show", ind=None):
    d = {"version": 2 if ind else 1, "acceptsHWFocus": focus, "showWhenDataModelInvalid": invalid, "whenVisible": visible,
         "boundsType": "Absolute", "bounds": b}
    if ind:
        d["additionalInvalidatingHandles"] = ind
    return d


def entry(name, typ, data, b, remap=None, focus="No", visible="Always", ind=None):
    return {"version": 2,
            "componentData": {"version": 1, "name": name, "type": typ, "data": data},
            "handle remapping": {"version": 1, "map": [{"key": "Data", "value": remap}] if remap else []},
            "bounds": bounds(b, focus, visible, ind=ind)}


def bg(colour="0", image=""):
    return {"version": 1, "focussed": {"version": 1, "colour": colour, "image": image},
            "unfocussed": {"version": 1, "colour": colour, "image": image}}


def component(children, actions=None, ignore=False, background=None):
    return {"version": 2, "actions": actions or [], "backgroundData": background or bg(),
            "ignoreMousePresses": ignore, "disableCoarseDataWheel": False, "componentsData": children}


def act(on, handler, extra=""):
    return {"version": 1, "onAction": on, "handler": handler, "handleName": "Data", "additionalData": extra}


FOCUS = {"version": 1, "backgroundColour": "19ffffff", "outlineColour": "ffe81f40", "backgroundInset": 4.0, "outlineThickness": 1.0}


def text_style(h=22.0, colour="ffbea880", style="SemiBold", just="left verticallyCentred", case="Upper Case", font="Titillium Web"):
    return {"version": 1, "font": {"version": 1, "name": font, "style": style, "height": h}, "colour": colour,
            "justification": just, "case": case}


def label(kind, b, remap=None, text=None, **ts):
    d = {"version": 1, "textStyle": text_style(**ts), "type": kind, "handleName": "Data" if remap else "Invalid"}
    if text is not None:
        d["text"] = text
    return entry("label", "Label", d, b, remap)


def _inherit(e):
    """A label inside a component reads the component's own Data handle."""
    e["componentData"]["data"]["handleName"] = "Data"
    return e


def definitions():
    """Reusable components: generic slider slot, the two overlays."""
    slider_slot = component([
        entry("focus", "Focus", FOCUS, "0 0 278 107", visible="WhenFocussed"),
        entry("slider", "Slider", {"version": 1, "handleName": "Data"}, "15 15 248 77"),
    ], actions=[act("Mouse Down", "Q-Link"), act("Double Click", "Show Overlay", "knob overlay"),
                act("Enter Pressed", "Show Overlay", "knob overlay")])
    knob_overlay = component([entry("overlay", "KnobOverlay", Obj(
        ("version", 2), ("version", 1),
        ("actions", [{"version": 1, "onAction": "Focus Lost", "handler": "Focus Lost", "handleName": "Focus Lost", "additionalData": ""}]),
        ("overlayType", "Knob With Header"), ("scaleType", "Linear"), ("polarityType", "Unipolar"),
        ("showMinusSign", True), ("handleName", "Data")), "0 0 1280 800", focus="Yes")], ignore=True)
    return [{"key": "sliderSlot", "value": slider_slot}, {"key": "knob overlay", "value": knob_overlay}]


def slider_slot_def():
    slot = component([
        entry("focus", "Focus", FOCUS, "0 0 278 107", visible="WhenFocussed"),
        entry("slider", "Slider", {"version": 1, "handleName": "Data"}, "15 15 248 77"),
    ], actions=[act("Mouse Down", "Q-Link"), act("Double Click", "Show Overlay", "knob overlay"),
                act("Enter Pressed", "Show Overlay", "knob overlay")])
    knob_overlay = component([entry("overlay", "KnobOverlay", Obj(
        ("version", 2), ("version", 1),
        ("actions", [{"version": 1, "onAction": "Focus Lost", "handler": "Focus Lost", "handleName": "Focus Lost", "additionalData": ""}]),
        ("overlayType", "Knob With Header"), ("scaleType", "Linear"), ("polarityType", "Unipolar"),
        ("showMinusSign", True), ("handleName", "Data")), "0 0 1280 800", focus="Yes")], ignore=True)
    menu_overlay = component([entry("overlay", "MenuOverlay", Obj(
        ("version", 1), ("version", 1),
        ("actions", [{"version": 1, "onAction": "Focus Lost", "handler": "Focus Lost", "handleName": "Focus Lost", "additionalData": ""}]),
        ("withNumbers", False), ("handleName", "Data")), "0 0 1280 800", focus="Yes")], ignore=True)
    return [{"key": "sliderSlot", "value": slot}, {"key": "knob overlay", "value": knob_overlay}, {"key": "menu overlay", "value": menu_overlay}]


KNOB_FOCUS = dict(FOCUS, backgroundColour="00000000", outlineColour="00000000")   # no square behind a round knob


def focus_ring(b, knob=False):
    return entry("focus", "Focus", KNOB_FOCUS if knob else FOCUS, b, visible="WhenFocussed")




# ---- art ------------------------------------------------------------------------------------------------------------
YEL, CHAR, RED, GRN = (245, 196, 0), (31, 31, 31), (232, 52, 28), (53, 208, 127)
INK, DIM, WELL, KEY = (240, 237, 228), (154, 150, 137), (10, 10, 10), (42, 42, 42)


def uf(size):
    return ImageFont.truetype(os.path.join(FONTS, "Univers_53_Extended_Regular.otf"), int(size))


def save(im, name):
    im.save(os.path.join(OUT, name))
    return name


def rgba(c, a=255):
    return tuple(c) + (a,)


def caption_button(w, h, caption, lit, fill_on=YEL, fill_off=KEY, ink_on=(10, 10, 10), ink_off=DIM, size=None):
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, w - 1, h - 1), 4, fill=fill_on if lit else fill_off)
    d.text((w // 2, h // 2 + 1), caption, font=uf(size or min(h * 0.42, 17)), fill=ink_on if lit else ink_off, anchor="mm")
    return im


def red_button(w, h, caption, lit):
    """GENERATE / MUTATE: the glossy red key of the 2.1 skin."""
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    top, bot = ((255, 120, 96), (226, 52, 30)) if lit else ((236, 84, 62), (178, 24, 8))
    for y in range(h):
        t = y / (h - 1)
        d.line((0, y, w, y), fill=tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(3)) + (255,))
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), 5, fill=255)
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    out.paste(im, (0, 0), mask)
    ImageDraw.Draw(out).text((w // 2, h // 2 + 1), caption, font=uf(h * 0.36), fill=(255, 255, 255), anchor="mm")
    return out


def mute_button(w, h, caption, lit):
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, w - 1, h - 1), 6, fill=(232, 52, 28) if lit else (84, 52, 30), outline=(20, 12, 6), width=2)
    d.text((w // 2, h // 2 + 1), caption, font=uf(h * 0.4), fill=(255, 255, 255) if lit else (150, 112, 84), anchor="mm")
    return im


def switch_images():
    """SYNC: a small slide switch."""
    out = []
    for lit in (True, False):
        im = Image.new("RGBA", (64, 34), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle((0, 2, 63, 31), 15, fill=YEL if lit else (10, 10, 10), outline=(70, 70, 70), width=2)
        kx = 46 if lit else 17
        d.ellipse((kx - 12, 5, kx + 12, 29), fill=(40, 40, 40) if lit else (84, 80, 72))
        out.append(im)
    return save(out[0], "sw_on.png"), save(out[1], "sw_off.png")


LANES = {"gate": YEL, "acc": RED, "sld": GRN, "lock": (214, 210, 196)}


def lane_images(kind):
    outs = []
    for lit in (True, False):
        im = Image.new("RGBA", (64, 44), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle((0, 0, 63, 43), 5, fill=LANES[kind] if lit else (28, 28, 28), outline=(70, 66, 40) if lit else (10, 10, 10), width=2)
        outs.append(im)
    return save(outs[0], "ln_%s_on.png" % kind), save(outs[1], "ln_%s_off.png" % kind)


_KNOBS = {}


def knob_def(r):
    """A film-strip knob from the 2.1 module-look strip (64 frames), scaled to the layout's radius."""
    size = int(round(r * 2.2))
    name = "kn%d" % size
    if name not in _KNOBS:
        src = Image.open(os.path.join(IMG, "knob_strip.png")).convert("RGBA")
        strip = Image.new("RGBA", (size, size * 64), (0, 0, 0, 0))
        for i in range(64):
            fr = src.crop((0, i * 200, 200, i * 200 + 200)).resize((size, size), Image.LANCZOS)
            strip.paste(fr, (0, i * size))
        save(strip, name + ".png")
        pad = 6
        _KNOBS[name] = (size, {"key": name, "value": component([
            entry("knob", "Knob", {"version": 3, "knobType": "FilmStrip", "filmStrip": name + ".png", "numFrames": 64, "invert": False,
                                   "dragOrientation": "Vertical", "handleName": "Data"}, "0 0 %d %d" % (size, size)),
        ], actions=[act("Mouse Down", "Q-Link"), act("Double Click", "Show Overlay", "knob overlay"),
                    act("Enter Pressed", "Show Overlay", "knob overlay")])})
    return _KNOBS[name]


def note_def():
    """The step's NOTE slider: the 2.1 strip (29 frames of 52 x 270), dragged vertically."""
    if "nslider" not in _KNOBS:
        shutil.copy(os.path.join(IMG, "note_strip.png"), os.path.join(OUT, "note_strip.png"))
        _KNOBS["nslider"] = (0, {"key": "nslider", "value": component([
            focus_ring("-4 -4 60 278"),
            entry("strip", "Knob", {"version": 3, "knobType": "FilmStrip", "filmStrip": "note_strip.png", "numFrames": 29, "invert": False,
                                    "dragOrientation": "Vertical", "handleName": "Data"}, "0 0 52 270"),
        ], actions=[act("Mouse Down", "Q-Link"), act("Double Click", "Show Overlay", "knob overlay"),
                    act("Enter Pressed", "Show Overlay", "knob overlay")])})
    return _KNOBS["nslider"][1]


# ---- the pages -------------------------------------------------------------------------------------------------------
class Page:
    def __init__(self, name, fn, sub=0):
        self.name, self.fn, self.sub = name, fn, sub
        self.kids, self.groups, self.qrows = [], [], []

    def tab(self, bgfile):
        kids = [entry("bg", "Image", {"version": 2, "imageType": "Regular", "colour": "0", "image": bgfile}, "0 0 1280 628")] + self.kids
        return {"version": 1, "tabName": self.name, "fnKeyIndex": self.fn, "fnKeySubIndex": self.sub,
                "componentDefinition": component(kids, background=bg("ff1a1a1a")), "qlinkBoundsData": self.groups}

    def button(self, key, b, on, off, bid=0, n=1, name=None, ind=None):
        self.kids.append(entry(name or key, "Button", {"version": 2, "onImage": on, "offImage": off, "buttonId": (bid if n > 1 else 1), "numButtonsInGroup": n,
                                                       "handleName": "Data", "gestureBehaviour": GESTURE}, b, remap=P(key), focus="No", ind=ind))

    def qgroup(self, rect, keys):
        self.groups.append("%d %d %d %d" % (rect[0], rect[1], rect[2] - rect[0], rect[3] - rect[1]))
        self.qrows.append(keys)


def parse_layout():
    tabs, cur = {}, None
    for line in open(os.path.join(ROOT, "vst", "layout.conf")):
        line = line.strip()
        m = re.match(r"\[tab (.+)\]", line)
        if m:
            cur = tabs.setdefault(m.group(1), {"items": [], "q": []})
            continue
        if not cur or not line or line.startswith("#"):
            continue
        if line.startswith("qlinks"):
            cur["q"].append(line.split("=", 1)[1].strip().split(","))
            continue
        kind, rest = line.split(None, 1)
        attrs = {k: v.strip('"') for k, v in re.findall(r'(\w+)=("[^"]*"|\S+)', rest)}
        cur["items"].append((kind, attrs))
    return tabs


def when(a):
    """when=key:value -> the IndexedEnabling handle that shows a widget only while that choice is selected."""
    if "when" not in a:
        return None
    k, v = a["when"].split(":")
    opts = [o.lower() for o in OPTIONS[k]]
    return ["IndexedEnabling/%d/%d/%s" % (opts.index(v.lower()), len(opts), P(k))]


PICKERS, PICK_DEFS, PICK_N = [], {}, [0]


def pick_panel(key, n, px, py, fw, fh, opts):
    """A drawn pick-list for the choice `key`: a panel with one radio Button per option and a close key, visible only while
    ui_open == n + 1 (the proven recipe, docs/SDK-PORTING.md). The plugin clears ui_open when the choice changes."""
    cols = 1 if len(opts) <= 8 else (4 if len(opts) > 12 else 3)
    rows = (len(opts) + cols - 1) // cols
    cw, ch, gap, hdr = (240 if cols == 1 else 200), 46, 4, 48
    pw, ph = cols * (cw + gap) + gap + 8, hdr + rows * (ch + gap) + gap + 8
    ck = "list_%d_%s" % (len(opts), hashlib.md5("|".join(opts).encode()).hexdigest()[:8])
    if ck not in PICK_DEFS:
        bgim = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
        dd = ImageDraw.Draw(bgim)
        dd.rounded_rectangle((0, 0, pw - 1, ph - 1), 10, fill=(20, 20, 20), outline=YEL, width=3)
        dd.text((16, hdr // 2 + 2), "SELECT", font=uf(16), fill=YEL, anchor="lm")
        kidsl = [entry("panel", "Image", {"version": 2, "imageType": "Regular", "colour": "0", "image": save(bgim, ck + "_bg.png")}, "0 0 %d %d" % (pw, ph))]
        for i, o in enumerate(opts):
            r, c = i % rows, i // rows
            on = save(caption_button(cw, ch, o, True, size=16), "%s_%d_on.png" % (ck, i))
            off = save(caption_button(cw, ch, o, False, ink_off=INK, size=16), "%s_%d_off.png" % (ck, i))
            kidsl.append(entry("opt %d" % i, "Button", {"version": 2, "onImage": on, "offImage": off, "buttonId": i, "numButtonsInGroup": len(opts),
                                                         "handleName": "Data", "gestureBehaviour": GESTURE},
                               "%d %d %d %d" % (8 + c * (cw + gap), hdr + gap + r * (ch + gap), cw, ch)))
        xon = save(caption_button(56, 36, "X", True, size=18), "x_on.png")
        xoff = save(caption_button(56, 36, "X", False, ink_off=INK, size=18), "x_off.png")
        kidsl.append(entry("close", "Button", {"version": 2, "onImage": xon, "offImage": xoff, "buttonId": 0, "numButtonsInGroup": UI_STEPS,
                                               "handleName": "Data", "gestureBehaviour": GESTURE}, "%d 6 56 36" % (pw - 66), remap=P("ui_open")))
        PICKERS.append({"key": ck, "value": component(kidsl)})
        PICK_DEFS[ck] = (pw, ph)
    pw, ph = PICK_DEFS[ck]
    if cols == 1:
        x = max(8, min(px - pw // 2, 1272 - pw))
        y = py + fh // 2 + 4
        if y + ph > 620:
            y = py - fh // 2 - 4 - ph
        y = max(4, y)
    else:
        x, y = (1280 - pw) // 2, max(4, (628 - ph) // 2)
    return entry("list " + key, ck, {"version": 1, "handleName": "Data"}, "%d %d %d %d" % (x, y, pw, ph), remap=P(key), focus="No",
                 ind=["IndexedEnabling/%d/%d/%s" % (n + 1, UI_STEPS, P("ui_open"))])


def value_label(b, key, colour="ffd0cdc2", h=20.0, just="horizontallyCentred verticallyCentred", ind=None):
    e = label("Value", b, remap=P(key), just=just, colour=colour, style="SemiBold", case="Original", h=h)
    if ind:
        e["bounds"] = bounds(b, ind=ind)
    return e


def build_page(name, fn, spec, art_dir=None):
    """One printed page: the 2.1 art (module slab, wordmark, panels) + baked captions + the live widgets at the layout.conf positions."""
    art = Image.new("RGBA", (1280, 628), (0, 0, 0, 255))
    d = ImageDraw.Draw(art)
    pos = {}
    p = Page(name, fn)
    for kind, a in spec["items"]:
        if kind == "art":
            im = Image.open(os.path.join(IMG, os.path.basename(a["file"]))).convert("RGBA")
            art.alpha_composite(im, (int(a["x"]), int(a["y"]) - 86))
        elif kind == "frame":
            im = Image.open(os.path.join(IMG, os.path.basename(a["img"]))).convert("RGBA")
            art.alpha_composite(im, (int(a["x"]), int(a["y"]) - 86))
            if a.get("title"):
                d.text((int(a["x"]) + 18, int(a["y"]) - 86 + 20), a["title"], font=uf(24), fill=INK, anchor="lm")
    bar_numbers = []
    for kind, a in spec["items"]:
        key = a.get("key")
        cx, cy = int(a.get("cx", 0)), int(a.get("cy", 0)) - 86
        if kind == "text":
            if "when" in a:
                bar_numbers.append((a["when"], a["label"], cx, cy))
            else:
                d.text((cx, cy), a["label"], font=uf(13 * float(a.get("size", 1))), fill=INK, anchor="lm" if a.get("align") == "left" else "mm")
            continue
        if key is None or key not in LOCKSET:
            continue
        pos[key] = (cx, cy)
        ind = when(a)
        if kind == "knob":
            size, defn = knob_def(int(a["r"]))
            if defn["key"] not in [x["key"] for x in KNOB_DEFS]:
                KNOB_DEFS.append(defn)
            p.kids.append(entry(key, defn["key"], {"version": 1, "handleName": "Data"}, "%d %d %d %d" % (cx - size // 2, cy - size // 2, size, size),
                                remap=P(key), focus="Yes", ind=ind))
            if a.get("label") and not ind:
                d.text((cx, cy + size // 2 + 10), a["label"].replace("\n", " ").title() if a["label"].isupper() and False else a["label"], font=uf(13), fill=INK, anchor="mm")
            p.kids.append(value_label("%d %d 124 28" % (cx - 62, cy + size // 2 + 24), key, ind=ind))
        elif kind == "button":
            w, h = 150, 46
            p.button(key, "%d %d %d %d" % (cx - w // 2, cy - h // 2, w, h), save(red_button(w, h, a["label"], True), "rb_%s_on.png" % a["label"].lower()),
                     save(red_button(w, h, a["label"], False), "rb_%s_off.png" % a["label"].lower()))
        elif kind == "toggle":
            w, h = int(a.get("w", 64)), int(a.get("h", 34))
            if key.endswith("_gate") or key.endswith("_acc") or key.endswith("_sld") or key.endswith("_lock"):
                lk = key.rsplit("_", 1)[1]
                on, off = lane_images(lk)
                p.button(key, "%d %d 64 44" % (cx - 32, cy - 22), on, off)
            elif w >= 100:
                cap = "MUTE" if key == "mute" else a.get("label") or key.upper().replace("_", " ")
                p.button(key, "%d %d %d %d" % (cx - w // 2, cy - h // 2, w, h), save(mute_button(w, h, cap, True), "mb_%s_on.png" % key),
                         save(mute_button(w, h, cap, False), "mb_%s_off.png" % key))
            else:
                on, off = switch_images()
                p.button(key, "%d %d 64 34" % (cx - 32, cy - 17), on, off)
                d.text((cx, cy + 32), a.get("label", ""), font=uf(13), fill=INK, anchor="mm")
        elif kind == "enum_h":
            opts = OPTIONS[key]
            sw, sh = int(a["sw"]), 34
            x0 = cx - sw * len(opts) // 2
            if a.get("label"):
                d.text((cx, cy - 34), a["label"], font=uf(15), fill=INK, anchor="mm")
            for i, o in enumerate(opts):
                on = save(caption_button(sw, sh, o, True, size=14), "eh_%s_%d_on.png" % (key, i))
                off = save(caption_button(sw, sh, o, False, size=14), "eh_%s_%d_off.png" % (key, i))
                p.button(key, "%d %d %d %d" % (x0 + i * sw, cy - sh // 2, sw, sh), on, off, bid=i, n=len(opts), name="%s %d" % (key, i), ind=ind)
        elif kind == "popup":
            w, h = int(a["w"]), max(int(a["h"]), 40)
            if a.get("label") and not ind:
                d.text((cx - w // 2, cy - h // 2 - 14), a["label"], font=uf(15), fill=DIM, anchor="lm")
            elif a.get("label"):
                d.text((cx - w // 2, cy - h // 2 - 14), a["label"], font=uf(15), fill=DIM, anchor="lm")
            n = PICK_N[0]; PICK_N[0] += 1
            assert n < UI_STEPS - 1
            fld = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            fd = ImageDraw.Draw(fld)
            fd.rounded_rectangle((0, 0, w - 1, h - 1), 3, fill=WELL)
            fd.polygon([(w - 36, h // 2 - 5), (w - 20, h // 2 - 5), (w - 28, h // 2 + 5)], fill=YEL)
            fname = save(fld, "fld_%d_%d.png" % (w, h))
            p.kids.append(entry(key + " box", "Image", {"version": 2, "imageType": "Regular", "colour": "0", "image": fname}, "%d %d %d %d" % (cx - w // 2, cy - h // 2, w, h), ind=ind))
            p.kids.append(value_label("%d %d %d %d" % (cx - w // 2 + 10, cy - h // 2, w - 50, h), key, colour="fff5c400", just="left verticallyCentred", ind=ind))
            clear = save(Image.new("RGBA", (8, 8), (0, 0, 0, 0)), "clear.png")
            p.kids.append(entry(key + " field", "Button", {"version": 2, "onImage": clear, "offImage": clear, "buttonId": n + 1, "numButtonsInGroup": UI_STEPS,
                                                           "handleName": "Data", "gestureBehaviour": GESTURE},
                                "%d %d %d %d" % (cx - w // 2, cy - h // 2, w, h), remap=P("ui_open"), focus="No", ind=ind))
            PANELS.append((p, pick_panel(key, n, cx, cy, w, h, OPTIONS[key]), ind))
        elif kind == "slider_v":
            note_def()
            p.kids.append(entry(key, "nslider", {"version": 1, "handleName": "Data"}, "%d %d 52 270" % (cx - 26, cy - 135), remap=P(key), focus="Yes"))
            p.kids.append(value_label("%d %d 60 28" % (cx - 30, cy + 140), key))
        elif kind == "picture":
            strip = Image.new("RGBA", (1088, 8 * 17), (0, 0, 0, 0))
            for i, f in enumerate(a["files"].split(",")):
                fr = Image.open(os.path.join(IMG, os.path.basename(f))).convert("RGBA")
                strip.paste(fr, (0, 8 * i))
            p.kids.append(entry("run light", "Image", {"version": 2, "imageType": "FilmStrip", "colour": "0", "image": save(strip, "run_strip.png"),
                                                       "numFrames": 17, "handleName": "Data"}, "%s %d 1088 8" % (a["x"], int(a["y"]) - 86), remap=P(key)))
        elif kind == "readout":
            w, h = int(a["w"]), int(a["h"])
            p.kids.append(value_label("%d %d %d %d" % (cx - w // 2, cy - h // 2, w, h), key, colour="fff5c400", h=22.0, ind=ind))
    if bar_numbers:   # step numbers 1..16 / 17..32 follow the bar switch: a 2-frame strip bound to it
        bk = [k for kind, a in spec["items"] for k in [a.get("key")] if k and k.endswith("_edit_bar")][0]
        strip = Image.new("RGBA", (1280, 28 * 2), (0, 0, 0, 0))
        sd = ImageDraw.Draw(strip)
        for w_, lb, cx, cy in bar_numbers:
            fr = int(w_.split(":")[1])
            sd.text((cx, fr * 28 + 14), lb, font=uf(14), fill=INK, anchor="mm")
        p.kids.append(entry("step numbers", "Image", {"version": 2, "imageType": "FilmStrip", "colour": "0", "image": save(strip, "steps_strip.png"),
                                                      "numFrames": 2, "handleName": "Data"}, "0 %d 1280 28" % (bar_numbers[0][3] - 14), remap=P(bk)))
    return p, art, pos


KNOB_DEFS = []
PANELS = []   # (page, list-entry, ind): the pick-list panels go last on their page so they draw over everything


def block_rect(keys, pos, edit=False):
    pts = [pos[k] for k in keys if k in pos]
    if edit:
        return (min(x for x, _ in pts) - 40, 150, max(x for x, _ in pts) + 40, 470)
    return (min(x for x, _ in pts) - 70, min(y for _, y in pts) - 56, max(x for x, _ in pts) + 70, max(y for _, y in pts) + 60)


def qlinks_for(pages):
    maps = []
    for p in pages:
        q = {"Q-Link %d" % n: -1 for n in range(1, 17)}
        for gi, keys in enumerate(p.qrows[:4]):
            first = 13 - 4 * gi
            for i, key in enumerate(keys):
                q["Q-Link %d" % (first + i)] = LOCK.index(key)
        maps.append({"Tab": p.fn + 1, "SubTab": p.sub + 1, "Bank Direction": "RowTopDown", "Q-Links": q})
    prog = {"Q-Link %d" % n: -1 for n in range(1, 17)}
    return {"version": 4, "info": {"version": 1, "type": "CompleteDescription"},
            "Screen Mode Q-Links": {"version": 4, "map": maps}, "Program Mode Q-Links": prog}


TABS = [("SEQ A", "SEQ A"), ("EDIT A", "SEQ A EDIT"), ("SEQ B", "SEQ B"), ("EDIT B", "SEQ B EDIT"), ("MOD", "MOD"), ("GLOBAL", "GLOBAL")]


def main():
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT)
    spec_all = parse_layout()
    pages, tabs = [], []
    for fn, (title, src) in enumerate(TABS):
        spec = spec_all[src]
        p, art, pos = build_page(title, fn, spec)
        p.fn = fn
        edit = src.endswith("EDIT")
        if edit:
            side = "a" if src.startswith("SEQ A") else "b"
            notes = ["%s_e%d_note" % (side, i) for i in range(16)]
            blocks = [notes[i:i + 4] for i in range(0, 16, 4)]
        else:
            blocks = [k for line in spec["q"] for i in range(0, len(line), 4) for k in [[x for x in line[i:i + 4] if x in LOCKSET]] if k]
        for keys in blocks[:4]:
            p.qgroup(block_rect(keys, pos, edit), keys)
        for pg, panel, ind in PANELS:
            if pg is p:
                p.kids.append(panel)
        pages.append(p)
        tabs.append(p.tab(save(art.convert("RGB"), "bg_%s.png" % title.replace(" ", "_").lower())))
    repl, seen = [], set()
    for k in LOCK:
        if k in seen or not OPTIONS.get(k):
            continue
        seen.add(k)
        repl.append({"key": P(k), "value": OPTIONS[k]})
    defs = slider_slot_def() + KNOB_DEFS + [_KNOBS["nslider"][1]] + PICKERS
    tui = {"pageData": {"version": 1, "componentDefinitions": {"version": 2, "importFiles": [], "localComponentDefinitions": defs},
                        "replacementStrings": repl, "info": {"version": 1, "type": "CompleteDescription"}, "tabs": tabs}}
    open(os.path.join(OUT, "TUI.json"), "w").write(dump(tui) + "\n")
    open(os.path.join(OUT, "Q-Links.json"), "w").write(dump(qlinks_for(pages)) + "\n")
    print("wrote", OUT, "-", len(tabs), "tabs,", len(os.listdir(OUT)), "files")


if __name__ == "__main__":
    main()
