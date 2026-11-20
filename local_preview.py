"""One on-demand local video preview for the native workspace."""
import math
import tkinter as tk
from tkinter import ttk

import tema


class Preview:
    def __init__(self, parent, external):
        self.frame = ttk.Frame(parent, style="Card.TFrame", padding=6)
        self.picture = tk.Label(self.frame, text="Selecione um clipe")
        self.picture.pack(fill="both", expand=True)
        buttons = ttk.Frame(self.frame, style="Card.TFrame")
        buttons.pack(fill="x", pady=(5, 0))
        self.play_button = ttk.Button(buttons, text="Reproduzir", style="Compact.TButton",
                                      command=self.toggle, state="disabled")
        self.play_button.pack(side="left")
        self.external = external
        self.open_button = ttk.Button(buttons, text="Abrir MP4", style="Compact.TButton",
                                      command=lambda: external(self.row), state="disabled")
        self.open_button.pack(side="right")
        self.time = tk.StringVar(value="")
        ttk.Label(buttons, textvariable=self.time, style="CardMuted.TLabel").pack(side="left", padx=7)
        self.player = None
        self.row = None
        self.timer = None
        self.paused = False
        self.height = 218
        self.position = 0.
        self.image = None
        self.still = None
        self.picture.bind("<Unmap>", lambda _: self.stop())
        self.recolor()

    def recolor(self):
        colors = tema.active
        self.picture.configure(bg=colors["media"], fg=colors["media_text"])

    def set_clip(self, row):
        if (row or {}).get("path") == (self.row or {}).get("path"):
            self.row = row
            return
        self.stop()
        self.row = row
        self.position = 0.
        self.still = None
        self.image = None
        self.time.set("")
        self.picture.configure(image="", text="Prévia do clipe" if row else "Selecione um clipe")
        self.play_button.configure(state="normal" if row else "disabled")
        self.open_button.configure(state="normal" if row else "disabled")

    def poster(self, photo):
        self.still = photo
        if not self.player:
            self.picture.configure(image=photo or "", text="" if photo else "Prévia do clipe")

    def set_height(self, height):
        if height == self.height:
            return
        self.height = height
        if self.player:
            self.player.set_size(-1, height)

    @staticmethod
    def clock(seconds):
        return f"{int(seconds) // 60}:{int(seconds) % 60:02}"

    def toggle(self):
        if not self.row:
            return
        if self.player:
            self.paused = not self.paused
            self.player.set_pause(self.paused)
            self.play_button.configure(text="Continuar" if self.paused else "Pausar")
            if not self.paused and self.timer is None:
                self.timer = self.frame.after(1, self.tick)
            return
        try:
            from ffpyplayer.player import MediaPlayer

            self.player = MediaPlayer(self.row["path"],
                                      ff_opts={"out_fmt": "rgb24", "x": -1, "y": self.height, "framedrop": True})
            self.paused = False
            self.play_button.configure(text="Pausar")
            self.timer = self.frame.after(12, self.tick)
        except (ImportError, OSError, RuntimeError, ValueError):
            self.stop()
            self.time.set("Abra o MP4 para assistir.")

    def tick(self):
        self.timer = None
        if not self.player or self.paused:
            return
        try:
            frame, wait = self.player.get_frame()
            if wait == "eof":
                self.stop()
                return
            if frame:
                image, at = frame
                width, height = image.get_size()
                pixels = image.to_bytearray()[0]
                ppm = f"P6\n{width} {height}\n255\n".encode("ascii") + bytes(pixels)
                self.image = tk.PhotoImage(data=ppm, format="PPM")
                self.picture.configure(image=self.image, text="")
                self.position = max(0., at)
                duration = self.player.get_metadata().get("duration")
                if duration and math.isfinite(duration):
                    label = f"{self.clock(self.position)} / {self.clock(duration)}"
                else:
                    label = self.clock(self.position)
                self.time.set(label)
            delay = min(180, max(8, round(wait * 1000))) if isinstance(wait, (int, float)) else 24
            self.timer = self.frame.after(delay, self.tick)
        except (RuntimeError, ValueError, OSError, tk.TclError):
            self.stop()
            self.time.set("Abra o MP4 para assistir.")

    def stop(self):
        if self.timer is not None:
            self.frame.after_cancel(self.timer)
            self.timer = None
        if self.player:
            player, self.player = self.player, None
            player.close_player()
        self.paused = False
        self.play_button.configure(text="Reproduzir")
        if self.row:
            self.picture.configure(image=self.still or "", text="" if self.still else "Prévia do clipe")
            self.image = None
