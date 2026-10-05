"""Tests for walker.py: sprite data, what pose he's in, Chae's connection, the audience, and finding the feed."""
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


# ---------- Chae's connection and the audience (ConnectionMessage / ListenerCountMessage) ----------
CONNECTED = {"type": "connection", "data": {"connected": True}}
GONE = {"type": "connection", "data": {"connected": False}}


def test_naps_while_chae_is_disconnected_from_the_server():
    w = walker.Walker(); w.set_online(True); w.feed(CONNECTED)
    w.feed(STEP, 0); assert w.pose(0.1) == "walk"
    w.feed(GONE, 0.2); assert w.pose(0.3) == "sleep"                      # even mid-walk
    w.feed(CONNECTED, 1); assert w.pose(1.0 + walker.HOLD) == "idle"      # wakes up when Chae is back


def test_chae_status_is_forgotten_when_we_lose_the_feed():
    w = walker.Walker(); w.set_online(True); w.feed(GONE)
    w.set_online(False); assert w.chae is None and w.pose(0) == "sleep"
    w.set_online(True); assert w.pose(0) == "idle"                        # older servers never send a connection message


def test_bad_connection_messages_change_nothing():
    w = walker.Walker(); w.set_online(True)
    for m in ({"type": "connection", "data": {"connected": "no"}}, {"type": "connection", "data": {}},
              {"type": "connection"}, {"type": "connection", "data": [False]}):
        w.feed(m)
    assert w.chae is None and w.pose(0) == "idle"


def test_audience_is_everyone_listening_including_you():
    w = walker.Walker(); w.set_online(True)
    w.feed({"type": "listeners", "data": {"count": 1}}); assert w.listeners == 1     # just you
    w.feed({"type": "listeners", "data": {"count": 8}}); assert w.listeners == 8
    for bad in ({"type": "listeners", "data": {"count": -1}}, {"type": "listeners", "data": {"count": True}},
                {"type": "listeners", "count": 3}, {"listeners": 3}):
        w.feed(bad)
    assert w.listeners == 8
    w.feed({"type": "listeners", "data": {"count": 0}}); assert w.listeners == 0


def test_audience_leaves_when_we_lose_the_feed():
    w = walker.Walker(); w.set_online(True); w.feed({"type": "listeners", "data": {"count": 5}})
    w.set_online(False); assert w.listeners == 0


# ---------- finding the feed through openapi.json ----------
def test_listen_url_comes_from_the_openapi_document():
    spec = {"paths": {"/openapi.json": {"get": {}}, "/ws": {"get": {"summary": "send"}},
                      "/feeds/listen": {"get": {"x-websocket-messages": [{"direction": "server-to-client", "frame": "text"}]}}}}
    assert walker.listen_url(spec, "https://runchaerun.cactus.vg/") == "wss://runchaerun.cactus.vg/feeds/listen"
    assert walker.listen_url(spec, "http://localhost:3000") == "ws://localhost:3000/feeds/listen"


def test_no_listen_socket_without_the_openapi_document():
    for spec in (None, {}, {"paths": None}, [1], {"paths": {"/ws": {"get": {"x-websocket-messages": "?"}}}}):
        assert walker.listen_url(spec, "https://x.example") is None


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


# ---------- live motion detail from the phone's sensor stream ----------
def sensor(samples, thr=0.7): return {"type": "sensor", "data": {"samples": samples, "rejected": 0, "threshold": thr}}


def shake(w, start, secs, amp, thr=0.7):
    """Feed sensor batches every 0.1 s like the phone does."""
    for b in range(int(secs * 10)): w.feed(sensor([amp * (1 if k % 2 else -1) for k in range(6)], thr), start + b / 10)


def test_sensor_messages_are_motion_not_steps():
    w = walker.Walker(); w.set_online(True)
    shake(w, 0, 1, 0.7)
    assert w.last_step is None and w.pose(1) == "idle" and len(w.motion) == 60


