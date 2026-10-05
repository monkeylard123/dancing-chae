"""
Pixel-art frames for the desktop walker (walker.py).

He is painted from simple shapes (ellipses, rectangles, pixel rows) onto a W x H grid of palette characters;
every shape gets a 1-pixel dark outline, which also draws the lines between overlapping parts.
To change his look, edit the coordinates/colours in paint() - no drawing code in walker.py needs to change.
Frames come out as lists of strings ('.' = transparent), the same format the tests and walker.py use.
"""
import math
from functools import lru_cache

PALETTE = {
    "k": "#1a1a1e",   # outline
    # camo cap
    "c": "#75684c", "d": "#3a3529", "g": "#556040", "C": "#8d7f5f",
    "w": "#ecebe4",   # white lettering on the cap
    "r": "#4a4a52",   # rings on the brim
    # face
    "h": "#2a1d16",   # hair, eyebrows
    "s": "#e4b096", "S": "#c98f76",   # skin, skin shadow
    "W": "#f2efe9", "e": "#4a2a16",   # eye white, iris
    "m": "#3a2216", "M": "#5e3a24",   # mustache, its highlight
    "b": "#9a7864", "B": "#7f6150",   # stubble, darker stubble
    "l": "#b8786a",   # lips
    "u": "#3f7fa6",   # blue earpiece
    "o": "#d4a640",   # gold earring
    # clothes
    "t": "#1d1d22", "T": "#3a3a44",   # black shirt, highlight / laces
    "O": "#b08040",   # brass eyelets for the laces
    "p": "#3b4252", "P": "#2b313d",   # trousers, seams and belt line
    "f": "#5a3a24", "F": "#2a1c12",   # shoes, soles
    # audience shirts, one per fan in turn
    "1": "#ef4444", "2": "#3b82f6", "3": "#22c55e", "4": "#eab308", "5": "#a855f7", "6": "#f97316",
}
FAN_COLORS = "123456"

W, H = 64, 112          # frame size in pixels
HEADROOM = 8            # extra rows above each frame in the window, for the z's


def noise(x, y, seed=0):
    """Deterministic 0..99 per pixel, for texture."""
    n = (x * 73856093) ^ (y * 19349663) ^ (seed * 83492791)
    return (n ^ (n >> 13)) * 1274126177 % 100


def camo(x, y):
    v = math.sin(x * 0.42 + y * 0.18) + 0.8 * math.sin(y * 0.55 - x * 0.27 + 1.3) + 0.004 * noise(x, y, 1)
    return "d" if v > 0.95 else "g" if v > 0.15 else "C" if v < -1.1 else "c"


def stubble(x, y):
    n = noise(x, y, 2)
    return "B" if n < 22 else "s" if n > 95 else "b"


class Grid:
    def __init__(self, w=W, h=H): self.w, self.h, self.px = w, h, [["."] * w for _ in range(h)]

    def set(self, x, y, c):
        if 0 <= x < self.w and 0 <= y < self.h: self.px[y][x] = c

    def fill(self, pts, color, line=True):
        """Paint pixels; color is a palette char or f(x, y). line: outline the shape first."""
        pts = set(pts)
        if line:
            for x, y in pts:
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    if (x + dx, y + dy) not in pts: self.set(x + dx, y + dy, "k")
        for x, y in pts: self.set(x, y, color(x, y) if callable(color) else color)

    def rows(self): return ["".join(r) for r in self.px]


def ellipse(cx, cy, rx, ry, keep=None):
    """Pixels whose centres fall inside the ellipse (cx=32 is symmetric on a 64-wide grid)."""
    return [(x, y) for y in range(int(cy - ry) - 1, int(cy + ry) + 2) for x in range(int(cx - rx) - 1, int(cx + rx) + 2)
            if ((x + .5 - cx) / rx) ** 2 + ((y + .5 - cy) / ry) ** 2 <= 1 and (keep is None or keep(x, y))]


def rect(x0, y0, x1, y1): return [(x, y) for y in range(y0, y1 + 1) for x in range(x0, x1 + 1)]


def spans(rows, y0):
    """{row offset: [(x0, x1), ...]} -> pixels, rows counted from y0."""
    return [(x, y0 + dy) for dy, runs in rows.items() for a, b in runs for x in range(a, b + 1)]


def line(g, a, b, c):
    (x0, y0), (x1, y1) = a, b; n = max(abs(x1 - x0), abs(y1 - y0), 1)
    for i in range(n + 1): g.set(round(x0 + (x1 - x0) * i / n), round(y0 + (y1 - y0) * i / n), c)


