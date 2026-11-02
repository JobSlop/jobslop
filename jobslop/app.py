"""Starting jobslop: the local server, the window, the phone server."""

import os
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from http.server import ThreadingHTTPServer

from jobslop.config import APP_PORT, DATA_DIR, RES_DIR
from jobslop.extension import install_extension, pairing_code
from jobslop.runtime import state
from jobslop.server.handler import Handler
from jobslop.server.phone import phone_settings, start_phone_server
from jobslop.updates import after_update_cleanup


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main():
    after_update_cleanup()
    install_extension()
    pairing_code()
    arg_port = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--port=")), None)
    port = int(arg_port or os.environ.get("JOBFINDER_PORT") or APP_PORT)
    try:
        server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    except OSError:
        # Port taken: most likely jobslop is already open, so just show another window onto it
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=3) as r:
                page = r.read(3000)
                already = b"jobslop" in page or b"Job Finder" in page   # older versions were called Job Finder
        except Exception:
            already = False
        if not already:
            port = free_port()   # something else has the port; the extension won't connect this time
            server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        else:
            server = None
    state["port"] = port
    if server:
        threading.Thread(target=server.serve_forever, daemon=True).start()
        if phone_settings().get("enabled") and "--no-phone" not in sys.argv:
            start_phone_server()                       # phone access was left switched on
    url = f"http://127.0.0.1:{port}"

    if "--browser" not in sys.argv:
        try:
            import webview  # pywebview: gives the app its own window
            webview.create_window("jobslop", url, width=1200, height=850, min_size=(420, 500))
            icon = RES_DIR / "jf.ico"            # same jF icon as the .exe file
            webview.start(private_mode=False, storage_path=str(DATA_DIR / "window"),
                          icon=str(icon) if icon.exists() else None)
            return
        except Exception as e:
            print("Couldn't open app window, using browser instead:", e)

    print(f"jobslop is running at {url}\nKeep this window open. Press Ctrl+C to stop.")
    if "--no-open" not in sys.argv:
        webbrowser.open(url)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