def test_no_sensor_data_means_the_default_look():
    w = walker.Walker(); w.set_online(True); w.feed(STEP, 0)
    pose, i, detail = w.look(0.2)
    assert pose == "walk" and detail == () and sprites.pick(pose, i) == tuple(sprites.FRAMES[pose][i])


def test_harder_motion_means_longer_strides_and_bigger_arm_swings():
    def detail(amp):
        w = walker.Walker(); w.set_online(True); shake(w, 0, 1.5, amp); w.feed(STEP, 1.4)
        return dict(w.look(1.5)[2])
    soft, hard = detail(0.15), detail(1.2)
    assert soft["stride"] < hard["stride"] and soft["arms"] < hard["arms"]
    assert 2 <= soft["stride"] and hard["stride"] <= 6


def test_his_body_follows_the_phone_bounce():
    w = walker.Walker(); w.set_online(True)
    shake(w, 0, 1, 0.1); w.feed(sensor([1.4] * 6), 1.0)                  # a big push, threshold-sized and more
    assert dict(w.look(1.0 + walker.LAG + 0.01)[2])["bob"] == 2
    w.feed(sensor([-1.4] * 6), 1.1)
    assert dict(w.look(1.1 + walker.LAG + 0.01)[2])["bob"] == -2


def test_shuffling_without_a_counted_step_makes_him_fidget():
    w = walker.Walker(); w.set_online(True)
    shake(w, 0, 1.2, 0.5)                                                 # moving, but no step message
    pose, i, detail = w.look(1.2)
    assert pose == "idle" and dict(detail)["fidget"] in (-1, 1)
    w2 = walker.Walker(); w2.set_online(True); shake(w2, 0, 1.2, 0.05)
    assert dict(w2.look(1.2)[2])["fidget"] == 0


def test_motion_goes_stale_when_the_phone_stops_sending():
    w = walker.Walker(); w.set_online(True); shake(w, 0, 1, 1.0)
    assert w.look(1.0)[2] != () and w.look(5.0)[2] == () and w.signal(5.0) == 0


def test_bad_sensor_batches_are_harmless():
    w = walker.Walker(); w.set_online(True)
    for m in (sensor("x"), sensor([None, True, "1", 0.5]), sensor([0.5], thr=0), {"type": "sensor", "data": None},
              {"t": "sig", "v": [0.2, 0.3], "thr": 0.7}):
        w.feed(m, 0)
    assert all(isinstance(x, float) for _, x in w.motion) and w.pose(0.1) == "idle"


def test_every_detail_combination_draws_a_full_size_frame():
    for pose in ("walk", "run"):
        for i in range(sprites.PHASES[pose]):
            for stride in (2, 8):
                for bob in (-2, 2):
                    check(list(sprites.pick(pose, i, stride=stride, arms=6, bob=bob)), sprites.W, sprites.H)
    for fidget in (-1, 1): check(list(sprites.pick("idle", 0, bob=-2, fidget=fidget)), sprites.W, sprites.H)


# ---------- listener names ----------
def test_listener_names_come_with_the_count():
    w = walker.Walker(); w.set_online(True)
    w.feed({"type": "listeners", "data": {"count": 3, "names": ["Alex", "", "Nick"]}})
    assert w.listeners == 3 and w.names == ["Alex", "", "Nick"]
    w.feed({"type": "listeners", "data": {"count": 1}})                  # a server from before names existed
    assert w.listeners == 1 and w.names == []


def test_odd_names_are_made_safe():
    w = walker.Walker(); w.set_online(True)
    w.feed({"type": "listeners", "data": {"count": 3, "names": [None, 5, "x" * 100]}})
    assert w.names == ["", "", "x" * walker.NAME_CHARS]
    w.feed({"type": "listeners", "data": {"count": 2, "names": "Alex"}}); assert w.names == []


def test_names_are_forgotten_when_we_lose_the_feed():
    w = walker.Walker(); w.set_online(True); w.feed({"type": "listeners", "data": {"count": 1, "names": ["Alex"]}})
    w.set_online(False); assert w.names == []