GLYPHS = {"i": ["#", ".", "#", "#", "#"], "s": ["..", "##", "#.", ".#", "##"], "o": ["...", "###", "#.#", "#.#", "###"],
          "n": ["...", "##.", "#.#", "#.#", "#.#"], "a": ["...", "##.", "..#", "#.#", "###"], "l": ["#", "#", "#", "#", "#"]}


def text(g, s, x, y, c):
    for ch in s:
        for dy, row in enumerate(GLYPHS[ch]):
            for dx, p in enumerate(row):
                if p == "#": g.set(x + dx, y + dy, c)
        x += len(GLYPHS[ch][0]) + 1


def paint(lift=(0, 0), bob=0, swing=0, shut=False, sit=False, back=False):
    """One frame. lift: how far each foot is raised (yours-left, yours-right). bob: upper body up (+) / down (-).
    swing: hands move opposite ways. shut: eyes closed. sit: sitting on the floor (for the nap).
    back: seen from behind (for turning around): back of the head and cap, no face, plain shirt back."""
    g = Grid()
    dy = 15 - bob if sit else -bob                        # everything above the hips moves by dy
    Y = lambda y: y + dy

    # ---- legs and shoes
    if sit:
        g.fill(rect(16, 103, 47, 106), "p")
        for cx in (17.5, 46.5):
            g.fill(ellipse(cx, 108, 7.5, 3.5), lambda x, y: "F" if y >= 109 else "f")
    else:
        for (x0, x1), up_ in zip(((17, 30), (33, 46)), lift):
            g.fill(rect(x0, 92, x1, 104 - up_), lambda x, y, s=(x0 + x1) // 2: "P" if x == s else "p")
            g.fill(ellipse((x0 + x1 + 1) / 2, 106.5 - up_, 8, 3.5), lambda x, y, b=107 - up_: "F" if y >= b + 1 else "f")
        g.fill(rect(17, Y(88), 46, 93), lambda x, y: "P" if y == Y(88) else "p")

    # ---- arms (behind the torso) and hands
    for cx, s in ((11.5, swing), (52.5, -swing)):
        g.fill(ellipse(cx, Y(68), 5, 5) + rect(int(cx) - 3, Y(68), int(cx) + 4, Y(84) + s),
               lambda x, y, cx=cx: "T" if x < 32 and x + .5 < cx - 2.5 else "t")
        g.fill(ellipse(cx, Y(87) + s, 4, 3.5), "s")

    # ---- torso, open laced collar
    g.fill(ellipse(32, Y(70), 19, 8, lambda x, y: y <= Y(70)) + rect(14, Y(70), 49, Y(89)), "t")
    if back:                                                         # plain back with a collar line and a centre seam
        line(g, (24, Y(63)), (39, Y(63)), "T"); line(g, (32, Y(66)), (32, Y(86)), "T")
    else:
        collar = [(x, Y(62) + i) for i in range(12) for x in range(32 - max(1, 6 - i // 2), 32 + max(1, 6 - i // 2))]
        g.fill(collar, lambda x, y: "B" if noise(x, y, 3) < 40 else "b")
        for i, yy in enumerate((64, 68, 72)):
            a, b = (25 + i, Y(yy)), (38 - i, Y(yy))
            g.set(*a, "O"); g.set(*b, "O")
            if i < 2: line(g, (a[0] + 1, a[1]), (36 - i, Y(yy + 4)), "T"); line(g, (b[0] - 1, b[1]), (27 + i, Y(yy + 4)), "T")
        line(g, (32, Y(75)), (32, Y(86)), "k")

    # ---- neck, ears, head
    g.fill(rect(25, Y(56), 38, Y(63)), lambda x, y: "B" if noise(x, y, 4) < 50 else "b")
    for cx in (15.5, 48.5):
        g.fill(ellipse(cx, Y(41), 3.2, 5.5), lambda x, y, cx=cx: "S" if abs(x + .5 - cx) < 1.2 else "s")
    head = set(ellipse(32, Y(41), 16, 17) + ellipse(32, Y(49), 15, 11))
    ear = 15.5 if back else 48.5                                      # his left ear: on your right from the front
    if back:                                                          # back of the head: hair down to the nape, then neck
        g.fill(head, lambda x, y: ("k" if noise(x, y, 7) < 12 else "h") if y <= Y(52) else stubble(x, y))
    else:
        g.fill(head, "s")
    g.fill(ellipse(ear, Y(39), 1.6, 2.6), "u", line=False)                                # blue earpiece
    e = int(ear)
    for x, y in ((e, Y(46)), (e - 1, Y(47)), (e + 1, Y(47)), (e, Y(48))): g.set(x, y, "o")   # gold earring
    if back:
        g.fill(ellipse(32, Y(25), 18.5, 15, lambda x, y: y <= Y(25)), camo)               # cap crown, no lettering
        g.fill([(x, y) for x, y in ellipse(32, Y(26), 4, 3.5) if y <= Y(25)], "h")          # opening at the back
        line(g, (27, Y(23)), (37, Y(23)), "d"); g.set(32, Y(23), "r")                      # strap and buckle
        return g.rows()
    g.fill([(x, y) for x, y in head if (x < 19 or x > 44) and Y(28) <= y <= Y(44)], "h", line=False)   # sideburns
    g.fill([(x, y) for x, y in head if y >= Y(46) or ((x < 21 or x > 42) and y >= Y(42))], stubble, line=False)
    g.fill([(x, y) for x, y in head if y >= Y(55)], lambda x, y: "B" if noise(x, y, 5) < 60 else "b", line=False)

    # ---- brows, eyes, nose
    g.fill(spans({0: [(21, 28), (35, 42)], 1: [(20, 29), (34, 43)]}, Y(32)), "h", line=False)
    if shut:
        g.fill(spans({0: [(22, 22), (28, 28), (35, 35), (41, 41)], 1: [(23, 27), (36, 40)]}, Y(36)), "k", line=False)
    else:
        g.fill(spans({0: [(22, 28), (35, 41)]}, Y(35)), "k", line=False)                # heavy upper lids
        g.fill(spans({0: [(22, 28), (35, 41)], 1: [(23, 27), (36, 40)]}, Y(36)), "W", line=False)
        g.fill(spans({0: [(24, 26), (37, 39)], 1: [(24, 26), (37, 39)]}, Y(36)), "e", line=False)
        g.set(25, Y(36), "k"); g.set(38, Y(36), "k")
    g.fill(spans({0: [(23, 27), (36, 40)]}, Y(38)), "S", line=False)
    g.fill(spans({i: [(30, 30)] for i in range(6)}, Y(37)), "S", line=False)
    g.fill(spans({0: [(29, 34)], 1: [(28, 35)], 2: [(28, 35)]}, Y(43)),
           lambda x, y: "S" if x in (28, 35) or y == Y(45) else "s", line=False)
    g.set(29, Y(45), "k"); g.set(34, Y(45), "k")

    # ---- mustache, mouth
    g.fill(spans({0: [(26, 37)], 1: [(23, 40)], 2: [(21, 42)], 3: [(20, 43)], 4: [(20, 26), (37, 43)],
                  5: [(20, 24), (39, 43)], 6: [(21, 23), (40, 42)]}, Y(46)),
           lambda x, y: "M" if y <= Y(47) and noise(x, y, 6) < 35 else "m", line=False)
    g.fill(spans({0: [(27, 36)], 1: [(28, 35)]}, Y(50)), lambda x, y: "S" if y == Y(51) else "l", line=False)

    # ---- cap: crown, lettering, brim, rings
    g.fill(ellipse(32, Y(25), 18.5, 15, lambda x, y: y <= Y(25)), camo)
    text(g, "isional", 22, Y(14), "w")
    g.fill(ellipse(32, Y(26), 23, 4.5), lambda x, y: "d" if y >= Y(28) else "C" if y == Y(27) else camo(x, y))
    for cx, cy in ((10, 27), (12.5, 30)):
        g.fill(set(ellipse(cx, Y(cy), 2.4, 2.4)) - set(ellipse(cx, Y(cy), 1.2, 1.2)), "r", line=False)
    return g.rows()


# ---- poses. Each pose has a few animation phases; the live motion detail (from Chae's phone sensor) tweaks them:
# stride = how high the stepping foot lifts, arms = how far the hands swing, bob = extra body lift (+ up, - down),
# fidget = a small hand shuffle while standing. The defaults are the look without any sensor data.
PHASES = {"idle": 8, "walk": 4, "run": 4, "sleep": 2}
DEFAULT_DETAIL = {"walk": {"stride": 3, "arms": 2}, "run": {"stride": 6, "arms": 4}}


def turned(rows, angle):
    """He turns like a paper cut-out: angle 0 faces you, +-90 is edge-on, beyond that you see his back (rows must
    already be the back view then). He narrows by |cos(angle)| and slides a little the way he's turning."""
    f = abs(math.cos(math.radians(angle)))
    w = max(4, round(W * f))
    left = max(0, min(W - w, (W - w) // 2 - round(3 * math.sin(math.radians(angle)))))
    return [("." * left + "".join(r[min(W - 1, int((x + .5) * W / w))] for x in range(w))).ljust(W, ".") for r in rows]


@lru_cache(maxsize=2048)
def pick(pose, i, stride=None, arms=None, bob=0, fidget=0, turn=0):
    """The frame (tuple of rows) for animation phase i of pose, with optional live detail.
    turn: degrees he's turned away from you (-180..180, + = his right), from Chae's pivots."""
    if pose == "sleep": return tuple(paint(sit=True, shut=True, bob=-(i % 2)))           # breathing
    back = abs(turn) > 90
    if pose == "idle": kw = dict(bob=bob, swing=fidget, shut=i == 6)                     # phase 6 blinks
    else:
        d = DEFAULT_DETAIL[pose]
        stride, arms = d["stride"] if stride is None else stride, d["arms"] if arms is None else arms
        side = 1 if i < 2 else -1                                                        # which foot is stepping
        if pose == "walk":                                                               # stand, step, stand, other step
            up_, b, sw = (stride, 1, arms) if i % 2 else (0, 0, 0)
        else:                                                                            # run: push off high, then land
            up_, b, sw = (stride, 2, arms) if i % 2 == 0 else (max(1, stride // 3), 0, arms // 3)
        kw = dict(lift=(up_, 0) if side > 0 else (0, up_), bob=b + bob, swing=sw * side)
    rows = paint(back=back, **kw)
    return tuple(turned(rows, turn) if turn else rows)


STAND = list(pick("idle", 0))
FRAMES = {pose: [list(pick(pose, i)) for i in range(n)] for pose, n in PHASES.items()}


def double(rows): return ["".join(ch * 2 for ch in r) for r in rows for _ in (0, 1)]


# Audience: one small fan per listener, standing to his left. "x" is swapped for that fan's shirt colour.
FAN = double([
    "..kkkk..",
    ".kssssk.",
    ".kssssk.",
    ".kssssk.",
    "..kkkk..",
    ".kxxxxk.",
    "kxxxxxxk",
    "kxxxxxxk",
    "kxxxxxxk",
    ".kxxxxk.",
    ".kk..kk.",
    ".kk..kk.",
])
FAN_CHEER = double([                # arms up while he's moving
    "k.kkkk.k",
    "kksssskk",
    ".kssssk.",
    ".kssssk.",
    "..kkkk..",
    ".kxxxxk.",
    ".kxxxxk.",
    ".kxxxxk.",
    ".kxxxxk.",
    ".kxxxxk.",
    ".kk..kk.",
    ".kk..kk.",
])
FAN_W, FAN_H = len(FAN[0]), len(FAN)
MAX_FANS = 10                       # more listeners than this show as "+N"


def fan(i, cheer=False):
    """Rows for the i-th fan (colours cycle)."""
    c = FAN_COLORS[i % len(FAN_COLORS)]
    return [r.replace("x", c) for r in (FAN_CHEER if cheer else FAN)]


# Pixel font for the "+N" audience count (3x5, doubled).
DIGITS = {k: double(v) for k, v in {
    "0": ["kkk", "k.k", "k.k", "k.k", "kkk"], "1": [".k.", "kk.", ".k.", ".k.", "kkk"],
    "2": ["kkk", "..k", "kkk", "k..", "kkk"], "3": ["kkk", "..k", ".kk", "..k", "kkk"],
    "4": ["k.k", "k.k", "kkk", "..k", "..k"], "5": ["kkk", "k..", "kkk", "..k", "kkk"],
    "6": ["kkk", "k..", "kkk", "k.k", "kkk"], "7": ["kkk", "..k", ".k.", ".k.", ".k."],
    "8": ["kkk", "k.k", "kkk", "k.k", "kkk"], "9": ["kkk", "k.k", "kkk", "..k", "kkk"],
    "+": ["...", ".k.", "kkk", ".k.", "..."],
}.items()}
DIGIT_W, DIGIT_H = len(DIGITS["0"][0]), len(DIGITS["0"])

# "z" drawn above his head while he naps, at these spots (frame coordinates; negative y is in the headroom).
ZED = double(["kkkk", "..k.", ".k..", "kkkk"])
Z_SPOTS = [(44, 10), (50, 1), (56, -8)]
