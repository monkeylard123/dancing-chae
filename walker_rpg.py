"""
The "RPG" look for the desktop walker: a tiny 16x24 overworld sprite, like an old-school RPG hero, that walks
toward you, away from you, left and right. Which way he faces follows Chae's turning (the phone's gyro).

Same interface as walker_sprites (the classic look): W, H, HEADROOM, PHASES, Z_SPOTS and pick(pose, i, **detail).
The art is plain 16x24 character grids below (one character per pixel, colours from walker_sprites.PALETTE,
'.' transparent); pick() blows each pixel up to a BLOCK x BLOCK square so he's the same size as the classic look.
"""
from functools import lru_cache

NAME = "RPG"
BLOCK = 4                           # each art pixel is drawn this many screen pixels wide (at scale 1)
SW, SH = 16, 24                     # art size in pixels
TOP = 3                             # empty art rows above him, so hops never clip his cap
W, H = SW * BLOCK, (SH + TOP) * BLOCK   # frame size, like walker_sprites.W / H
HEADROOM = 8
PHASES = {"idle": 8, "walk": 4, "run": 4, "sleep": 2}
Z_SPOTS = [(40, 20), (46, 12), (52, 4)]

# ---- toward you ("down")
DOWN_HEAD = [
    "....kkkkkkkk....",
    "...kcgccdcgck...",
    "..kcgcwwwwcdck..",
    "..kdccgccgccdk..",
    ".kkddddddddddkk.",
    "..khsSSSSSSshk..",
    "..khsksssskshk..",
    ".kshsssSSssshuk.",
    "..kbmmmmmmmmbk..",
    "..kbbmllllmbbk..",
    "...kbbbbbbbbk...",
    "....kkbbbbkk....",
]
DOWN_BLINK = DOWN_HEAD[:6] + ["..khsSssssSshk.."] + DOWN_HEAD[7:]
DOWN_BODY = [
    "...kktbssbtkk...",
    "..kTtOkbbkOtTk..",
    "..kTttOkkOttTk..",
    ".kTkttttttttkTk.",
    ".kskttttttttksk.",
    "..kkppppppppkk..",
]
# ---- away from you ("up"): back of the cap with its strap, hair, earpiece now on your left
UP_HEAD = [
    "....kkkkkkkk....",
    "...kcgccdcgck...",
    "..kcgcdccgcdck..",
    "..kdccgcrcccdk..",
    "..kccckhhkccck..",
    "..khhhhhhhhhhk..",
    "..khhhhhhhhhhk..",
    ".kuhhhhhhhhhhsk.",
    "..khhhhhhhhhhk..",
    "..kbhhhhhhhhbk..",
    "...kbbbbbbbbk...",
    "....kkbbbbkk....",
]
UP_BODY = [
    "...kkttttttkk...",
    "..kTttttttttTk..",
    "..kTtttTTtttTk..",
    ".kTkttttttttkTk.",
    ".kskttttttttksk.",
    "..kkppppppppkk..",
]
FRONT_LEGS = {                      # shared by up and down: stand, his right foot up, his left foot up
    "stand": ["...kppppppppk...", "...kpppkkpppk...", "...kpppkkpppk...", "...kfffkkfffk...",
              "..kfffFkkFfffk..", "..kkkkk..kkkkk.."],
    "right": ["...kppppppppk...", "...kpppkkpppk...", "...kfffkkpppk...", "..kfffFkkpppk...",
              "..kkkkk.kFfffk..", "........kkkkk..."],
}
FRONT_LEGS["left"] = [r[::-1] for r in FRONT_LEGS["right"]]

