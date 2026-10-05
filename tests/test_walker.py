"""Tests for walker.py: sprite data, what pose he's in, and the audience count."""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import walker
import walker_sprites as sprites

STEP = {"gap": 0.5, "out": 0.5, "source": "phone", "speed": 0.5, "step": 1, "toon": "Default", "total": 396}   # listen-feed shape


# ---------- sprites ----------
def check(rows, w, h=None):
    assert all(len(r) == w for r in rows), rows
    assert h is None or len(rows) == h
    assert all(ch == "." or ch in sprites.PALETTE for r in rows for ch in r)


def test_every_frame_is_the_same_size_and_uses_known_colours():
    for pose, frames in sprites.FRAMES.items():
        assert frames and pose in walker.FPS
        for f in frames: check(f, sprites.W, sprites.H)
    for i in range(len(sprites.FAN_COLORS)):
        check(sprites.fan(i), sprites.FAN_W, sprites.FAN_H); check(sprites.fan(i, True), sprites.FAN_W, sprites.FAN_H)
    for g in sprites.DIGITS.values(): check(g, sprites.DIGIT_W, sprites.DIGIT_H)
    check(sprites.ZED, len(sprites.ZED[0]))


# ---------- pose ----------
def test_naps_while_disconnected_even_mid_walk():
    w = walker.Walker(); w.feed(STEP, 0)
    assert w.pose(0.1) == "sleep"
    w.set_online(True); assert w.pose(0.1) == "walk"
    w.set_online(False); assert w.pose(0.2) == "sleep"


def test_walks_after_a_step_then_goes_idle():
    w = walker.Walker(); w.set_online(True)
    assert w.pose(0) == "idle"
    w.feed(STEP, 10)
    assert w.pose(10.5) == "walk" and w.pose(10.01 + walker.HOLD) == "idle"   # the feed's speed never drops to 0 by itself


def test_runs_above_walkpads_walk_max():
    w = walker.Walker(); w.set_online(True)
    w.feed(dict(STEP, speed=0.72), 0); assert w.pose(0.1) == "run"
    w.feed(dict(STEP, speed=0.45), 1); assert w.pose(1.1) == "walk"


def test_state_messages_use_walkpads_own_threshold():
    w = walker.Walker(); w.set_online(True)
    w.feed({"type": "state", "data": {"steps": 5, "speed": 0.75, "cfg": {"walk_max": 0.8}, "output": "gamepad"}}, 0)
    assert w.pose(0.1) == "walk"                                           # 0.75 is a walk when walk_max is 0.8
    w.feed({"steps": 6, "speed": 0, "cfg": {"walk_max": 0.8}}, 5)          # bare state, new step
    assert w.pose(5.1) == "walk" and w.pose(5.01 + walker.HOLD) == "idle"


def test_other_messages_are_ignored():
    w = walker.Walker(); w.set_online(True)
    for m in ({"type": "login_response", "success": True}, {"type": "sensor", "data": {"samples": [1]}},
              {"t": "pong"}, "junk", None, [1, 2], {"hello": 1}):
        w.feed(m, 0)
    assert w.pose(0.1) == "idle"


def test_animation_frames_cycle():
    w = walker.Walker(); w.set_online(True); w.feed(STEP, 0)
    seen = {w.frame(t / 100)[1] for t in range(0, 100)}
    assert seen == set(range(len(sprites.FRAMES["walk"])))


# ---------- audience ----------
def test_listener_count_in_any_of_the_accepted_shapes():
    w = walker.Walker(); w.set_online(True)
    w.feed({"listeners": 3}); assert w.listeners == 3
    w.feed({"type": "listeners", "count": 7}); assert w.listeners == 7
    w.feed({"type": "audience", "data": {"count": 2}}); assert w.listeners == 2
    w.feed(dict(STEP, listeners=12), 0); assert w.listeners == 12 and w.pose(0.1) == "walk"   # riding along on a step
    w.feed({"listeners": -1}); w.feed({"listeners": True}); assert w.listeners == 12


def test_audience_leaves_when_disconnected():
    w = walker.Walker(); w.set_online(True); w.feed({"listeners": 4})
    w.set_online(False); assert w.listeners == 0


# ---------- finding the feed through openapi.json ----------
def test_listen_url_comes_from_the_openapi_document():
    spec = {"paths": {"/openapi.json": {"get": {}}, "/ws": {"get": {"summary": "send"}},
                      "/feeds/listen": {"get": {"x-websocket-messages": [{"direction": "server-to-client", "frame": "text"}]}}}}
    assert walker.listen_url(spec, "https://runchaerun.cactus.vg/") == "wss://runchaerun.cactus.vg/feeds/listen"
    assert walker.listen_url(spec, "http://localhost:3000") == "ws://localhost:3000/feeds/listen"


def test_listen_url_falls_back_when_the_document_is_missing_or_odd():
    for spec in (None, {}, {"paths": None}, [1], {"paths": {"/ws": {"get": {"x-websocket-messages": "?"}}}}):
        assert walker.listen_url(spec, "https://x.example") == "wss://x.example/ws/listen"


def test_new_step_envelope_from_openapi_is_understood():
    w = walker.Walker(); w.set_online(True)
    w.feed({"type": "step", "data": {"source": "phone", "step": 3, "speed": 0.9, "gap": 0.3}}, 0)
    assert w.pose(0.1) == "run"
    w.feed({"type": "sensor", "data": {"samples": [0.1], "rejected": 0, "threshold": 1.2}}, 5)
    assert w.pose(5.1) == "idle"


# ---------- Windows click-through (faked: we only check we ask Windows for the right things) ----------
class FakeUser32:
    def __init__(self): self.style, self.keys = 0x00000100, set()
    def GetAncestor(self, wid, flag): return 4242 if wid == 77 and flag == 2 else 0
    def GetWindowLongW(self, hwnd, idx): assert hwnd == 4242 and idx == -20; return self.style
    def SetWindowLongW(self, hwnd, idx, val): assert hwnd == 4242 and idx == -20; self.style = val
    def GetAsyncKeyState(self, vk): return 0x8000 if vk in self.keys else 0


def test_locking_makes_him_click_through_and_unlocking_undoes_it():
    u = FakeUser32(); w = walker.Win32(u); orig = u.style
    w.click_through(77, True)
    assert u.style & w.TRANSPARENT and u.style & w.LAYERED and u.style & w.NOACTIVATE and u.style & orig == orig
    w.click_through(77, False)
    assert not u.style & w.TRANSPARENT and not u.style & w.NOACTIVATE and u.style & w.LAYERED
    u.keys = {walker.LOCK_VK}; assert w.key_down(walker.LOCK_VK) and not w.key_down(0x11)
