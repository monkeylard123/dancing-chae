# Dancing Chae

A little pixel-art Chae who lives on your desktop and walks when Chae walks. He is transparent, always on top, and
driven live by the step feed from [WalkPad (moovit)](https://github.com/chaepr/moovit) through the
[Chae WebSocket server](https://github.com/nicholas477/chae_ws_server).

| what's happening | what he does |
|---|---|
| steps are arriving | walks |
| steps are arriving fast (`speed` above WalkPad's `walk_max`, 0.65 by default) | runs |
| no step for 1.2 s | stands around, blinking now and then |
| the WebSocket is disconnected | sits down for a nap, with z's rising |
| listeners are connected | a little audience gathers to his left and cheers while he moves (10 fans, then `+N`) |

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
python walker.py --server https://other.host  # another Chae WebSocket server
python walker.py --url ws://127.0.0.1:8080/ws # skip discovery and listen to a socket directly
python walker.py --reset                      # forget the saved position and size
```

Transparency and click-through use Windows APIs. On macOS/Linux he runs, but with a dark box behind him.

## Where the data comes from

On every (re)connect he reads `https://runchaerun.cactus.vg/openapi.json` and listens on the path that declares
server-to-client `x-websocket-messages` (today `/ws/listen`). If the document can't be read, he uses `/ws/listen`.

Accepted messages:

* `{"type": "step", "data": {"step", "speed", "gap", ...}}` and `{"type": "state", "data": {...}}`: the `StepMessage` /
  `StateMessage` envelopes from `openapi.json`. A state message's `cfg.walk_max` replaces the default run threshold.
* bare step objects (`{"step", "speed", "gap", ...}`), which older server versions relayed, and WalkPad's bare state.
* **audience (not sent by the server yet):** `{"type": "listeners", "count": n}` (also `"audience"`, or `count` inside
  `data`), or a `"listeners": n` field on any message.
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

They cover the frame sizes and colours, the pose rules, the message shapes, the audience count, OpenAPI discovery
and the click-through calls (through a fake `user32`). Not covered: real transparency and hotkeys on screen.

## Files

* `walker.py`: connection, pose logic, and the transparent window
* `walker_sprites.py`: the art (palette, `paint()`, poses, fans, pixel font)
* `walker.bat`: one-click setup and launch on Windows
* `tests/test_walker.py`: tests