# ---- side on, facing right (left is the mirror image): brim forward, earpiece and earring, mustache in profile
SIDE_HEAD = [
    ".....kkkkkk.....",
    "....kcgcdcck....",
    "...kcgccgcdck...",
    "...kdccgcccck...",
    "...kdddddddddddk",
    "...khhsssssk....",
    "...khussskssk...",
    "...khoSsssssSk..",
    "...kbbbbmmmmmk..",
    "...kbbbbbbmbk...",
    "....kbbbbbbk....",
    ".....kkbbkk.....",
]
SIDE_BLINK = SIDE_HEAD[:6] + ["...khusssSssk..."] + SIDE_HEAD[7:]
SIDE_BODY = {                       # arm hanging, swung forward, swung back
    "stand": [".....kttOk......", "....kttttOk.....", "....kTtttttk....", "....kTtttttk....",
              "....ktstttk.....", ".....kppppk....."],
    "fwd":   [".....kttOk......", "....kttttOk.....", "....kTtttttk....", "....ktTtttTk....",
              "....kttttttsk...", ".....kppppk....."],
    "back":  [".....kttOk......", "....kttttOk.....", "...kTttttttk....", "...kTktttttk....",
              "...kskttttk.....", ".....kppppk....."],
}
SIDE_LEGS = {
    "stand": [".....kppppk.....", ".....kppppk.....", ".....kpppk......", ".....kpppk......",
              ".....kffffk.....", ".....kkkkkk....."],
    "apart": [".....kppppk.....", "....kppkkppk....", "...kppk..kppk...", "...kpk....kpk...",
              "..kffk....kfffk.", "..kkkk....kkkkk."],
}

# ---- napping: sat down facing you, head nodded, eyes shut
SIT_HEAD = ["................"] * 5 + DOWN_HEAD[:6] + ["..khsSSssSSshk.."] + DOWN_HEAD[7:]
SIT_BODY = [
    "...kktbssbtkk...",
    "..kTtOkbbkOtTk..",
    ".kTkttOkkOttkTk.",
    ".kskttttttttksk.",
    "kppppppppppppppk",
    "kffkpppppppkkffk",
    "kkkk........kkkk",
]


def facing_to_direction(turn):
    """Degrees he's turned away from you (+ = his right, which is your left) -> down/left/up/right."""
    a = (turn + 180) % 360 - 180
    if abs(a) <= 45: return "down"
    if abs(a) >= 135: return "up"
    return "left" if a > 0 else "right"


def frame_rows(pose, i, direction="down"):
    """The 16x24 art for phase i of pose, facing direction. Walk/run phases: stand, step, stand, other step."""
    if pose == "sleep":
        rows = SIT_HEAD + SIT_BODY
        return rows if i % 2 == 0 else ["." * SW] + rows[:-1]           # breathing: he slumps a pixel
    step = pose in ("walk", "run") and i % 2 == 1
    other = i >= 2
    if direction in ("down", "up"):
        head = (DOWN_BLINK if pose == "idle" and i == 6 else DOWN_HEAD) if direction == "down" else UP_HEAD
        body = DOWN_BODY if direction == "down" else UP_BODY
        legs = FRONT_LEGS[("left" if other else "right") if step else "stand"]
        rows = head + body + legs
    else:
        head = SIDE_BLINK if pose == "idle" and i == 6 else SIDE_HEAD
        body = SIDE_BODY[("back" if other else "fwd") if step else "stand"]
        rows = head + body + SIDE_LEGS["apart" if step else "stand"]
        if direction == "left": rows = [r[::-1] for r in rows]
    return rows


def blow_up(rows, shift=0):
    """Each art pixel -> a BLOCK x BLOCK square; shift moves him up (+) or down (-) by that many screen pixels."""
    blank = "." * W
    big = [blank] * (TOP * BLOCK) + ["".join(ch * BLOCK for ch in r) for r in rows for _ in range(BLOCK)]
    if shift > 0: big = big[shift:] + [blank] * shift
    elif shift < 0: big = [blank] * -shift + big[:shift]
    return big


@lru_cache(maxsize=1024)
def pick(pose, i, stride=None, arms=None, bob=0, fidget=0, turn=0):
    """Same call as walker_sprites.pick. turn picks the direction; bob and the step hop move him up and down;
    stride/arms (step size from the phone's motion) make the hop bigger; fidget shuffles him sideways a little."""
    direction = "down" if pose == "sleep" else facing_to_direction(turn)
    hop = 0
    if pose in ("walk", "run") and i % 2 == 1:
        hop = BLOCK if pose == "walk" else 2 * BLOCK                 # a little hop on each step, more when running
        if stride is not None: hop += max(0, stride - (3 if pose == "walk" else 6))
    big = blow_up(frame_rows(pose, i, direction), hop + (bob if pose != "sleep" else 0))
    if fidget: big = [r[-fidget * 2:] + r[:-fidget * 2] for r in big]            # shift 2 px left/right (edges are blank)
    return tuple(big)
