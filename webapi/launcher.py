from __future__ import annotations

import argparse
import os
import socket
import sys
import threading
import time
import webbrowser

import uvicorn


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000


def _configure_bundled_playwright() -> None:
    if not getattr(sys, "frozen", False) or not hasattr(sys, "_MEIPASS"):
        return

    browser_path = os.path.join(sys._MEIPASS, "playwright-browsers")
    if os.path.isdir(browser_path):
        os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", browser_path)


def _wait_for_server(host: str, port: int, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.2):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def run(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, open_browser: bool = True) -> None:
    _configure_bundled_playwright()
    from webapi.app import app

    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    startup_errors: list[BaseException] = []

    def serve() -> None:
        try:
            server.run()
        except BaseException as exc:
            startup_errors.append(exc)

    server_thread = threading.Thread(target=serve, daemon=True)
    server_thread.start()

    if not _wait_for_server(host, port):
        server.should_exit = True
        if startup_errors:
            raise RuntimeError("The local dashboard server failed to start.") from startup_errors[0]
        raise RuntimeError(f"The local dashboard did not start on {host}:{port}.")

    url = f"http://{host}:{port}"
    if open_browser:
        webbrowser.open(url)

    try:
        while server_thread.is_alive():
            server_thread.join(timeout=0.5)
    except KeyboardInterrupt:
        server.should_exit = True
        server_thread.join(timeout=5)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local FPL Draft Dashboard.")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", default=DEFAULT_PORT, type=int)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    run(host=args.host, port=args.port, open_browser=not args.no_browser)


if __name__ == "__main__":
    main()
