"""Application state and background jobs for the WebView2 interface."""

import ast
import codecs
import os
import queue
import re
import runpy
import shutil
import subprocess
import sys
import threading
from collections import deque
from dataclasses import asdict
from fnmatch import fnmatch
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

from gogdl_settings import DOWNLOAD_FIELDS, LOG_FIELDS, UPDATE_FIELDS, cli_options, language_codes, load_settings, save_settings, validate_settings

PROJECT = Path(__file__).resolve().parent
CLI = PROJECT / "gogrepoc.py"
SETTINGS = PROJECT / "gogdl-settings.json"
FIELD_GROUPS = {"Каталог": UPDATE_FIELDS, "Загрузка": DOWNLOAD_FIELDS, "Журнал": LOG_FIELDS}
FIELDS = (*UPDATE_FIELDS, *DOWNLOAD_FIELDS, *LOG_FIELDS)
GOG_PAGES = {"auth.gog.com", "login.gog.com", "embed.gog.com", "www.gog.com", "gog.com"}
RESUME_PROMPT = "(D)iscard incompatible manifest or (A)bort? (D/d/A/a): "


def callback_code(url):
    parsed = urlsplit(url)
    if parsed.scheme == "https" and parsed.netloc == "embed.gog.com" and parsed.path == "/on_login_success":
        return parse_qs(parsed.query).get("code", [None])[0]
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
            "status": self.status, "busy": bool(self.process or self.authenticating),
            "authenticating": self.authenticating,
            "signedIn": (PROJECT / "gog-token.dat").is_file(), "resume": self.resume,
            "free": self.free_space, "catalogStatus": self.catalog_status,
            "queueGeneration": self.queue_generation,
            "queue": [(game_id, self.title(self.catalog.get(game_id, {})) or slug)
                      for game_id, slug in self.pending.items() if self.allowed(game_id)],
            "log": "\n".join(self.logs),
        }

    def settings_info(self):
        return {"theme": self.settings["theme"], "savedLogin": bool(self.settings["saved_login"]),
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
        if self.process or self.authenticating:
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
        if self.process or self.authenticating:
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

    def exchange_code(self, code):
        self.status = "Получение токена GOG…"
        self.dirty = True

        def exchange():
            try:
                cli = runpy.run_path(str(CLI))
                cli["rootLogger"].handlers.clear()
                with cli["makeGOGSession"](True) as session:
                    success = cli["exchange_login_code"](session, code)
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
            elif kind == "auth":
                self.authenticating = False
                self.status = "Вход в GOG выполнен" if value else "Не удалось получить токен GOG"
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
