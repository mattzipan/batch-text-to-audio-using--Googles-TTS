"""WordTape desktop entry point (spec task E1).

Boots the local FastAPI server in a daemon thread, then opens the native
pywebview window (falling back to the system browser when webview is
unavailable). Importing this module has no side effects.
"""

import argparse
import json
import sys
import webbrowser

from app import boot, config, server


def _setup_native_drop(window) -> None:
    """Bridge native file drops to the loaded page (packaged-app fix).

    WebKitGTK (the packaged Linux backend) does not populate
    ``dataTransfer.files`` for plain JS listeners, and pywebview only collects
    the dropped filesystem paths when a DOM ``drop`` handler is registered
    from Python — that registration arms pywebview's GTK drag-data hook, which
    injects ``pywebviewFullPath`` into each file of the event. We forward the
    first path to the page (``window.__wordtapeNativeDrop``), which imports it
    via the local server's ``/api/project/import`` path mode. Registered on
    the document so drops anywhere in the window work; ``dragover`` is
    prevent-defaulted so WebKitGTK allows the drop at all. Browser fallback
    mode keeps the plain HTML5 handlers in ``app.js`` and never calls this.
    """
    from webview.dom import DOMEventHandler

    def forward_drop(event: dict) -> None:
        try:
            files = (event.get("dataTransfer") or {}).get("files") or []
        except AttributeError:
            return
        path = None
        for file in files:
            if not isinstance(file, dict):
                continue
            if file.get("pywebviewFullPath"):
                path = str(file["pywebviewFullPath"])
                break
            name = str(file.get("name") or "")
            if path is None and name.startswith("file://"):
                path = name[len("file://") :]
        if not path:
            return
        try:
            window.evaluate_js(
                "window.__wordtapeNativeDrop && window.__wordtapeNativeDrop("
                + json.dumps(path)
                + ")"
            )
        except Exception:  # noqa: BLE001 - drop bridge must never crash the app
            pass

    def register() -> None:
        document = window.dom.document
        document.on(
            "dragover",
            DOMEventHandler(lambda event: None, prevent_default=True),
        )
        document.on("drop", DOMEventHandler(forward_drop, prevent_default=True))

    window.events.loaded += register


def main(argv=None) -> None:
    """Parse args, start the server thread, then show the window (or not)."""
    parser = argparse.ArgumentParser(prog="WordTape")
    parser.add_argument(
        "--server-only",
        action="store_true",
        help="run the local server without opening a window",
    )
    args = parser.parse_args(argv)

    try:
        config.apply_api_key_to_env()
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)

    port = boot.find_free_port()
    fastapi_app = server.create_app()
    thread = boot.start_server_thread(fastapi_app, port)
    url = f"http://127.0.0.1:{port}"
    if not boot.wait_until_up(url):
        print(f"Error: server did not start at {url}", file=sys.stderr)
        sys.exit(1)

    if args.server_only:
        print(f"WordTape server at {url}", flush=True)
        thread.join()
        return

    if getattr(sys, "frozen", False) is True:
        try:
            for candidate in (
                "/usr/lib/python3/dist-packages",
                "/usr/lib/python3.12/site-packages",
                "/usr/local/lib/python3.12/dist-packages",
            ):
                import os

                if os.path.isdir(candidate) and candidate not in sys.path:
                    sys.path.append(candidate)
        except Exception:
            pass

    try:
        import webview

        class Api:
            """JS bridge: file dialogs returning plain JSON-safe values."""

            def pick_folder(self):
                try:
                    result = webview.windows[0].create_file_dialog(
                        webview.FOLDER_DIALOG
                    )
                except Exception:
                    return None
                if result is None:
                    return None
                if isinstance(result, (list, tuple)):
                    return list(result)
                return str(result)

            def pick_file(self, extensions=None):
                try:
                    if extensions:
                        if isinstance(extensions, str):
                            exts = [extensions]
                        else:
                            exts = list(extensions)
                        patterns = ";".join(
                            f"*.{str(e).lstrip('*.')}" for e in exts
                        )
                        file_types = (
                            f"Supported files ({patterns})",
                            "All files (*.*)",
                        )
                    else:
                        file_types = ("All files (*.*)",)
                    result = webview.windows[0].create_file_dialog(
                        webview.OPEN_DIALOG,
                        allow_multiple=False,
                        file_types=file_types,
                    )
                except Exception:
                    return None
                if result is None:
                    return None
                if isinstance(result, (list, tuple)):
                    items = list(result)
                    if len(items) == 0:
                        return None
                    if len(items) == 1:
                        return str(items[0])
                    return [str(item) for item in items]
                return str(result)

        window = webview.create_window(
            config.APP_NAME,
            url,
            width=1280,
            height=800,
            min_size=(640, 400),
            resizable=True,
            js_api=Api(),
        )
        _setup_native_drop(window)
        webview.start(
            private_mode=False,
            storage_path=str(config.app_root() / ".webview"),
        )
    except Exception as err:
        print(
            f"Webview unavailable ({err}), falling back to browser. "
            f"Open {url} manually if needed.",
            flush=True,
        )
        try:
            webbrowser.open(url)
        except Exception:
            pass
        thread.join()


if __name__ == "__main__":
    import multiprocessing

    multiprocessing.freeze_support()
    main()
