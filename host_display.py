"""
host_display.py — Run this on the HOST PC.

The window stays dark. When MAKCU sends a left click to this PC,
the window flashes bright white so the capture card can detect it.

Requirements:
    pip install tkinter  (usually included with Python)

Usage:
    python host_display.py

Controls:
    Escape — quit
    r      — manual reset to dark (in case it got stuck)
"""

import tkinter as tk

# ── Configuration ──────────────────────────────────────────────────────────────
COLOR_IDLE      = "#0a0a0a"   # Near-black when waiting
COLOR_TRIGGERED = "#ffffff"   # Pure white when clicked
RESET_DELAY_MS  = 50          # How long to stay white before auto-reset (ms)
FULLSCREEN      = True        # Set False if you want a windowed mode
WINDOW_WIDTH    = 1280        # Used only when FULLSCREEN = False
WINDOW_HEIGHT   = 720
# ──────────────────────────────────────────────────────────────────────────────


class ColorDisplay:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Latency Test — Host Display")
        self.root.configure(bg=COLOR_IDLE)
        self.triggered = False
        self._reset_job = None

        if FULLSCREEN:
            self.root.attributes("-fullscreen", True)
        else:
            self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")

        # Canvas fills the entire window — catches all click events
        self.canvas = tk.Canvas(
            self.root,
            bg=COLOR_IDLE,
            highlightthickness=0,
            cursor="none",          # Hide cursor so it doesn't affect capture
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Status label (invisible on capture card at this font size)
        self.label = tk.Label(
            self.canvas,
            text="WAITING FOR CLICK",
            fg="#333333",
            bg=COLOR_IDLE,
            font=("Courier", 14),
        )
        self.label.place(relx=0.5, rely=0.5, anchor="center")

        # Bindings
        self.canvas.bind("<Button-1>", self._on_click)
        self.root.bind("<Button-1>", self._on_click)
        self.root.bind("<Escape>", lambda _: self.root.destroy())
        self.root.bind("r", lambda _: self._reset())
        self.root.bind("R", lambda _: self._reset())

        # Make sure window is on top and focused so MAKCU click lands here
        self.root.lift()
        self.root.focus_force()

    def _on_click(self, event=None):
        if self.triggered:
            return
        self.triggered = True

        # Cancel any pending reset
        if self._reset_job is not None:
            self.root.after_cancel(self._reset_job)

        # Flash white — update() forces an immediate redraw before returning
        self.canvas.configure(bg=COLOR_TRIGGERED)
        self.root.configure(bg=COLOR_TRIGGERED)
        self.label.configure(bg=COLOR_TRIGGERED, fg="#cccccc", text="TRIGGERED")
        self.root.update()  # Flush to display immediately

        # Schedule auto-reset
        self._reset_job = self.root.after(RESET_DELAY_MS, self._reset)

    def _reset(self):
        self._reset_job = None
        self.triggered = False
        self.canvas.configure(bg=COLOR_IDLE)
        self.root.configure(bg=COLOR_IDLE)
        self.label.configure(bg=COLOR_IDLE, fg="#333333", text="WAITING FOR CLICK")
        self.root.update()

    def run(self):
        print("Host display running.")
        print(f"  Idle color:     {COLOR_IDLE}")
        print(f"  Trigger color:  {COLOR_TRIGGERED}")
        print(f"  Auto-reset:     {RESET_DELAY_MS} ms")
        print(f"  Fullscreen:     {FULLSCREEN}")
        print("\nWindow is open. Send a click via MAKCU to trigger it.")
        print("Press Escape to quit.\n")
        self.root.mainloop()


if __name__ == "__main__":
    app = ColorDisplay()
    app.run()
