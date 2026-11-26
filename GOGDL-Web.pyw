"""Entry point for the WebView2 version of GOGDL."""

import ctypes

from gogdl_window import run


if __name__ == "__main__":
    try:
        run()
    except Exception as error:
        ctypes.windll.user32.MessageBoxW(
            None, f"Не удалось запустить WebView2.\n\n{error}", "GOGDL", 0x10,
        )
