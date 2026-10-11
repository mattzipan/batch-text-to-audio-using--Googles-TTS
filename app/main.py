"""WordTape desktop entry point (spec task E1).

Boots the local FastAPI server in a daemon thread, then opens the native
pywebview window (falling back to the system browser when webview is
unavailable). Importing this module has no side effects.
"""

import argparse
import sys
import webbrowser

from app import boot, config, server


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

        webview.create_window(
            config.APP_NAME,
            url,
            width=1280,
            height=800,
            min_size=(1024, 700),
            resizable=True,
            js_api=Api(),
        )
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
