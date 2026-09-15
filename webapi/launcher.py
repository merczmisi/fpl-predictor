from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
import webbrowser
from typing import Optional

import uvicorn


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000


def _configure_bundled_playwright() -> None:
    if not getattr(sys, "frozen", False) or not hasattr(sys, "_MEIPASS"):
        return

    executable_dir = os.path.dirname(os.path.abspath(sys.executable))
    contents_dir = os.path.dirname(executable_dir)
    candidates = [
        os.path.join(contents_dir, "Resources", "_internal", "playwright-browsers"),
        os.path.join(contents_dir, "Frameworks", "playwright-browsers"),
        os.path.join(sys._MEIPASS, "playwright-browsers"),
    ]
    for browser_path in candidates:
        if os.path.isdir(browser_path):
            os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", os.path.realpath(browser_path))
            break


def run_auth_worker() -> int:
    """Run async Playwright in the isolated authentication process."""
    _configure_bundled_playwright()
    import asyncio
    from fpl_draft.async_auth import AsyncBrowserAuth

    token = asyncio.run(
        AsyncBrowserAuth(headless=os.environ.get("FPL_HEADLESS", "1") != "0").ensure_authenticated()
    )
    print(token, flush=True)
    return 0


def run_auth_check_worker() -> int:
    """Run async Playwright in a non-interactive mode that only validates an existing profile token."""
    _configure_bundled_playwright()
    import asyncio
    from fpl_draft.async_auth import AsyncBrowserAuth

    token = asyncio.run(
        AsyncBrowserAuth(headless=os.environ.get("FPL_HEADLESS", "1") != "0").check_authenticated()
    )
    print(token or "", flush=True)
    return 0


# Only one auth worker may use the shared Chromium profile at a time.
_auth_worker_lock = threading.Lock()


def get_auth_token() -> str:
    if getattr(sys, "frozen", False):
        command = [sys.executable, "--auth-worker"]
    else:
        command = [sys.executable, "-m", "webapi.launcher", "--auth-worker"]

    with _auth_worker_lock:
        completed = subprocess.run(command, capture_output=True, text=True, check=False)

    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "FPL authentication worker failed."
        raise RuntimeError(detail)

    token = completed.stdout.strip().splitlines()[-1] if completed.stdout.strip() else ""
    if not token:
        raise RuntimeError("FPL authentication worker returned no token.")
    return token


def get_auth_status() -> Optional[str]:
    """Check for an existing valid FPL session without launching an interactive login.

    Returns the access token if the shared profile already holds a valid session,
    or None if the caller should prompt the user to connect via `get_auth_token()`.
    """
    if getattr(sys, "frozen", False):
        command = [sys.executable, "--auth-check"]
    else:
        command = [sys.executable, "-m", "webapi.launcher", "--auth-check"]

    with _auth_worker_lock:
        completed = subprocess.run(command, capture_output=True, text=True, check=False)

    if completed.returncode != 0:
        return None

    token = completed.stdout.strip().splitlines()[-1] if completed.stdout.strip() else ""
    return token or None


def _poll_health(host: str, port: int, timeout: float) -> dict | None:
    """Return the /health payload once reachable, or None if it never responds."""
    deadline = time.monotonic() + timeout
    url = f"http://{host}:{port}/health"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=0.5) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
            time.sleep(0.1)
        except (ValueError, json.JSONDecodeError):
            return {}
    return None


def run(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, open_browser: bool = True) -> None:
    _configure_bundled_playwright()
    instance_token = uuid.uuid4().hex
    os.environ["FPL_INSTANCE_TOKEN"] = instance_token
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

    health = _poll_health(host, port, timeout=10.0)
    if health is None:
        server.should_exit = True
        if startup_errors:
            raise RuntimeError("The local dashboard server failed to start.") from startup_errors[0]
        raise RuntimeError(f"The local dashboard did not start on {host}:{port}.")

    if health.get("instance") != instance_token:
        server.should_exit = True
        raise RuntimeError(
            f"Port {port} is already used by another running FPL Draft (or other) process. "
            "Quit any other FPL Draft windows/processes and try again."
        )

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
    parser.add_argument("--auth-worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--auth-check", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.auth_worker:
        raise SystemExit(run_auth_worker())
    if args.auth_check:
        raise SystemExit(run_auth_check_worker())
    run(host=args.host, port=args.port, open_browser=not args.no_browser)


if __name__ == "__main__":
    main()
