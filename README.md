# Dancing Chae

A little pixel-art Chae who lives on your desktop and walks when Chae walks. He is transparent, always on top, and
driven live by the step feed from [WalkPad (moovit)](https://github.com/chaepr/moovit) through the
[Chae WebSocket server](https://github.com/nicholas477/chae_ws_server).

| what's happening | what he does |
|---|---|
| steps are arriving | walks |
| steps are arriving fast (`speed` above WalkPad's `walk_max`, 0.65 by default) | runs |
| no step for 1.2 s | stands around, blinking now and then |
| Chae is disconnected from the server (or he can't reach the server) | sits down for a nap, with z's rising |
| people are listening (you included) | a little audience gathers to his left and cheers while he moves (10 fans, then `+N`) |

## Run it (Windows)

1. Install [Python 3](https://www.python.org/downloads/) and tick **"Add python.exe to PATH"** in the installer.
2. Download this repo (**Code -> Download ZIP**, then unzip) or `git clone` it.
3. Double-click **`walker.bat`**.

The first run takes a few seconds while it sets up its own environment in `.venv` (it only installs `aiohttp`).
After that he starts straight away, with no console window.

The first time, he's **unlocked** (dashed outline): drag him where you want him, scroll the mouse wheel to resize him,
and right-click for a menu. Press **Ctrl+Alt+P** to lock him: a locked walker is click-through, so he never gets in your way.
Press Ctrl+Alt+P again to unlock him. Position and size are saved to `walker.json`.

### Without the .bat

```bash
pip install -r requirements.txt
python walker.py                              # live feed
python walker.py --demo                       # fake data: idle, walk, run, nap, with a growing audience
python walker.py --scale 3                    # bigger (1 to 6, default 2)
python walker.py --server https://other.host  # another Chae WebSocket server (found through its openapi.json)
python walker.py --reset                      # forget the saved position and size
```

Transparency and click-through use Windows APIs. On macOS/Linux he runs, but with a dark box behind him.

## Where the data comes from

He only ever finds the feed through the server's OpenAPI document. Before every (re)connect he reads
`https://runchaerun.cactus.vg/openapi.json` again and listens on the path that declares server-to-client
`x-websocket-messages` (today `/ws/listen`). If the document can't be read or names no such path, he keeps napping
and asks again a couple of seconds later.

Messages he uses (schemas in `openapi.json`):

* `{"type": "connection", "data": {"connected": true|false}}`: whether Chae's WalkPad is connected to the server.
  While it's `false` he naps. The server sends it as soon as he connects and again whenever Chae connects or disconnects.
* `{"type": "listeners", "data": {"count": n}}`: how many walkers/listeners are connected, yours included. Each one
  is a fan in the audience, so you always see yourself.
* `{"type": "step", "data": {"step", "speed", "gap", ...}}` and `{"type": "state", "data": {...}}`: Chae's steps and
  WalkPad's state. A state message's `cfg.walk_max` replaces the default run threshold. Bare step objects (what older
  server versions relayed) and WalkPad's bare state also work.
* `sensor` messages and anything else are ignored.

## Changing how he looks

He is 64x112 pixels, painted from simple shapes in `paint()` in [`walker_sprites.py`](walker_sprites.py). Every
shape gets a 1-pixel outline automatically. Edit the coordinates and the `PALETTE` colours there; the poses
(`FRAMES`), the audience and the z's are in the same file. `walker.py` only animates whatever frames it finds.

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q
```

They cover the frame sizes and colours, the pose rules, Chae's connection status, the audience count, OpenAPI discovery
and the click-through calls (through a fake `user32`). Not covered: real transparency and hotkeys on screen.

## Files

* `walker.py`: connection, pose logic, and the transparent window
* `walker_sprites.py`: the art (palette, `paint()`, poses, fans, pixel font)
* `walker.bat`: one-click setup and launch on Windows
* `tests/test_walker.py`: tests
