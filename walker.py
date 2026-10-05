#!/usr/bin/env python3
"""
Dancing Chae - a little pixel-art guy who lives on your desktop and walks when Chae walks (Windows).

    py walker.py                          # finds the listen socket in https://runchaerun.cactus.vg/openapi.json
    py walker.py --server https://...     # another Chae WebSocket server (also found through its openapi.json)
    py walker.py --demo                   # fake data: idle, walk, run, then a nap when Chae "disconnects"

He walks while steps are coming in, runs when the pace is fast, stands around when you stop,
and naps whenever Chae is disconnected from the server (or he can't reach the server himself).

First run he starts UNLOCKED: drag him where you want, scroll to resize, right-click for a menu.
Ctrl+Alt+P locks/unlocks him; a locked walker is click-through.

The sprite art lives in walker_sprites.py. Only needs tkinter and aiohttp (see requirements.txt).
"""
import argparse, asyncio, ctypes, json, logging, logging.handlers, math, os, queue, sys, threading, time
from collections import OrderedDict, deque

import walker_sprites as sprites

IS_WINDOWS = sys.platform == "win32"
KEY = "#010203"                     # this exact colour becomes fully transparent (Windows)

DEFAULTS = {"x": None, "y": None, "scale": 2, "locked": False, "server": "https://runchaerun.cactus.vg", "name": None}
NAME_CHARS = 24     # the server keeps at most this many characters of a name
MIN_SCALE, MAX_SCALE = 1, 6
DATA = os.environ.get("WALKER_DATA_DIR") or os.path.dirname(os.path.abspath(__file__))
CONF, LOG = os.path.join(DATA, "walker.json"), os.path.join(DATA, "walker.log")
log = logging.getLogger("walker")
HOLD = 1.2          # keep walking this long after the last step (s)
RUN_SPEED = 0.66    # speed above which he runs, unless a state message brings WalkPad's own cfg (walk_max + 0.01)
FPS = {"idle": 2, "walk": 6, "run": 10, "sleep": 1}
BATCH = 0.1         # the phone sends a sensor batch about every 0.1 s; its samples are spread over that time
LAG = 0.12          # play the motion back this far behind real time, so a batch is always there to play
FRESH = 0.6         # motion data older than this (s) is ignored: the phone page stopped sending
FIDGET = 0.35       # standing still but moving this much (energy) makes him shuffle on the spot
TURN_STEP = 15      # turning is drawn in steps of this many degrees
LOCK_VK = 0x50      # Ctrl+Alt+P (WalkPad's stats overlay uses L/H/Q, so they can run side by side)


def load_conf(path=CONF):
    c = dict(DEFAULTS)
    try:
        with open(path) as f: c.update({k: v for k, v in json.load(f).items() if k in DEFAULTS})
    except (OSError, ValueError): pass
    return c


def save_conf(c, path=CONF):
    try:
        with open(path, "w") as f: json.dump(c, f, indent=2)
    except OSError: pass


# ---------------------------------------------------------------- Windows bits (isolated so they can be faked in tests)
class Win32:
    GWL_EXSTYLE, LAYERED, TRANSPARENT, TOOLWINDOW, NOACTIVATE = -20, 0x80000, 0x20, 0x80, 0x08000000

    def __init__(self, user32=None):
        self.user32 = user32 or (ctypes.windll.user32 if IS_WINDOWS else None)

    def click_through(self, wid, on):
        """on: mouse clicks pass straight through him. off: he can be dragged again."""
        u = self.user32
        if u is None: return
        hwnd = u.GetAncestor(wid, 2) or wid                  # Tk gives a child window; we need the top-level one
        st = u.GetWindowLongW(hwnd, self.GWL_EXSTYLE) | self.LAYERED | self.TOOLWINDOW
        st = (st | self.TRANSPARENT | self.NOACTIVATE) if on else (st & ~(self.TRANSPARENT | self.NOACTIVATE))
        u.SetWindowLongW(hwnd, self.GWL_EXSTYLE, st)

    def key_down(self, vk):
        return bool(self.user32 and self.user32.GetAsyncKeyState(vk) & 0x8000)


