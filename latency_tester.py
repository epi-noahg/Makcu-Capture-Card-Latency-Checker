"""
latency_tester.py — Run this on the CAPTURE PC (the one with MAKCU + capture card).

Flow per test:
  1. Drain stale frames from the capture card buffer
  2. Verify the host display is in its dark/idle state
  3. Send a left click via MAKCU  ← timer starts HERE (t0)
  4. Read frames as fast as possible until brightness spikes
  5. Record t1, report (t1 - t0) in milliseconds

Requirements:
    pip install opencv-python numpy makcu

Usage:
    python latency_tester.py

Tweak the CONFIG block below before running.
"""

import time
import statistics
import sys

import cv2
import numpy as np
from typing import Optional
from makcu import create_controller, MouseButton


# ── Configuration ──────────────────────────────────────────────────────────────
CAPTURE_DEVICE      = 0        # OpenCV device index for your capture card
                                # Try 0, 1, 2 … until you see the right feed
CAPTURE_WIDTH       = 1920
CAPTURE_HEIGHT      = 1080
CAPTURE_FPS         = 120

BRIGHTNESS_IDLE     = 30       # Frames below this are considered "dark/idle"
BRIGHTNESS_TRIGGER  = 180      # Frames above this count as "white/triggered"
                                # (0–255 grayscale average)

DETECTION_ROI       = None     # Region of interest: (x, y, w, h) in pixels,
                                # or None to use the full frame.
                                # Smaller ROI = faster detection loop.
                                # Example: (400, 200, 480, 360)

NUM_TESTS           = 200      # Number of measurement runs
TEST_GAP_SECONDS    = 0.070   # Pause AFTER host goes dark before next click (s)
MAX_WAIT_SECONDS    = 0.5     # Bail out if no change detected within this time
MAX_WAIT_DARK_SEC   = 0.5     # Max time to wait for host to return to dark (s)

DRAIN_FRAMES        = 8        # Frames to discard before each test to flush
                                # the capture card's internal buffer

MAKCU_DEBUG         = False    # Set True to see MAKCU serial traffic
# ──────────────────────────────────────────────────────────────────────────────


def brightness(frame: np.ndarray, roi=None) -> float:
    """Return mean grayscale brightness of frame (or roi sub-region)."""
    if roi is not None:
        x, y, w, h = roi
        frame = frame[y : y + h, x : x + w]
    return float(np.mean(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)))


def drain_buffer(cap: cv2.VideoCapture, n: int = DRAIN_FRAMES) -> Optional[np.ndarray]:
    """Read and discard n frames to flush the capture card buffer.
    Returns the last frame, or None on failure."""
    frame = None
    for _ in range(n):
        ok, frame = cap.read()
        if not ok:
            return None
    return frame


def open_capture(device: int) -> cv2.VideoCapture:
    cap = cv2.VideoCapture(device, cv2.CAP_AVFOUNDATION)
    if not cap.isOpened():
        raise RuntimeError(
            f"Cannot open capture device {device}.\n"
            "  • Try a different CAPTURE_DEVICE index (0, 1, 2 …)\n"
            "  • Make sure the capture card is plugged in and not in use."
        )
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  CAPTURE_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAPTURE_HEIGHT)
    cap.set(cv2.CAP_PROP_FPS,          CAPTURE_FPS)
    cap.set(cv2.CAP_PROP_BUFFERSIZE,   1)
    return cap


def preview_loop(cap: cv2.VideoCapture) -> None:
    """Print live brightness to terminal so the user can verify the feed."""
    print("\n── BRIGHTNESS MONITOR ───────────────────────────────────────")
    print(f"  Idle threshold    : < {BRIGHTNESS_IDLE}")
    print(f"  Trigger threshold : > {BRIGHTNESS_TRIGGER}")
    print("  Make sure the host display is dark before pressing Enter.")
    print("─────────────────────────────────────────────────────────────")
    print("  (Press Ctrl+C to stop monitoring and start tests)\n")

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("ERROR: lost capture signal.")
                break
            b = brightness(frame, DETECTION_ROI)
            status = "DARK (ok)" if b < BRIGHTNESS_IDLE else ("BRIGHT" if b > BRIGHTNESS_TRIGGER else "mid")
            print(f"\r  Brightness: {b:6.1f}  [{status}]        ", end="", flush=True)
    except KeyboardInterrupt:
        print("\n")


def wait_for_dark(cap: cv2.VideoCapture) -> None:
    """Poll capture card until the host display returns to idle (dark)."""
    deadline = time.perf_counter() + MAX_WAIT_DARK_SEC
    while time.perf_counter() < deadline:
        ok, frame = cap.read()
        if ok and brightness(frame, DETECTION_ROI) < BRIGHTNESS_IDLE:
            return


