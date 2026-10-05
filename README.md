# Dancing Chae

A little pixel-art Chae who lives on your desktop and walks when Chae walks. He is transparent, always on top, and
driven live by the step feed from [WalkPad (moovit)](https://github.com/chaepr/moovit) through the
[Chae WebSocket server](https://github.com/nicholas477/chae_ws_server).

| what's happening | what he does |
|---|---|
| steps are arriving | walks |
| steps are arriving fast (`speed` above WalkPad's `walk_max`, 0.65 by default) | runs |
| no step for 1.2 s | stands around, blinking now and then |
| Chae shuffles or sways without a counted step | bobs and fidgets on the spot |
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
python walker.py --demo                       # fake data: idle, walk, run, nap, with motion and a growing audience
python walker.py --scale 3                    # bigger (1 to 6, default 2)
python walker.py --server https://other.host  # another Chae WebSocket server (found through its openapi.json)
python walker.py --reset                      # forget the saved position and size
```

Transparency and click-through use Windows APIs. On macOS/Linux he runs, but with a dark box behind him.

## He's napping and Chae is walking?

Right-click him: the first line of the menu says what he's doing and why (for example `Napping: Can't reach ...` with
the error). Every connection attempt and error is also written to **`walker.log`** next to `walker.bat`; the menu has
**Open walker.log**. Send that file along when asking for help.

* **"Chae is disconnected from the server"**: he's right; Chae's WalkPad isn't connected right now.
* **"Can't reach ..."**: the error says why. To use a different address for the same server, right-click
  **Server: ... (change...)**; he reads that server's `openapi.json` and reconnects. It's remembered in `walker.json`.
* **Started from an old copy?** Close him (right-click **Quit**), `git pull` or download the ZIP again, and start
  `walker.bat` again. A running walker doesn't pick up new code.

`walker.bat` checks on every start that `aiohttp` is installed in `.venv`, so a `.venv` made by something else (an
editor, the tests) gets fixed instead of leaving him unable to connect.

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
* `{"type": "sensor", "data": {"samples": [...], "threshold": t}}`: the phone's motion signal, about 60 samples a
  second in batches of ~6. It is the acceleration-magnitude signal the phone's step detector uses (not rotation), so
  it tells him how hard and when Chae is moving, not which way. He plays it back ~0.1 s behind real time:
  * his body bobs up and down with each sample (divided by the step threshold, so a typical step peak is 1)
  * the last second's energy sets how high his feet lift and how far his arms swing, from soft steps to stomping
  * moving without a counted step makes him fidget on the spot
  * with no fresh samples (phone page closed) he falls back to his standard animation
* anything else is ignored.

## Changing how he looks

He is 64x112 pixels, painted from simple shapes in `paint()` in [`walker_sprites.py`](walker_sprites.py). Every
shape gets a 1-pixel outline automatically. Edit the coordinates and the `PALETTE` colours there; the poses
(`FRAMES`), the audience and the z's are in the same file. `walker.py` only animates whatever frames it finds.

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q
```

They cover the frame sizes and colours, the pose rules, the motion detail, Chae's connection status, the audience count, OpenAPI discovery
and the click-through calls (through a fake `user32`). Not covered: real transparency and hotkeys on screen.

## Files

* `walker.py`: connection, pose logic, and the transparent window
* `walker_sprites.py`: the art (palette, `paint()`, poses, fans, pixel font)
* `walker.bat`: one-click setup and launch on Windows
* `walker.log` (created when he runs): connection steps and errors
* `tests/test_walker.py`: tests
