from __future__ import annotations

import argparse
import socket
import threading
import time
import webbrowser

import uvicorn


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000


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
    config = uvicorn.Config("webapi.app:app", host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()

    if not _wait_for_server(host, port):
        server.should_exit = True
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
