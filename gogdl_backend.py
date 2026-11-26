"""Application state and background jobs for the WebView2 interface."""

import ast
import codecs
import os
import queue
import re
import runpy
import secrets
import shutil
import subprocess
import sys
import threading
import time
from collections import deque
from dataclasses import asdict
from fnmatch import fnmatch
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

from gogdl_updater import download_update
from gogdl_settings import DOWNLOAD_FIELDS, LOG_FIELDS, UPDATE_FIELDS, cli_options, language_codes, load_settings, save_settings, validate_settings

APP_VERSION = "0.2.0"
APP_AUTHOR = "Evered"
APP_VERSION_DATE = "2026-11-26"
PROJECT = Path(__file__).resolve().parent
CLI = PROJECT / "gogrepoc.py"
SETTINGS = PROJECT / "gogdl-settings.json"
FIELD_GROUPS = {"Каталог": UPDATE_FIELDS, "Загрузка": DOWNLOAD_FIELDS, "Журнал": LOG_FIELDS}
FIELDS = (*UPDATE_FIELDS, *DOWNLOAD_FIELDS, *LOG_FIELDS)
RESUME_PROMPT = "(D)iscard incompatible manifest or (A)bort? (D/d/A/a): "


def callback_code(url, expected_state):
    try:
        parsed = urlsplit(url.strip())
    except ValueError:
        return None
    if parsed.scheme != "https" or parsed.netloc != "embed.gog.com" or parsed.path != "/on_login_success":
        return None
    params = parse_qs(parsed.query, keep_blank_values=True)
    codes = params.get("code", [])
    states = params.get("state", [])
    if len(codes) != 1 or not codes[0] or len(states) != 1:
        return None
    if secrets.compare_digest(states[0].encode(), expected_state.encode()):
        return codes[0]
    return None


def auth_url(state):
    cli = runpy.run_path(str(CLI))
    return cli["GOG_AUTH_URL"] + "?" + urlencode({
        "client_id": cli["GOG_CLIENT_ID"],
        "redirect_uri": cli["GOG_GALAXY_REDIRECT_URL"] + "?origin=client",
        "response_type": "code",
        "layout": "client2",
        "state": state,
    })


def browser_login(state, cancelled):
    try:
        from playwright.sync_api import Error, sync_playwright
    except ImportError:
        return None, "Для входа запустите Setup-GOGDL.cmd"

    code = None

    def on_request(request):
        nonlocal code
        if code is None and request.is_navigation_request():
            code = callback_code(request.url, state)

    try:
        with sync_playwright() as playwright:
            for channel in ("msedge", "chrome"):
                if cancelled.is_set():
                    return None, "Вход отменён"
                try:
                    browser = playwright.chromium.launch(channel=channel, headless=False, timeout=10000)
                    break
                except Error:
                    continue
            else:
                return None, "Не удалось открыть Edge или Chrome. Проверьте, установлен ли один из браузеров."

            try:
                context = browser.new_context()
                context.on("request", on_request)
                page = context.new_page()
                try:
                    page.goto(auth_url(state), wait_until="commit", timeout=15000)
                except Error:
                    if not context.pages:
                        return None, "Окно входа закрыто"
                    if not code:
                        return None, "Не удалось открыть страницу входа GOG"

                deadline = time.monotonic() + 600
                while not code and not cancelled.is_set() and time.monotonic() < deadline:
                    if not context.pages:
                        return None, "Окно входа закрыто"
                    try:
                        context.pages[0].wait_for_timeout(150)
                    except Error:
                        if not context.pages:
                            return None, "Окно входа закрыто"
                        raise
            finally:
                browser.close()
    except (Error, OSError):
        if not code:
            return None, "Не удалось завершить вход в браузере"

    if cancelled.is_set():
        return None, "Вход отменён"
    return (code, "") if code else (None, "Время ожидания входа истекло")


def format_size(size):
    for unit in ("Б", "КиБ", "МиБ", "ГиБ", "ТиБ"):
        if size < 1024 or unit == "ТиБ":
            value = f"{size:.2f}".rstrip("0").rstrip(".").replace(".", ",")
            return f"{value} {unit}"
        size /= 1024


