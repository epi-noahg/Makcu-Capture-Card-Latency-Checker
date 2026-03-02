# Video Capture Card Latency Tester

Measures end-to-end video capture card latency using a [MAKCU](https://makcu.com) USB HID controller. The tool fires a real hardware mouse click, detects the resulting screen flash through a capture card, and reports latency statistics across hundreds of automated runs.

## How It Works

```
┌─────────────────────────┐          ┌──────────────────────────────┐
│        HOST PC          │          │        CAPTURE PC            │
│                         │◄─ HDMI ──│  (capture card + MAKCU)      │
│  host_display.py        │          │                              │
│  ┌─────────────────┐    │          │  latency_tester.py           │
│  │  Dark window    │    │          │  1. drain capture buffer     │
│  │  flashes white  │    │          │  2. verify display is dark   │
│  │  on left click  │    │ ◄─ USB ──│  3. MAKCU fires left click ← t0
│  └─────────────────┘    │  (MAKCU) │  4. read frames until white  │
│                         │          │  5. report t1 − t0 in ms     │
└─────────────────────────┘          └──────────────────────────────┘
```

The timer starts the instant before `makcu.click()` is called. The measurement ends when the capture card frame crosses the brightness threshold — giving you the true round-trip latency: click → display renders → capture card delivers the frame.

## Requirements

**Host PC**
- Python 3.8+
- `tkinter` (included in most Python distributions)

**Capture PC**
- Python 3.8+
- MAKCU USB HID controller
- Video capture card
- macOS with AVFoundation (default backend), or adjust `open_capture()` for your platform

```bash
pip install opencv-python numpy makcu
```

## Setup

### 1. Host PC

Connect the host PC's display output to your capture card via HDMI (or whatever interface your card uses). Then run:

```bash
python host_display.py
```

The window goes fullscreen and stays near-black. It flashes white for 50 ms whenever a left click lands on it, then returns to dark automatically.

| Key | Action |
|-----|--------|
| `Esc` | Quit |
| `r` | Force reset to dark |

### 2. Capture PC

Point the MAKCU at the host PC (it will deliver clicks to the focused window). Then run:

```bash
python latency_tester.py
```

The script opens a **brightness monitor** first so you can verify the capture feed is working and the display is dark. Press `Ctrl+C` to start the test run.

## Configuration

Edit the `CONFIG` block at the top of each script.

### `latency_tester.py`

| Parameter | Default | Description |
|-----------|---------|-------------|
| `CAPTURE_DEVICE` | `0` | OpenCV device index — try 0, 1, 2 … |
| `CAPTURE_WIDTH/HEIGHT` | `1920×1080` | Capture resolution |
| `CAPTURE_FPS` | `120` | Requested frame rate |
| `BRIGHTNESS_IDLE` | `30` | Grayscale mean below this = "dark" |
| `BRIGHTNESS_TRIGGER` | `180` | Grayscale mean above this = "white" |
| `DETECTION_ROI` | `None` | `(x, y, w, h)` sub-region, or `None` for full frame |
| `NUM_TESTS` | `200` | Number of automated runs |
| `TEST_GAP_SECONDS` | `0.070` | Pause between tests (lets display settle) |
| `MAX_WAIT_SECONDS` | `0.5` | Timeout per test |
| `DRAIN_FRAMES` | `8` | Frames discarded before each test to flush the buffer |

**Tip:** Set `DETECTION_ROI` to a small region of the screen (e.g. `(400, 200, 480, 360)`) to reduce per-frame CPU cost and tighten the detection loop.

### `host_display.py`

| Parameter | Default | Description |
|-----------|---------|-------------|
| `COLOR_IDLE` | `#0a0a0a` | Near-black background color |
| `COLOR_TRIGGERED` | `#ffffff` | Flash color |
| `RESET_DELAY_MS` | `50` | How long the flash lasts |
| `FULLSCREEN` | `True` | Set `False` for windowed mode |

## Sample Output

```
╔══════════════════════════════════════════════════╗
║   Video Capture Card Latency Tester              ║
║   Capture PC side  (MAKCU + capture card)        ║
╚══════════════════════════════════════════════════╝

Opening capture device 0 … OK  (1920×1080 @ 120.0 fps)
Detection ROI: full frame

Connecting to MAKCU (debug=False) … connected.

── BRIGHTNESS MONITOR ───────────────────────────────────────
  Idle threshold    : < 30
  Trigger threshold : > 180
  Make sure the host display is dark before pressing Enter.
─────────────────────────────────────────────────────────────
  (Press Ctrl+C to stop monitoring and start tests)

  Brightness:    8.3  [DARK (ok)]        ^C

Running 200 tests  (gap: 70ms)

  [  1/200]  34.21 ms
  [  2/200]  31.88 ms
  ...
  [ 10/200]  33.05 ms
  ── [10/200]  avg 33.14  med 33.05  min 30.12  max 36.77  σ 1.82  ms

════════════════════════════════════════════════════════
  FINAL RESULTS
════════════════════════════════════════════════════════
  Successful : 200 / 200
  Min        : 28.44 ms
  Max        : 41.03 ms
  Average    : 33.21 ms
  Median     : 32.98 ms
  Std dev    :  2.14 ms
════════════════════════════════════════════════════════
```

## Accuracy Notes

- **Timer placement:** `t0` is recorded immediately before `makcu.click()` — as close to the hardware event as Python allows.
- **Buffer flushing:** `DRAIN_FRAMES=8` reads before each test discards stale frames so you never detect a flash from a previous run.
- **Buffer depth:** `CAP_PROP_BUFFERSIZE=1` minimizes how many frames OpenCV queues internally, reducing systematic offset.
- **Tight read loop:** The detection loop has no `sleep()` — it reads frames as fast as the capture card delivers them.
- **ROI detection:** Only the configured ROI is converted to grayscale and averaged, keeping CPU overhead low.

The measured latency includes: MAKCU USB HID latency + display render time + capture card digitization latency + frame delivery latency to OpenCV. It does **not** include network, input processing, or any software stack above the OS.