def test_the_feed_says_hello_with_your_name():
    import asyncio, json, queue
    from aiohttp import web

    async def scenario():
        got = []
        async def doc(request):
            return web.json_response({"paths": {"/ws/listen": {"get": {"x-websocket-messages": [{"direction": "server-to-client"}]}}}})
        async def listen(request):
            ws = web.WebSocketResponse(); await ws.prepare(request)
            async for m in ws:
                got.append(json.loads(m.data))
                if len(got) == 2: await ws.close()
            return ws
        app = web.Application(); app.router.add_get("/openapi.json", doc); app.router.add_get("/ws/listen", listen)
        runner = web.AppRunner(app); await runner.setup(); site = web.TCPSite(runner, "127.0.0.1", 0); await site.start()
        port = site._server.sockets[0].getsockname()[1]
        feed = walker.Feed(queue.Queue(), f"http://127.0.0.1:{port}", "Alex")
        task = asyncio.ensure_future(feed.main())
        for _ in range(50):
            await asyncio.sleep(0.1)
            if got and feed.name == "Alex": feed.name = "Big Nick"         # renaming sends another hello
            if len(got) >= 2: break
        task.cancel(); await runner.cleanup()
        return got

    assert asyncio.run(scenario())[:2] == [{"type": "hello", "name": "Alex"}, {"type": "hello", "name": "Big Nick"}]


# ---------- turning (gyro heading from the /phone page) ----------
def turn_batch(heading): return {"type": "sensor", "data": {"samples": [0.0] * 6, "threshold": 0.7, "heading": heading, "turn_rate": 0}}


def test_a_pivot_turns_him_then_he_faces_you_again():
    w = walker.Walker(); w.set_online(True)
    for k in range(10): w.feed(turn_batch(10.0), k / 10)                 # standing still, heading steady
    assert w.facing(0.95) == 0
    for k in range(10): w.feed(turn_batch(10 + 18 * (k + 1)), 1 + k / 10)   # a quick 180 to the right in 1 s
    assert 60 < w.facing(1.95) <= 180
    for k in range(60): w.feed(turn_batch(190.0), 2 + k / 10)            # then stands still for 6 s
    assert abs(w.facing(7.95)) < 10


def test_turning_left_is_negative_and_wraps_around_360():
    w = walker.Walker(); w.set_online(True)
    w.feed(turn_batch(5.0), 0)
    for k in range(5): w.feed(turn_batch((5 - 15 * (k + 1)) % 360), 0.1 * (k + 1))   # crosses 0 -> 350, 335, ...
    assert -90 < w.facing(0.5) < -20


def test_turn_shows_in_the_drawing_details_and_goes_stale():
    w = walker.Walker(); w.set_online(True); w.feed(STEP, 0)
    w.feed(turn_batch(0.0), 0); w.feed(turn_batch(90.0), 0.1)
    turn = dict(w.look(0.15)[2]).get("turn")
    assert turn and turn % walker.TURN_STEP == 0 and turn > 0
    assert "turn" not in dict(w.look(5)[2]) and w.facing(5) == 0


def test_bad_headings_are_ignored():
    w = walker.Walker(); w.set_online(True)
    for h in ("90", None, True, float("nan"), float("inf")): w.feed(turn_batch(h), 0)
    assert w.heading is None and w.facing(0) == 0


def test_turned_frames_stay_full_size_and_show_his_back():
    front, back = sprites.pick("walk", 1, turn=0), sprites.pick("walk", 1, turn=180)
    assert front != back
    for a in (15, 45, 90, 135, 180, -45, -165):
        check(list(sprites.pick("walk", 1, turn=a)), sprites.W, sprites.H)
        check(list(sprites.pick("idle", 0, turn=a)), sprites.W, sprites.H)
    side = sprites.pick("idle", 0, turn=90)
    assert max(len(r.strip(".")) for r in side) < 10                      # edge-on he's a sliver