# ---------------------------------------------------------------- what he's doing (no GUI code: easy to test)
class Walker:
    """Turns feed messages and connection changes into a pose ("sleep", "idle", "walk", "run") and an animation frame."""
    def __init__(self):
        self.online, self.last_step, self.speed, self.run_speed, self.steps = False, None, 0.0, RUN_SPEED, None
        self.listeners, self.chae = 0, None          # chae: is Chae's WalkPad connected to the server (None = not told yet)
        self.names = []                              # listener names in join order ("" = didn't give one)
        self.motion = deque()                        # (time, sample / step threshold) from the phone's sensor batches
        self.heading, self.turn_at = None, None      # Chae's direction from the phone's gyro (0 = the way he faced at Start)

    def set_online(self, on):
        """Whether WE are connected to the listen feed."""
        self.online = on
        if not on:                                                    # unknown until the server tells us again
            self.listeners, self.chae, self.names = 0, None, []; self.motion.clear(); self.heading = None

    def status(self, m):
        """The server's ConnectionMessage {"type": "connection", "data": {"connected": bool}} and ListenerCountMessage
        {"type": "listeners", "data": {"count": n, "names": [...]}} (see openapi.json; servers before names existed
        send only the count). Returns True if m was one of them."""
        if not isinstance(m, dict) or not isinstance(m.get("data"), dict): return False
        d = m["data"]
        if m.get("type") == "connection":
            if isinstance(d.get("connected"), bool): self.chae = d["connected"]
            return True
        if m.get("type") == "listeners":
            n = d.get("count")
            if isinstance(n, int) and not isinstance(n, bool) and n >= 0: self.listeners = n   # includes you, watching him
            names = d.get("names")
            self.names = [x[:NAME_CHARS] if isinstance(x, str) else "" for x in names] if isinstance(names, list) else []
            return True
        return False

    @staticmethod
    def kind(m):
        """("step"|"state"|None, payload). The listen feed sends bare step objects ({"step", "speed", "gap", ...});
        WalkPad's outbound socket wraps them as {"type": "step"|"state", "data": {...}}; its own /ws sends bare state."""
        if not isinstance(m, dict): return None, None
        if isinstance(m.get("data"), dict) and m.get("type") in ("step", "state"): return m["type"], m["data"]
        if "type" in m or "t" in m: return None, None                 # login replies, sensor batches, pongs, ...
        if "steps" in m: return "state", m
        if "step" in m: return "step", m
        return None, None

    def sensor(self, m, now):
        """Phone motion: {"type": "sensor", "data": {"samples": [...], "threshold": t}} (or WalkPad's own {"t": "sig",
        "v": [...], "thr": t}). Samples are the phone's acceleration signal; dividing by the step threshold makes a
        typical step peak about 1. Returns True if m was one."""
        if not isinstance(m, dict): return False
        if m.get("type") == "sensor" and isinstance(m.get("data"), dict):
            v, thr = m["data"].get("samples"), m["data"].get("threshold"); self.turning(m["data"].get("heading"), now)
        elif m.get("t") == "sig": v, thr = m.get("v"), m.get("thr")
        else: return False
        v = [x for x in v if isinstance(x, (int, float)) and not isinstance(x, bool)] if isinstance(v, list) else []
        thr = thr if isinstance(thr, (int, float)) and thr > 0.05 else 1.0
        start = max(now, self.motion[-1][0] + BATCH / max(1, len(v))) if self.motion else now   # keep playback in order
        if start > now + 2 * BATCH:                                   # batches bunched up: don't drift behind
            while self.motion and self.motion[-1][0] >= now: self.motion.pop()
            start = now
        for k, x in enumerate(v): self.motion.append((start + k * BATCH / len(v), x / thr))
        while self.motion and self.motion[0][0] < now - 2: self.motion.popleft()
        return True

    def turning(self, heading, now):
        """Chae's heading: degrees turned since he tapped Start (or Reset) on the /phone page, clockwise from above.
        The way he faced then is "forward", which is facing you; the heading is how far he's turned from it."""
        if not isinstance(heading, (int, float)) or isinstance(heading, bool) or not math.isfinite(heading): return
        self.heading, self.turn_at = heading, now

    def facing(self, now):
        """How far he's turned away from you (-180..180 degrees, + = to his right): Chae's direction relative to how
        he faced at Start. 0 (facing you) without fresh gyro data."""
        if self.heading is None or self.turn_at is None or now - self.turn_at > FRESH: return 0.0
        return wrap(self.heading)

    def signal(self, now):
        """The motion sample playing right now (about 1 at a step peak), or 0 without fresh data."""
        at, val = now - LAG, 0.0
        for ts, x in self.motion:
            if ts > at: break
            val = x if at - ts < FRESH else 0.0
        return val

    def energy(self, now):
        """How hard he's moving over the last second (RMS of the samples, ~1 for firm steps), or None without data."""
        xs = [x for ts, x in self.motion if now - LAG - 1 <= ts <= now - LAG]
        return (sum(x * x for x in xs) / len(xs)) ** 0.5 if len(xs) >= 6 else None

    def look(self, now=None):
        """Everything needed to draw him: (pose, phase, detail) where detail feeds sprites.pick()."""
        now = time.time() if now is None else now
        pose, i = self.frame(now)
        e, sig = self.energy(now), self.signal(now)
        if pose == "sleep": return pose, i, ()
        turn = round(self.facing(now) / TURN_STEP) * TURN_STEP
        turn = (("turn", turn),) if turn else ()
        if e is None: return pose, i, turn
        bob = max(-2, min(2, round(sig * 2)))                         # his body follows the phone's bounce
        if pose == "idle":
            fidget = (1 if int(now * 4) % 2 else -1) if e > FIDGET else 0
            return pose, i, (("bob", bob), ("fidget", fidget)) + turn
        e = min(e, 1.5) / 1.5                                         # 0 = barely moving .. 1 = stomping
        base = 2 if pose == "walk" else 4
        return pose, i, (("stride", base + round(4 * e)), ("arms", base // 2 + round(4 * e)), ("bob", bob)) + turn

    def feed(self, m, now=None):
        now = time.time() if now is None else now
        if self.status(m) or self.sensor(m, now): return
        kind, d = self.kind(m)
        if kind is None: return
        speed = d.get("speed")
        if isinstance(speed, (int, float)): self.speed = speed
        if kind == "step":
            self.last_step = now
        else:
            steps = d.get("steps")
            if isinstance(steps, int):
                if self.steps is not None and steps > self.steps: self.last_step = now
                self.steps = steps
            if isinstance(speed, (int, float)) and speed > 0: self.last_step = now     # WalkPad's speed fades out after the last step
            cfg = d.get("cfg") or {}
            if isinstance(cfg.get("walk_max"), (int, float)) and d.get("output", "gamepad") == "gamepad":
                self.run_speed = cfg["walk_max"] + 0.01

    def pose(self, now=None):
        now = time.time() if now is None else now
        if not self.online or self.chae is False: return "sleep"
        if self.last_step is None or now - self.last_step >= HOLD: return "idle"
        return "run" if self.speed > self.run_speed else "walk"

    def frame(self, now=None):
        """(pose, animation phase)."""
        now = time.time() if now is None else now
        p = self.pose(now)
        return p, int(now * FPS[p]) % sprites.PHASES[p]


def wrap(deg):
    """An angle difference brought into -180..180."""
    return (deg + 180) % 360 - 180


# ---------------------------------------------------------------- data sources
def listen_url(spec, server):
    """The WebSocket URL to listen on, from the server's OpenAPI document: the path that declares server-to-client
    x-websocket-messages (preferring one with "listen" in it). None if the document doesn't name one."""
    found = []
    paths = (spec or {}).get("paths") if isinstance(spec, dict) else None
    for path, ops in (paths or {}).items():
        msgs = ((ops or {}).get("get") or {}).get("x-websocket-messages") or []
        if any(isinstance(m, dict) and m.get("direction") == "server-to-client" for m in msgs): found.append(path)
    if not found: return None
    path = sorted(found, key=lambda p: ("listen" not in p, p))[0]
    base = server.rstrip("/")
    if base.startswith("https://"): base = "wss://" + base[8:]
    elif base.startswith("http://"): base = "ws://" + base[7:]
    return base + path


class Feed(threading.Thread):
    """Listens to the WebSocket and reconnects forever. Only reports "online" once the connection proves itself
    (a message arrives or it stays open 2 s), so a server that accepts and instantly drops us doesn't wake him up.
    Where to listen always comes from the server's /openapi.json, queried again before every (re)connect;
    if it can't be read or names no listen socket, he stays asleep and asks again.
    Every step and error goes to walker.log and to the right-click menu ("status" messages), so a nap can be explained.
    Setting .server switches servers: the current connection is dropped and the new server's openapi.json is read."""
    def __init__(self, q, server, name=None):
        super().__init__(daemon=True); self.q, self.server, self.name, self.last = q, server, name, None

    def run(self):
        try: asyncio.run(self.main())
        except BaseException as e:                                    # e.g. aiohttp missing: say so instead of napping silently
            self.say(f"Feed stopped: {type(e).__name__}: {e}", logging.ERROR)

    def say(self, text, level=logging.INFO):
        if text != self.last: log.log(level, text); self.last = text
        self.q.put(("status", text))

    async def resolve(self, s, server):
        """The listen URL from server's openapi.json; raises with a readable reason if there isn't one."""
        import aiohttp
        doc = server.rstrip("/") + "/openapi.json"
        async with s.get(doc, timeout=aiohttp.ClientTimeout(total=10)) as r:
            if r.status != 200: raise ConnectionError(f"{doc} answered HTTP {r.status}")
            url = listen_url(await r.json(content_type=None), server)
        if url is None: raise ConnectionError(f"{doc} doesn't name a listen socket")
        return url

    async def main(self):
        import aiohttp, certifi, ssl
        # certifi's certificate list: some Python installs can't verify the server's HTTPS certificate otherwise
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        while True:
            told, server = False, self.server
            try:                                                      # a session closes its connector, so a new one each try
                async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl_context)) as s:
                    self.say(f"Reading {server.rstrip('/')}/openapi.json")
                    url = await self.resolve(s, server)
                    self.say(f"Connecting to {url}")
                    async with s.ws_connect(url, heartbeat=15) as ws:
                        opened, sent = time.time(), None
                        while self.server == server:
                            if self.name is not None and self.name != sent:      # tell the server who's watching
                                await ws.send_str(json.dumps({"type": "hello", "name": self.name})); sent = self.name
                            try: m = await ws.receive(timeout=0.5)
                            except asyncio.TimeoutError: m = None
                            if m is not None and m.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED,
                                                            aiohttp.WSMsgType.CLOSING, aiohttp.WSMsgType.ERROR): break
                            if not told and (m is not None or time.time() - opened > 2):
                                self.q.put(("online", True)); told = True; self.say(f"Connected to {url}")
                            if m is not None and m.type == aiohttp.WSMsgType.TEXT:
                                try: self.q.put(("msg", json.loads(m.data)))
                                except ValueError: pass
                        if self.server == server: self.say(f"{url} closed the connection", logging.WARNING)
            except Exception as e:
                self.say(f"Can't reach {server}: {type(e).__name__}: {e}".rstrip(": "), logging.WARNING)
            if told: self.q.put(("online", False))
            if self.server == server: await asyncio.sleep(2)