def read_process(process, events):
    decoder = codecs.getincrementaldecoder("utf-8")("replace")
    pending = ""
    with process.stdout:
        while chunk := process.stdout.read1(8192):
            pending += decoder.decode(chunk)
            while "\n" in pending:
                line, pending = pending.split("\n", 1)
                match = re.search(r"\| GOGDL_UPDATE (\d+) (\S+)\s*$", line)
                events.put(("game", match.groups()) if match else ("log", line))
            if pending.endswith(RESUME_PROMPT):
                pending = ""
                events.put(("resume", True))
    if pending:
        events.put(("log", pending))
    events.put(("exit", process.wait()))


class Backend:
    def __init__(self):
        self.events = queue.Queue()
        self.status = "Готово к запуску"
        try:
            self.settings = load_settings(SETTINGS)
            validate_settings(self.settings, CLI)
        except (OSError, ValueError, StopIteration) as error:
            self.settings = load_settings(SETTINGS, defaults_only=True)
            self.status = f"Не удалось прочитать настройки: {error}"
        self.logs = deque(maxlen=400)
        self.catalog = {}
        self.catalog_status = "Чтение каталога…"
        self.pending = {}
        self.checked = {}
        self.process = None
        self.action = ""
        self.queue_generation = 0
        self.batch = deque()
        self.current = None
        self.stopped = False
        self.resume = False
        self.authenticating = False
        self.updating_app = False
        self.app_update_status = ""
        self.browser_cancel = None
        self.login_status = ""
        self.free_space = "…"
        self.disk_pending = False
        self.messages = []
        self.dirty = True

    def load_catalog(self):
        def read():
            try:
                games = ast.literal_eval((PROJECT / "gog-manifest.dat").read_text(encoding="utf-8-sig"))
                catalog = {str(game["id"]): game for game in games}
                catalog = dict(sorted(catalog.items(), key=lambda item: self.title(item[1]).casefold()))
                result = catalog, f"Игр в каталоге: {len(catalog)}"
            except FileNotFoundError:
                result = {}, "Сначала обновите каталог"
            except (OSError, SyntaxError, TypeError, ValueError, KeyError):
                result = {}, "Не удалось прочитать каталог"
            self.events.put(("catalog", result))

        threading.Thread(target=read, daemon=True).start()

    def refresh_disk(self):
        if self.disk_pending:
            return
        self.disk_pending = True
        destination = self.settings["destination"]

        def read():
            try:
                free = format_size(shutil.disk_usage(destination).free)
            except (OSError, ValueError):
                free = "недоступно"
            self.events.put(("disk", (destination, free)))

        threading.Thread(target=read, daemon=True).start()

    @staticmethod
    def title(game):
        return game.get("long_title") or game.get("title", "")

    def allowed(self, game_id):
        excluded = set(self.settings["download_skipids"].split())
        title = self.catalog.get(game_id, {}).get("title", self.pending.get(game_id))
        return game_id not in excluded and title not in excluded

    def estimate(self, game):
        settings = self.settings
        platforms = set(settings["download_os"].split()) or {"windows", "linux", "mac"}
        platforms.difference_update(settings["download_skipos"].split())
        codes = language_codes(CLI)
        allowed_codes = set(settings["download_lang"].split()) or set(codes)
        languages = {codes[code] for code in allowed_codes.difference(settings["download_skiplang"].split())}
        patterns = [part.strip() for part in settings["download_skipfiles"].split(";") if part.strip()]
        sizes = {}
        for group, flag in (("downloads", "skipstandalone"), ("galaxyDownloads", "skipgalaxy"),
                            ("sharedDownloads", "skipshared"), ("extras", "skipextras")):
            if settings[flag]:
                continue
            for entry in game.get(group, []):
                if group != "extras" and (entry.get("os_type") not in platforms or entry.get("lang") not in languages):
                    continue
                name, size = entry.get("name"), entry.get("size")
                if name and type(size) is int and size >= 0 and not any(fnmatch(name, pattern) for pattern in patterns):
                    sizes[name] = max(sizes.get(name, 0), size)
        return sum(sizes.values())

    def catalog_info(self):
        return [(game_id, self.title(game), game.get("title", ""), self.estimate(game))
                for game_id, game in self.catalog.items() if self.allowed(game_id)]

    def snapshot(self):
        return {
            "status": self.status, "busy": bool(self.process or self.authenticating or self.updating_app),
            "updatingApp": self.updating_app, "appUpdateStatus": self.app_update_status,
            "authenticating": self.authenticating, "awaitingLogin": bool(self.browser_cancel),
            "loginStatus": self.login_status,
            "signedIn": (PROJECT / "gog-token.dat").is_file(), "resume": self.resume,
            "free": self.free_space, "catalogStatus": self.catalog_status,
            "queueGeneration": self.queue_generation,
            "queue": [(game_id, self.title(self.catalog.get(game_id, {})) or slug)
                      for game_id, slug in self.pending.items() if self.allowed(game_id)],
            "log": "\n".join(self.logs),
        }

    def settings_info(self):
        return {"version": {"number": APP_VERSION, "author": APP_AUTHOR, "date": APP_VERSION_DATE},
                "theme": self.settings["theme"], "language": self.settings["language"],
                "savedLogin": bool(self.settings["saved_login"]),
                "groups": {name: [{**asdict(field), "value": self.settings[field.key]} for field in fields]
                           for name, fields in FIELD_GROUPS.items()}}

    def apply_settings(self, values):
        updated = self.settings.copy()
        for field in FIELDS:
            value = values.get(field.key, updated[field.key])
            if type(value) is not type(field.default):
                raise ValueError(f"Проверьте значение поля «{field.label}».")
            updated[field.key] = value.strip() if isinstance(value, str) else value
        if not Path(updated["destination"]).is_absolute():
            raise ValueError("Укажите полный путь к папке загрузки.")
        validate_settings(updated, CLI)
        self.save(**updated)
        self.refresh_disk()
        self.messages.append(("catalog", self.catalog_info()))

    def save(self, **changes):
        updated = {**self.settings, **changes}
        save_settings(SETTINGS, updated)
        self.settings = updated

    def start(self, args):
        if self.process or self.authenticating or self.updating_app:
            return False
        python = Path(sys.executable)
        if python.name.lower() == "pythonw.exe":
            python = python.with_name("python.exe")
        action = args[0]
        runtime_path = str(PROJECT / ".gogdl-runtime")
        if os.environ.get("PYTHONPATH"):
            runtime_path += os.pathsep + os.environ["PYTHONPATH"]
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONPATH=runtime_path)
        env["GOGDL_REPORT_UPDATES" if action == "update" else "GOGDL_STRICT_DOWNLOAD"] = "1"
        try:
            self.process = subprocess.Popen(
                [str(python), "-u", str(CLI), *args, *cli_options(LOG_FIELDS, self.settings)],
                cwd=PROJECT, env=env, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                stdin=subprocess.PIPE if action == "update" else subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            )
        except OSError as error:
            self.status = f"Ошибка запуска: {error}"
            self.logs.append(self.status)
            self.dirty = True
            return False
        self.action = action
        self.stopped = False
        self.status = "Проверка каталога…" if action == "update" else "Загрузка…"
        self.logs.append("> " + subprocess.list2cmdline([CLI.name, *args]))
        threading.Thread(target=read_process, args=(self.process, self.events), daemon=True).start()
        self.dirty = True
        return True

    def update(self):
        self.checked = {}
        self.start(["update", *cli_options(UPDATE_FIELDS, self.settings)])

    def download(self, ids, batch):
        if self.process or self.authenticating or self.updating_app:
            return
        chosen = [game_id for game_id in dict.fromkeys(ids) if self.allowed(game_id)
                  and game_id in (self.pending if batch else self.catalog)]
        if not chosen:
            return
        destination = Path(self.settings["destination"])
        if not destination.is_dir():
            raise ValueError("Выберите существующую папку загрузки в настройках.")
        self.download_args = ["download", str(destination), *cli_options(DOWNLOAD_FIELDS, self.settings)]
        if batch:
            self.batch = deque(chosen)
            self.next_download()
        else:
            self.start([*self.download_args, "-ids", chosen[0]])

    def next_download(self):
        self.current = self.batch.popleft() if self.batch else None
        if self.current and not self.start([*self.download_args, "-ids", self.current]):
            self.batch.clear()
            self.current = None

    def stop(self):
        if self.process and self.process.poll() is None:
            self.stopped = True
            self.process.terminate()

    def resume_answer(self, discard):
        if self.resume and self.process and self.process.stdin:
            self.resume = False
            self.stopped = not discard
            try:
                self.process.stdin.write(b"d\n" if discard else b"a\n")
                self.process.stdin.flush()
            except OSError:
                pass
            self.dirty = True

    def update_application(self):
        if self.process or self.authenticating or self.updating_app:
            return
        self.updating_app = True
        self.status = self.app_update_status = "Проверяем обновление GOGDL…"
        self.dirty = True

        def check():
            try:
                files = download_update(PROJECT)
            except Exception as error:
                self.events.put(("appUpdateError", str(error)))
            else:
                self.events.put(("appUpdate", files))

        threading.Thread(target=check, daemon=True).start()

    def begin_login(self):
        if self.process or self.authenticating or self.updating_app:
            return
        state = secrets.token_urlsafe(24)
        cancelled = self.browser_cancel = threading.Event()
        self.authenticating = True
        self.status = self.login_status = "Войдите в GOG в открывшемся браузере"
        self.dirty = True

        def sign_in():
            try:
                code, status = browser_login(state, cancelled)
            except Exception:
                # Browser errors can include a URL with an authorization code.
                code, status = None, "Не удалось завершить вход в браузере"
            self.events.put(("browserLogin", (cancelled, code, status)))

        threading.Thread(target=sign_in).start()

    def cancel_login(self):
        if self.browser_cancel:
            self.browser_cancel.set()
            self.status = self.login_status = "Закрываем окно входа…"
            self.dirty = True

    def exchange_code(self, code):
        self.status = self.login_status = "Получение токена GOG…"
        self.dirty = True

        def exchange():
            try:
                cli = runpy.run_path(str(CLI))
                cli["rootLogger"].handlers.clear()
                with cli["makeGOGSession"](True) as session:
                    success = cli["exchange_login_code"](session, code, PROJECT / "gog-token.dat")
            except Exception:
                # The endpoint URL in an exception can contain the authorization code.
                success = False
            self.events.put(("auth", success))

        threading.Thread(target=exchange, daemon=True).start()

    def poll(self):
        for _ in range(120):
            try:
                kind, value = self.events.get_nowait()
            except queue.Empty:
                break
            self.dirty = True
            if kind == "log":
                self.logs.append(value)
            elif kind == "game":
                self.checked[value[0]] = value[1]
            elif kind == "catalog":
                self.catalog, self.catalog_status = value
                self.messages.append(("catalog", self.catalog_info()))
            elif kind == "disk":
                self.disk_pending = False
                if value[0] == self.settings["destination"]:
                    self.free_space = value[1]
                else:
                    self.refresh_disk()
            elif kind == "resume":
                self.resume = True
            elif kind == "appUpdateError":
                self.updating_app = False
                self.status = self.app_update_status = f"Не удалось обновить GOGDL: {value}"
            elif kind == "appUpdate":
                if value:
                    self.status = self.app_update_status = "Перезапускаем GOGDL…"
                    self.messages.append(("restartWithUpdate", value))
                else:
                    self.updating_app = False
                    self.status = self.app_update_status = "Установлена актуальная версия GOGDL"
            elif kind == "browserLogin":
                cancelled, code, status = value
                self.browser_cancel = None
                if code and not cancelled.is_set():
                    self.messages.append(("focusAfterLogin", None))
                    self.exchange_code(code)
                else:
                    self.authenticating = False
                    self.status = self.login_status = "Вход отменён" if cancelled.is_set() else status
            elif kind == "auth":
                self.authenticating = False
                self.status = self.login_status = "Вход в GOG выполнен" if value else "Не удалось получить токен GOG"
                self.logs.append(self.status)
            elif kind == "exit":
                success = value == 0 and not self.stopped
                self.status = "Остановлено" if self.stopped else f"Процесс завершён · код {value}"
                self.logs.append(self.status)
                if self.process.stdin:
                    try:
                        self.process.stdin.close()
                    except OSError:
                        pass
                self.process = None
                self.resume = False
                if self.action == "update" and success:
                    self.pending = self.checked
                    self.queue_generation += 1
                    self.load_catalog()
                elif self.current:
                    if success:
                        self.pending.pop(self.current, None)
                        self.next_download()
                    else:
                        self.batch.clear()
                        self.current = None