def run_single_test(makcu, cap: cv2.VideoCapture) -> Optional[float]:
    """
    Execute one latency measurement.
    Returns measured latency in ms, or None on failure.
    """
    # 1. Drain stale frames
    last_frame = drain_buffer(cap)
    if last_frame is None:
        return None

    # 2. Bail if host isn't dark yet
    if brightness(last_frame, DETECTION_ROI) > BRIGHTNESS_IDLE:
        return None

    # 3. Click + start timer atomically (as close as Python allows)
    t0 = time.perf_counter()
    makcu.click(MouseButton.LEFT)

    # 4. Tight read loop — no sleep, no overhead
    deadline = t0 + MAX_WAIT_SECONDS
    while True:
        ok, frame = cap.read()
        if not ok:
            return None

        if brightness(frame, DETECTION_ROI) >= BRIGHTNESS_TRIGGER:
            return (time.perf_counter() - t0) * 1000.0

        if time.perf_counter() > deadline:
            return None


STATS_INTERVAL = 10   # Print running stats every N successful tests


def print_running_stats(results: list, total: int) -> None:
    n = len(results)
    avg = statistics.mean(results)
    med = statistics.median(results)
    sd  = statistics.stdev(results) if n > 1 else 0.0
    print(f"  ── [{n}/{total}]  avg {avg:.2f}  med {med:.2f}  "
          f"min {min(results):.2f}  max {max(results):.2f}  σ {sd:.2f}  ms")


def print_results(results: list) -> None:
    print("\n" + "═" * 52)
    print("  FINAL RESULTS")
    print("═" * 52)
    print(f"  Successful : {len(results)} / {NUM_TESTS}")
    if results:
        print(f"  Min        : {min(results):.2f} ms")
        print(f"  Max        : {max(results):.2f} ms")
        print(f"  Average    : {statistics.mean(results):.2f} ms")
        print(f"  Median     : {statistics.median(results):.2f} ms")
        if len(results) > 1:
            print(f"  Std dev    : {statistics.stdev(results):.2f} ms")
    print("═" * 52 + "\n")


def main() -> None:
    print("╔══════════════════════════════════════════════════╗")
    print("║   Video Capture Card Latency Tester              ║")
    print("║   Capture PC side  (MAKCU + capture card)        ║")
    print("╚══════════════════════════════════════════════════╝\n")

    # ── Open capture card ──────────────────────────────────────────────────────
    print(f"Opening capture device {CAPTURE_DEVICE} … ", end="", flush=True)
    try:
        cap = open_capture(CAPTURE_DEVICE)
    except RuntimeError as e:
        print(f"\nERROR: {e}")
        sys.exit(1)

    w   = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h   = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    print(f"OK  ({w}×{h} @ {fps:.1f} fps)")

    if DETECTION_ROI is not None:
        x, y, rw, rh = DETECTION_ROI
        print(f"Detection ROI: ({x}, {y})  {rw}×{rh} px")
    else:
        print("Detection ROI: full frame")

    # ── Connect MAKCU ──────────────────────────────────────────────────────────
    print(f"\nConnecting to MAKCU (debug={MAKCU_DEBUG}) … ", end="", flush=True)
    makcu = create_controller(debug=MAKCU_DEBUG, auto_reconnect=True)
    print("connected.")

    try:
        # ── Preview ────────────────────────────────────────────────────────────
        preview_loop(cap)

        # ── Tests ──────────────────────────────────────────────────────────────
        print(f"\nRunning {NUM_TESTS} tests  (gap: {int(TEST_GAP_SECONDS * 1000)}ms)\n")
        results = []
        timeouts = 0
        w_n = len(str(NUM_TESTS))

        for n in range(1, NUM_TESTS + 1):
            if n > 1:
                wait_for_dark(cap)
                time.sleep(TEST_GAP_SECONDS)

            ms = run_single_test(makcu, cap)

            if ms is not None:
                results.append(ms)
                print(f"  [{n:{w_n}}/{NUM_TESTS}]  {ms:.2f} ms")
                if len(results) % STATS_INTERVAL == 0:
                    print_running_stats(results, NUM_TESTS)
            else:
                timeouts += 1
                print(f"  [{n:{w_n}}/{NUM_TESTS}]  SKIP")

        if timeouts:
            print(f"\n  ({timeouts} skipped / timed-out)")

        print_results(results)

    finally:
        print("Cleaning up …")
        makcu.disconnect()
        cap.release()
        cv2.destroyAllWindows()
        print("Done.")


if __name__ == "__main__":
    main()