class Demo(threading.Thread):
    """Fake data: idle (with a full pivot), walk, run, idle, then Chae disconnects (nap), repeating. Sends phone motion too."""
    def __init__(self, q): super().__init__(daemon=True); self.q = q

    heading = 0.0

    def motion(self, gap, strength, secs, spin=0.0):
        """Sensor batches every 0.1 s for secs: a bump per step (or a little sway while standing), turning at spin deg/s."""
        for b in range(max(1, round(secs / BATCH))):
            self.heading = (self.heading + spin * BATCH) % 360
            t0 = time.time()
            if gap: v = [strength * 0.9 * math.sin(math.pi * 2 * (t0 + k * BATCH / 6) / gap) for k in range(6)]
            else: v = [0.12 * math.sin(t0 * 3 + k * 0.1) for k in range(6)]
            self.q.put(("msg", {"type": "sensor", "data": {"samples": [round(x, 2) for x in v], "rejected": 0, "threshold": 1.0,
                                                           "heading": round(self.heading, 1), "turn_rate": spin}}))
            time.sleep(BATCH)

    def run(self):
        steps, fans = 0, 0
        while True:
            self.q.put(("online", True)); self.q.put(("msg", {"type": "connection", "data": {"connected": True}}))
            for gap, speed, secs in ((None, 0, 3), (0.55, 0.5, 6), (0.3, 0.95, 5), (None, 0, 3)):
                fans = fans + 3 if fans < 14 else 1                   # listeners hop in, up past the "+N" limit
                names = ["Alex", "Nick", "", "Chae's mum", "a very long name that gets shortened", "Sam", "Jo", "", "Kit", "Lee"]
                self.q.put(("msg", {"type": "listeners", "data": {"count": fans, "names": (names * 2)[:fans]}}))
                end = time.time() + secs
                while time.time() < end:
                    if gap:                                           # same shape as the listen feed (openapi StepMessage)
                        steps += 1
                        self.q.put(("msg", {"type": "step", "data": {"step": steps, "gap": gap, "speed": speed, "out": speed,
                                                                     "source": "phone"}}))
                    first_idle = gap is None and secs == 3 and time.time() < end - 1.5
                    self.motion(gap, 1.4 if gap and gap < 0.4 else 1.0, gap or 0.5, 360 if first_idle else 0)   # a full pivot
            self.q.put(("msg", {"type": "connection", "data": {"connected": False}})); time.sleep(6)


