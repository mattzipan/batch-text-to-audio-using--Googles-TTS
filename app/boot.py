"""Local server boot helpers (spec task C2): free port, daemon thread, poll."""

from __future__ import annotations

import socket
import threading
import time
import urllib.request
from typing import Any


def find_free_port() -> int:
    """Bind ``127.0.0.1:0`` and return the OS-assigned free port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def start_server_thread(fastapi_app: Any, port: int) -> threading.Thread:
    """Serve ``fastapi_app`` on 127.0.0.1:``port`` in a daemon thread."""
    import uvicorn

    server = uvicorn.Server(
        uvicorn.Config(
            fastapi_app, host="127.0.0.1", port=port, workers=1, log_level="warning"
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    return thread


def wait_until_up(url: str, timeout: float = 10.0) -> bool:
    """Poll ``url`` until it answers HTTP 200; ``False`` on timeout."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.0) as response:
                if response.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.1)
    return False
