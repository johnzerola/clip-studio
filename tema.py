"""Visual styles shared by the native Windows panels."""
from tkinter import ttk

BG = "#ecf2f3"
PAPER = "#f9fcfc"
INK = "#182e36"
MUTED = "#49616b"
TEAL = "#006451"
DEEP = "#102c34"


def apply(root):
    root.configure(background=BG)
    root.option_add("*Font", ("Segoe UI", 10))
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(".", font=("Segoe UI", 10), background=BG, foreground=INK)
    style.configure("TFrame", background=BG)
    style.configure("Card.TFrame", background=PAPER)
    style.configure("Card.TLabel", background=PAPER, foreground=INK)
    style.configure("Heading.TLabel", background=PAPER, foreground=INK, font=("Segoe UI Semibold", 12))
    style.configure("Muted.TLabel", foreground=MUTED)
    style.configure("TButton", background="#dae7e9", bordercolor="#c8dbdd", padding=(10, 7))
    style.map("TButton", background=[("active", "#cde0df")], foreground=[("disabled", "#7a8b8f")])
    style.configure("Primary.TButton", background=TEAL, foreground="#ffffff", bordercolor=TEAL,
                    font=("Segoe UI Semibold", 10), padding=(13, 8))
    style.map("Primary.TButton", background=[("disabled", "#b4c8c6"), ("active", "#087863")],
              foreground=[("disabled", "#344f51"), ("active", "#ffffff")])
    style.configure("TNotebook", background=BG, bordercolor="#c8dbdd", tabmargins=(0, 3, 0, 0))
    style.configure("TNotebook.Tab", background="#dce9e9", foreground=MUTED, padding=(16, 7))
    style.map("TNotebook.Tab", background=[("selected", PAPER), ("active", "#cfe2df")],
              foreground=[("selected", TEAL)])
    style.configure("TEntry", fieldbackground="#ffffff", padding=4, bordercolor="#c8dbdd")
    style.configure("TCombobox", fieldbackground="#ffffff", padding=3, bordercolor="#c8dbdd")
    style.map("TCombobox", fieldbackground=[("readonly", "#ffffff")])
    style.configure("Treeview", background=PAPER, fieldbackground=PAPER, foreground=INK, rowheight=28)
    style.map("Treeview", background=[("selected", TEAL)], foreground=[("selected", "white")])
    style.configure("Treeview.Heading", background="#dce9e9", foreground=INK, padding=6)