# ---------------------------------------------------------------- the window
class App:
    def __init__(self, conf, source, win=None):
        import tkinter as tk
        self.tk, self.c, self.walker, self.q = tk, conf, Walker(), queue.Queue()
        self.win, self.drag, self.cache, self.shown, self.lock_down = win or Win32(), None, OrderedDict(), None, False
        self.placed_crowd, self.fonts = (0, 0), {}
        if IS_WINDOWS:
            try: ctypes.windll.shcore.SetProcessDpiAwareness(2)
            except Exception: pass
        self.root = tk.Tk(); self.root.title("Dancing Chae"); self.root.overrideredirect(True)
        self.root.attributes("-topmost", True); self.root.configure(bg=KEY)
        try: self.root.attributes("-transparentcolor", KEY)
        except tk.TclError: pass                                      # not supported off Windows
        self.cv = tk.Canvas(self.root, bg=KEY, highlightthickness=0, bd=0); self.cv.pack(fill="both", expand=True)
        self.cv.bind("<ButtonPress-1>", self.press); self.cv.bind("<B1-Motion>", self.move)
        self.cv.bind("<ButtonRelease-1>", lambda e: save_conf(self.c))
        self.cv.bind("<MouseWheel>", lambda e: self.resize(1 if e.delta > 0 else -1))
        self.cv.bind("<Button-3>", self.menu)
        self.status = None
        self.feed = source(self.q); self.feed.start()
        self.place(); self.draw(); self.root.update(); self.set_locked(self.c["locked"], save=False)
        if self.c.get("name") is None and hasattr(self.feed, "name"): self.root.after(300, self.ask_name)   # first run
        self.root.after(50, self.tick)

    # ----- behaviour
    def crowd(self):
        """(fans drawn, extra listeners shown as "+N")."""
        n = self.walker.listeners; shown = min(n, sprites.MAX_FANS); return shown, n - shown

    @staticmethod
    def label(extra): return f"+{extra}" if extra else ""

    def crowd_w(self):
        """Width (sprite pixels) of the audience to his left: the "+N" label, then the fans (with room for the
        outermost fan's name tag to stick out)."""
        shown, extra = self.crowd()
        return len(self.label(extra)) * (sprites.DIGIT_W + 2) + shown * (sprites.FAN_W + 2) + (2 + sprites.FAN_W if shown else 0)

    def size(self):
        """Window size: the audience, then him, with headroom for the z's."""
        s = self.c["scale"]
        return (self.crowd_w() + sprites.W) * s, (sprites.H + sprites.HEADROOM) * s

    def place(self):
        """c["x"], c["y"] is where HE stands; the window grows to the left as listeners arrive, so he never moves."""
        w, h = self.size()
        if self.c["x"] is None:
            self.c["x"], self.c["y"] = self.root.winfo_screenwidth() - sprites.W * self.c["scale"] - 40, self.root.winfo_screenheight() - h - 60
        self.root.geometry(f'{w}x{h}+{int(self.c["x"]) - self.crowd_w() * self.c["scale"]}+{int(self.c["y"])}')

    def set_locked(self, on, save=True):
        self.c["locked"] = on; self.win.click_through(self.root.winfo_id(), on); self.shown = None; self.draw()
        if save: save_conf(self.c)

    def resize(self, d):
        self.c["scale"] = max(MIN_SCALE, min(MAX_SCALE, self.c["scale"] + d)); self.place(); self.shown = None; self.draw(); save_conf(self.c)

    def press(self, e): self.drag = (e.x_root - self.root.winfo_x(), e.y_root - self.root.winfo_y())

    def move(self, e):
        if self.drag and not self.c["locked"]:
            left, self.c["y"] = e.x_root - self.drag[0], e.y_root - self.drag[1]
            self.c["x"] = left + self.crowd_w() * self.c["scale"]
            self.root.geometry(f"+{left}+{self.c['y']}")

    def why(self):
        """One line for the menu: what he's doing and why."""
        w = self.walker
        if w.online and w.chae is False: return "Napping: Chae is disconnected from the server"
        if w.online: return "Connected" + (f", {w.listeners} listening" if w.listeners else "")
        return "Napping: " + (self.status or "connecting...")

    def ask_name(self):
        """Asks who's watching; the name labels you in Chae's audience. Cancel keeps the current one."""
        from tkinter import simpledialog
        new = simpledialog.askstring("Dancing Chae", "What's your name? It labels you in Chae's audience:",
                                     initialvalue=self.c.get("name") or "", parent=self.root)
        if new is None: return
        self.c["name"] = " ".join(new.split())[:NAME_CHARS]; save_conf(self.c); log.info("Name set to %r", self.c["name"])
        if hasattr(self.feed, "name"): self.feed.name = self.c["name"]
        self.shown = None

    def change_server(self):
        from tkinter import simpledialog
        new = simpledialog.askstring("Dancing Chae", "Chae WebSocket server (its openapi.json is read):",
                                     initialvalue=self.c["server"], parent=self.root)
        if new and new.strip() and new.strip() != self.c["server"]:
            self.c["server"] = new.strip(); save_conf(self.c); log.info("Server changed to %s", self.c["server"])
            if hasattr(self.feed, "server"): self.feed.server = self.c["server"]

    def menu(self, e):
        m = self.tk.Menu(self.root, tearoff=0)
        m.add_command(label=self.why()[:90], state="disabled")
        m.add_command(label=f"Name: {self.c.get('name') or '(none)'}  (change...)", command=self.ask_name)
        m.add_command(label=f"Server: {self.c['server']}  (change...)", command=self.change_server)
        m.add_command(label="Open walker.log", command=lambda: os.startfile(LOG) if IS_WINDOWS and os.path.exists(LOG) else None)
        m.add_separator()
        m.add_command(label="Lock (click-through)  Ctrl+Alt+P", command=lambda: self.set_locked(True))
        m.add_command(label="Bigger", command=lambda: self.resize(1)); m.add_command(label="Smaller", command=lambda: self.resize(-1))
        m.add_separator(); m.add_command(label="Quit", command=self.quit)
        m.tk_popup(e.x_root, e.y_root)

    def quit(self): save_conf(self.c); self.root.destroy()

    def tick(self):
        try:
            while True:
                kind, val = self.q.get_nowait()
                if kind == "online": self.walker.set_online(val)
                elif kind == "status": self.status = val
                else:
                    was = self.walker.chae; self.walker.feed(val)
                    if self.walker.chae != was and self.walker.chae is not None:
                        log.info("Chae is %s", "connected" if self.walker.chae else "disconnected")
        except queue.Empty: pass
        if self.crowd() != self.placed_crowd: self.placed_crowd = self.crowd(); self.place()
        combo = self.win.key_down(0x11) and self.win.key_down(0x12) and self.win.key_down(LOCK_VK)
        if combo and not self.lock_down: self.set_locked(not self.c["locked"])
        self.lock_down = combo
        self.draw()
        self.root.after(50, self.tick)

    # ----- drawing
    def image(self, rows):
        """A Tk image of one frame at the current scale (pixels not put stay transparent)."""
        key = (tuple(rows), self.c["scale"])
        if key in self.cache: self.cache.move_to_end(key)
        else:
            if len(self.cache) > 300: self.cache.popitem(last=False)  # live motion makes many variants; keep the recent ones
            img = self.tk.PhotoImage(width=len(rows[0]), height=len(rows))
            for y, row in enumerate(rows):                            # one put per run of same-coloured pixels
                x = 0
                while x < len(row):
                    end = x
                    while end < len(row) and row[end] == row[x]: end += 1
                    if row[x] != ".": img.put(sprites.PALETTE[row[x]], to=(x, y, end, y + 1))
                    x = end
            self.cache[key] = img.zoom(self.c["scale"])
        return self.cache[key]

    def tag(self, text, x, y, width, mine=False):
        """A name label centred at x with its bottom at y, shortened to fit width; yours is gold."""
        import tkinter.font as tkf
        px = max(9, int(5 * self.c["scale"]))
        f = self.fonts.get(px) or self.fonts.setdefault(px, tkf.Font(family="Segoe UI" if IS_WINDOWS else "DejaVu Sans", size=-px, weight="bold"))
        if f.measure(text) > width:
            while text and f.measure(text + "...") > width: text = text[:-1]
            text += "..."
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1), (1, 1)):        # dark outline so it reads on any wallpaper
            self.cv.create_text(x + dx, y + dy, text=text, font=f, fill="#111111", anchor="s")
        self.cv.create_text(x, y, text=text, font=f, fill="#fbbf24" if mine else "#ffffff", anchor="s")

    def draw(self):
        pose, i, detail = self.walker.look()
        z = int(time.time() * 1.5) % 3 if pose == "sleep" else -1
        cheer = int(time.time() * 4) if pose in ("walk", "run") else -1   # the crowd cheers while he moves
        key = (pose, i, detail, z, cheer, self.crowd(), tuple(self.walker.names))
        if key == self.shown: return
        self.shown = key; s = self.c["scale"]; w, h = self.size(); (shown, extra) = self.crowd()
        self.cv.delete("all")
        top, bottom, me = sprites.HEADROOM, sprites.H + sprites.HEADROOM, self.crowd_w()
        self.cv.create_image(me * s, top * s, image=self.image(sprites.pick(pose, i, **dict(detail))), anchor="nw")
        lx = 0                                                        # audience to his left: "+N" furthest out, then the fans
        for ch in self.label(extra):
            self.cv.create_image(lx * s, (bottom - sprites.DIGIT_H - 2) * s, image=self.image(sprites.DIGITS[ch]), anchor="nw")
            lx += sprites.DIGIT_W + 2
        for j in range(shown):                                        # fan 0 stands next to him, newer ones further left
            up_ = cheer >= 0 and (cheer + j) % 2 == 0
            fx = me - 2 - (j + 1) * (sprites.FAN_W + 2) + 2
            self.cv.create_image(fx * s, (bottom - sprites.FAN_H - (2 if up_ else 0)) * s, image=self.image(sprites.fan(j, up_)), anchor="nw")
            if j < len(self.walker.names) and self.walker.names[j]:  # name tag above the fan, alternating heights so they fit
                self.tag(self.walker.names[j], (fx + sprites.FAN_W / 2) * s, (bottom - sprites.FAN_H - 4 - 9 * (j % 2)) * s,
                         2 * (sprites.FAN_W + 2) * s, mine=self.walker.names[j] == self.c.get("name"))
        for zx, zy in sprites.Z_SPOTS[:z + 1]:                        # z's rise one by one while he naps
            self.cv.create_image((me + zx) * s, (top + zy) * s, image=self.image(sprites.ZED), anchor="nw")
        if not self.c["locked"]: self.cv.create_rectangle(1, 1, w - 2, h - 2, outline="#fbbf24", dash=(4, 3))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Dancing Chae desktop walker")
    ap.add_argument("--server", help=f"Chae WebSocket server to read openapi.json from (default {DEFAULTS['server']})")
    ap.add_argument("--demo", action="store_true", help="use fake data")
    ap.add_argument("--scale", type=int, help=f"pixel size, {MIN_SCALE} to {MAX_SCALE} (default {DEFAULTS['scale']})")
    ap.add_argument("--unlock", action="store_true", help="start unlocked so you can move him")
    ap.add_argument("--reset", action="store_true", help="forget the saved position and settings")
    a = ap.parse_args(argv)
    conf = dict(DEFAULTS) if a.reset else load_conf()
    if a.server: conf["server"] = a.server
    if a.scale: conf["scale"] = a.scale
    conf["scale"] = max(MIN_SCALE, min(MAX_SCALE, int(conf["scale"])))
    if a.unlock or a.reset or not os.path.exists(CONF): conf["locked"] = False
    try:
        h = logging.handlers.RotatingFileHandler(LOG, maxBytes=200_000, backupCount=1, encoding="utf-8")
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s")); log.addHandler(h); log.setLevel(logging.INFO)
    except OSError: pass
    log.info("Starting, server %s", conf["server"])
    app = App(conf, (lambda q: Demo(q)) if a.demo else (lambda q: Feed(q, conf["server"], conf.get("name"))))
    print("Dancing Chae running.  Right-click for the menu, Ctrl+Alt+P lock/unlock", flush=True)
    app.root.mainloop(); save_conf(conf)


if __name__ == "__main__":
    main()
