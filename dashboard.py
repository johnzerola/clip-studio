"""Native dashboard for monitoring and editorial performance."""
import sqlite3
import tkinter as tk
from tkinter import ttk
from urllib.parse import urlsplit

from job_registry import active_sources
from workspace_data import overview


class Dashboard:
    def __init__(self, frame, output, sources, clips, posting):
        self.frame, self.output = frame, output
        tools = ttk.Frame(frame)
        tools.pack(fill="x")
        ttk.Label(tools, text="Visão geral", style="Page.TLabel", font=("Segoe UI Semibold", 22)).pack(side="left")
        ttk.Button(tools, text="Ver clipes", command=clips).pack(side="right")
        ttk.Button(tools, text="Adicionar links", command=sources, style="Primary.TButton").pack(side="right", padx=8)
        cards = ttk.Frame(frame)
        cards.pack(fill="x", pady=(14, 16))
        self.values = []
        for index, title in enumerate(("Clipes gerados", "Para revisar", "Agendados", "Publicados")):
            cards.columnconfigure(index, weight=1, uniform="metric")
            card = ttk.Frame(cards, padding=(12, 8), style="Card.TFrame")
            card.grid(row=0, column=index, sticky="nsew", padx=(0, 8))
            value = tk.StringVar(value="0")
            self.values.append(value)
            ttk.Label(card, textvariable=value, style="Metric.TLabel", font=("Segoe UI Semibold", 22)).pack(anchor="w")
            ttk.Label(card, text=title, style="Card.TLabel").pack(anchor="w")
        ttk.Label(frame, text="Canais monitorados", style="Section.TLabel", font=("Segoe UI Semibold", 13)).pack(anchor="w")
        self.channels = ttk.Frame(frame)
        self.channels.pack(fill="x", pady=(5, 14))
        top = ttk.Frame(frame)
        top.pack(fill="x")
        ttk.Label(top, text="Desempenho registrado", style="Section.TLabel", font=("Segoe UI Semibold", 13)).pack(side="left")
        ttk.Button(top, text="Registrar métricas…", command=posting).pack(side="right")
        self.performance = ttk.Frame(frame)
        self.performance.pack(fill="x", pady=(5, 0))
        self.snapshot = None
        self.frame.after_idle(self.tick)

    def tick(self):
        self.refresh()
        self.frame.after(4000, self.tick)

    def refresh(self):
        if self.frame.winfo_ismapped():
            try:
                folder = self.output()
                numbers, ratings = overview(folder)
                active = active_sources(folder)
                view = numbers, ratings, active
                if self.snapshot != view:
                    self.snapshot = view
                    for value, number in zip(self.values, numbers):
                        value.set(str(number))
                    self.fill_activity(active)
                    self.fill_performance(ratings)
            except (OSError, ValueError, RuntimeError, sqlite3.Error) as error:
                self.snapshot = None
                self.clear(self.channels)
                ttk.Label(self.channels, text=str(error), style="Muted.TLabel").pack(anchor="w")

    @staticmethod
    def clear(frame):
        for widget in frame.winfo_children():
            widget.destroy()

    def fill_activity(self, active):
        self.clear(self.channels)
        if not active:
            ttk.Label(self.channels, text="Cole um canal em Lives e gravações e inicie a captura.",
                      style="Muted.TLabel").pack(anchor="w")
        for url, state in active:
            parts = urlsplit(url)
            channel = parts.path.strip("/") or parts.hostname or "Canal"
            ttk.Label(self.channels, text=f"●  {channel}   ·   {state}",
                      style="Live.TLabel" if state.startswith("Ao vivo") else "Muted.TLabel").pack(anchor="w")

    def fill_performance(self, ratings):
        self.clear(self.performance)
        if not ratings:
            ttk.Label(self.performance, text="Registre visualizações e retenção após publicar um clipe.",
                      style="Muted.TLabel").pack(anchor="w")
        for title, topic, platform, views, retention in ratings:
            ttk.Label(self.performance, text=f"{title[:44]}  ·  {topic}  ·  {platform}  ·  {views} visualizações  ·  {retention:g}% retidos").pack(anchor="w")
