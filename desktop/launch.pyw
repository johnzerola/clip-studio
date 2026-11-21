"""Run the installed Hook Spark panel in its own Edge app window."""
import ctypes
from ctypes import wintypes
import msvcrt
import os
from pathlib import Path
import secrets
import subprocess
import time
import urllib.request
import winreg

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ["LOCALAPPDATA"]) / "Codex Video"
ORIGIN = "http://127.0.0.1:45839"
NO_WINDOW = subprocess.CREATE_NO_WINDOW
PANEL_PID = DATA / "panel.pid"


def edge_path():
    for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles")):
        if base:
            edge = Path(base) / "Microsoft/Edge/Application/msedge.exe"
            if edge.is_file():
                return edge
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe") as key:
            executable = Path(winreg.QueryValue(key, None))
            if executable.is_file():
                return executable
    except OSError:
        pass
    raise RuntimeError("Microsoft Edge não está instalado. Instale o navegador para abrir o painel do Codex.")


def start():
    DATA.mkdir(parents=True, exist_ok=True)
    edge = [str(edge_path()), "--user-data-dir=" + str(DATA / "Panel"), "--no-first-run", "--disable-background-mode"]
    with (DATA / "launch.lock").open("a+b") as lock:
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            focus_panel()
            return
        PANEL_PID.unlink(missing_ok=True)
        with (DATA / "desktop.log").open("wb") as log:
            serve(edge, log)


def serve(edge, log):
    token, code = secrets.token_urlsafe(38), secrets.token_urlsafe(38)
    restart = ROOT / "work/desktop-restart.local"
    restart.unlink(missing_ok=True)
    env = {**os.environ, "CORTEX_SESSION": token, "CORTEX_LAUNCH_CODE": code}
    server = subprocess.Popen([str(ROOT / "desktop/runtime/node.exe"), str(ROOT / "desktop/server.mjs")],
                              cwd=ROOT, env=env, stdin=subprocess.PIPE, stdout=log, stderr=log,
                              creationflags=NO_WINDOW)
    try:
        client = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        probe = urllib.request.Request(ORIGIN + "/_desktop/ready", headers={"X-Cortex-Session": token})
        until = time.monotonic() + 25
        while server.poll() is None and time.monotonic() < until:
            try:
                with client.open(probe, timeout=1) as response:
                    if response.read(16) == b"ready":
                        break
            except OSError:
                time.sleep(0.25)
        else:
            raise RuntimeError("O painel local não iniciou. Registro em " + str(log.name))
        browser = subprocess.Popen([*edge, "--app=" + ORIGIN + "/_desktop/session?code=" + code], creationflags=NO_WINDOW)
        PANEL_PID.write_text(str(browser.pid), encoding="ascii")
        while browser.poll() is None and server.poll() is None:
            if restart.is_file():
                break
            time.sleep(0.5)
        if browser.poll() is None and restart.is_file():
            visit_windows(browser.pid, lambda window: ctypes.windll.user32.PostMessageW(window, 0x0010, 0, 0))
        if server.poll() is not None:
            raise RuntimeError("O serviço do painel foi encerrado. Registro em " + str(log.name))
    finally:
        PANEL_PID.unlink(missing_ok=True)
        server.stdin.close()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.terminate()


def focus_panel():
    user32 = ctypes.windll.user32

    def focus(window):
        user32.ShowWindowAsync(window, 9)  # SW_RESTORE
        user32.SetForegroundWindow(window)

    for _ in range(30):
        try:
            pid = int(PANEL_PID.read_text(encoding="ascii"))
            if visit_windows(pid, focus):
                return
        except (OSError, ValueError):
            pass
        time.sleep(0.15)


def visit_windows(pid, action):
    user32 = ctypes.windll.user32
    callback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    found = False

    @callback
    def visit(window, _):
        nonlocal found
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(window, ctypes.byref(owner))
        if owner.value == pid and user32.IsWindowVisible(window):
            action(window)
            found = True
        return True

    user32.EnumWindows(visit, 0)
    return found


if __name__ == "__main__":
    try:
        start()
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        ctypes.windll.user32.MessageBoxW(None, str(error), "Codex · Edição de vídeo", 0x10)
