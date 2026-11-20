"""Mesa editorial colors and native Windows widgets."""
from tkinter import ttk

LIGHT = dict(bg="#f2f5ee", rail="#eff3eb", paper="#ffffff", ink="#1c2f27",
             muted="#51665b", line="#d9e4d9", border="#95aa9c", selected="#dff1e5",
             accent="#15734e", on_accent="#ffffff", focus="#166e54", ring="#1a9b66",
             media="#161e1d", media_text="#e7f1eb", good="#176840", good_bg="#ddf5e3",
             mid="#784c00", mid_bg="#ffefd2", low="#a22c35", low_bg="#fde8e7")
DARK = dict(bg="#121722", rail="#10141e", paper="#1b2332", ink="#edf3ff",
            muted="#a9bbd2", line="#303a4d", border="#657994", selected="#26344f",
            accent="#9bb7ff", on_accent="#111c36", focus="#9bb7ff", ring="#a6bfff",
            media="#0b101b", media_text="#eaf0ff", good="#79e9b8", good_bg="#123b32",
            mid="#ffd58e", mid_bg="#3f301a", low="#ff9ca4", low_bg="#492b38")
active = LIGHT
BG, PAPER, INK, MUTED, TEAL, DEEP = (LIGHT[key] for key in ("bg", "paper", "ink", "muted", "accent", "rail"))
MODES = ("Sistema", "Claro", "Escuro")


def system_dark():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
            return not bool(winreg.QueryValueEx(key, "AppsUseLightTheme")[0])
    except (ImportError, OSError):
        return False


def reduced_motion():
    try:
        import ctypes
        enabled = ctypes.c_int(1)
        success = ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(enabled), 0)
        return bool(success and not enabled.value)
    except (AttributeError, OSError):
        return True


def resolve(mode):
    return DARK if mode == "Escuro" or (mode == "Sistema" and system_dark()) else LIGHT


def score(value):
    key, label = ("good", "Forte") if value >= 80 else (
        ("mid", "Promissor") if value >= 65 else ("low", "Precisa de ajuste"))
    return label, active[key], active[key + "_bg"]


def apply(root, mode="Sistema"):
    global active, BG, PAPER, INK, MUTED, TEAL, DEEP
    active = c = resolve(mode)
    BG, PAPER, INK, MUTED, TEAL, DEEP = (c[key] for key in ("bg", "paper", "ink", "muted", "accent", "rail"))
    root.configure(background=BG)
    root.option_add("*Text.background", PAPER)
    root.option_add("*Text.foreground", INK)
    root.option_add("*Text.insertBackground", INK)
    root.option_add("*Font", ("Segoe UI", 10))
    root.option_add("*TCombobox*Listbox.background", PAPER)
    root.option_add("*TCombobox*Listbox.foreground", INK)
    root.option_add("*TCombobox*Listbox.selectBackground", c["selected"])
    style = ttk.Style(root)
    if style.theme_use() != "clam":
        style.theme_use("clam")
    style.configure(".", background=BG, foreground=INK, bordercolor=c["line"],
                    lightcolor=c["line"], darkcolor=c["line"], troughcolor=c["rail"],
                    selectbackground=c["selected"], selectforeground=INK,
                    focuscolor=c["focus"], font=("Segoe UI", 10))
    for name in ("Card", "Gallery"):
        style.configure(f"{name}.TFrame", background=PAPER, bordercolor=c["line"])
        style.configure(f"{name}.TLabel", background=PAPER, foreground=INK)
    style.configure("CardTransition.TFrame", background=c["selected"])
    style.configure("Nav.TFrame", background=c["rail"])
    style.configure("Brand.TLabel", background=c["rail"], foreground=INK)
    style.configure("Heading.TLabel", background=PAPER, foreground=INK)
    style.configure("Metric.TLabel", background=PAPER, foreground=INK)
    style.configure("Muted.TLabel", foreground=MUTED)
    style.configure("CardMuted.TLabel", background=PAPER, foreground=MUTED)
    style.configure("Live.TLabel", foreground=c["good"])
    style.configure("TButton", background=PAPER, foreground=INK, bordercolor=c["border"], padding=(10, 7))
    style.map("TButton", background=[("active", c["selected"])], foreground=[("disabled", MUTED)],
              bordercolor=[("focus", c["focus"])])
    for name in ("Nav.TButton", "NavActive.TButton", "TabChoice.TButton", "TabSelected.TButton"):
        selected = name in ("NavActive.TButton", "TabSelected.TButton")
        rest = c["selected"] if selected else c["rail"] if name.startswith("Nav") else BG
        style.configure(name, padding=(10, 7), anchor="w", background=rest,
                        bordercolor=c["border"] if selected else rest,
                        lightcolor=rest, darkcolor=rest)
        style.map(name, background=[("active", c["selected"])], bordercolor=[("focus", c["focus"])])
    style.configure("Compact.TButton", padding=(7, 4))
    style.configure("Primary.TButton", background=TEAL, foreground=c["on_accent"], bordercolor=TEAL,
                    lightcolor=TEAL, darkcolor=TEAL, padding=(12, 8))
    style.map("Primary.TButton", background=[("disabled", c["line"]), ("pressed", c["selected"]),
                                             ("active", TEAL)],
              foreground=[("disabled", MUTED), ("pressed", INK), ("active", c["on_accent"])],
              bordercolor=[("focus", c["focus"])])
    style.configure("TNotebook", background=BG, borderwidth=0, bordercolor=BG)
    style.configure("Workspace.TNotebook", background=BG, borderwidth=0, bordercolor=BG)
    style.configure("TNotebook.Tab", background=c["rail"], foreground=MUTED, padding=(12, 6))
    style.map("TNotebook.Tab", background=[("selected", PAPER), ("active", c["selected"])],
              foreground=[("selected", INK)])
    for name in ("TEntry", "TCombobox", "TSpinbox"):
        style.configure(name, fieldbackground=PAPER, foreground=INK, arrowcolor=INK,
                        insertcolor=INK, padding=4, bordercolor=c["border"])
        style.map(name, fieldbackground=[("readonly", PAPER), ("disabled", c["rail"])],
                  foreground=[("readonly", INK), ("disabled", MUTED)],
                  bordercolor=[("focus", c["focus"])])
    style.configure("Treeview", background=PAPER, fieldbackground=PAPER, foreground=INK, rowheight=31)
    style.map("Treeview", background=[("selected", c["selected"])], foreground=[("selected", INK)])
    style.configure("Treeview.Heading", background=c["rail"], foreground=INK, padding=7)
    style.map("Treeview.Heading", background=[("active", c["selected"])])
