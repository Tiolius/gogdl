"""Options shared by the settings dialog and the command builders."""

import ast
import json
import math
import os
import tempfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    default: object = ""
    flag: str = ""
    choices: tuple = ()


UPDATE_FIELDS = (
    Field("update_os", "ОС", "windows", "-os"),
    Field("update_skipos", "Исключить ОС", flag="-skipos"),
    Field("update_lang", "Языки", "en ru", "-lang"),
    Field("update_skiplang", "Исключить языки", flag="-skiplang"),
    Field("update_mode", "Режим обновления", "Новые игры и обновления", choices=(
        ("Новые игры и обновления", "-standard"), ("Только новые игры", "-skipknown"),
        ("Только обновления", "-updateonly"), ("Весь каталог", "-full"),
    )),
    Field("update_resume", "Незавершённое обновление", "Продолжить при наличии", "-resumemode", choices=(
        ("Продолжить при наличии", "resume"), ("Начать заново", "noresume"),
        ("Только продолжить", "onlyresume"),
    )),
    Field("update_installers", "Тип установщиков", "Автономные", "-installers", choices=(
        ("Автономные", "standalone"), ("Автономные и Galaxy", "both"),
    )),
    Field("update_ids", "Обновить только эти ID или slug", flag="-ids"),
    Field("update_skipids", "Исключить ID или slug", flag="-skipids"),
    Field("update_wait", "Задержка перед проверкой, ч", flag="-wait"),
    Field("skiphidden", "Пропускать скрытые игры", False, "-skiphidden"),
    Field("nochangelogs", "Пропускать списки изменений", False, "-nochangelogs"),
    Field("md5xmls", "Сохранять файлы контрольных сумм MD5", False, "-md5xmls"),
    Field("strictverify", "Сохранять статус проверки только при совпадении MD5", False, "-strictverify"),
    Field("strictdupe", "При поиске дубликатов учитывать отсутствие MD5", False, "-strictdupe"),
    Field("lenientdownloadsupdate", "Мягкая проверка изменений установщиков", False, "-lenientdownloadsupdate"),
    Field("strictextrasupdate", "Строгая проверка изменений дополнительных материалов", False, "-strictextrasupdate"),
)

DOWNLOAD_FIELDS = (
    Field("destination", "Папка загрузки"),
    Field("download_os", "ОС", flag="-os"),
    Field("download_skipos", "Исключить ОС", flag="-skipos"),
    Field("download_lang", "Языки", flag="-lang"),
    Field("download_skiplang", "Исключить языки", flag="-skiplang"),
    Field("download_skipids", "Исключить ID или slug"),
    Field("download_skipfiles", "Исключить файлы или шаблоны через ;", flag="-skipfiles"),
    Field("download_wait", "Задержка перед каждой игрой, ч", flag="-wait"),
    Field("download_limit", "Лимит на игру, МиБ", flag="-downloadlimit"),
    Field("covers", "Скачивать обложки", True, "-covers"),
    Field("backgrounds", "Скачивать фоны", True, "-backgrounds"),
    Field("nocleanimages", "Удалять старые обложки и фоны вместо переноса в !orphaned", False, "-nocleanimages"),
    Field("skipextras", "Пропускать дополнительные материалы", False, "-skipextras"),
    Field("skipstandalone", "Пропускать автономные установщики", False, "-skipstandalone"),
    Field("skipgalaxy", "Пропускать установщики Galaxy", False, "-skipgalaxy"),
    Field("skipshared", "Пропускать общие установщики", False, "-skipshared"),
    Field("skippreallocation", "Не резервировать место под файлы заранее", False, "-skippreallocation"),
)

LOG_FIELDS = (
    Field("nolog", "Не записывать вывод в gogrepo.log", False, "-nolog"),
    Field("debug", "Показывать отладочные сообщения", False, "-debug"),
)


def load_settings(path, defaults_only=False):
    defaults = {field.key: field.default for field in (*UPDATE_FIELDS, *DOWNLOAD_FIELDS, *LOG_FIELDS)}
    defaults["destination"] = str(path.parent)
    defaults["theme"] = "light"
    defaults["saved_login"] = ""
    defaults["window_geometry"] = ""
    defaults["window_maximized"] = False
    if defaults_only:
        return defaults
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return defaults
    if not isinstance(saved, dict):
        raise ValueError("Некорректный формат настроек")
    for key, value in defaults.items():
        if type(saved.get(key)) is type(value):
            defaults[key] = saved[key]
    if defaults["theme"] not in ("light", "dark"):
        defaults["theme"] = "light"
    return defaults


def save_settings(path, settings):
    stream = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix="gogdl-settings-", suffix=".tmp", delete=False)
    temporary = Path(stream.name)
    try:
        with stream:
            json.dump(settings, stream, ensure_ascii=False, indent=2)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def cli_options(fields, settings):
    options = []
    for field in fields:
        value = settings[field.key]
        if field.choices:
            if field.flag:
                options.append(field.flag)
            options.append(dict(field.choices)[value])
        elif not field.flag:
            continue
        elif isinstance(value, bool):
            if value:
                options.append(field.flag)
        elif value:
            parts = ([part.strip() for part in value.split(";") if part.strip()]
                     if field.key == "download_skipfiles" else value.split())
            if parts:
                options.extend([field.flag, *parts])
    return options


@lru_cache(maxsize=1)
def language_codes(cli):
    # Read the supported codes from the local CLI without running it or opening its log.
    module = ast.parse(cli.read_bytes())
    return next(ast.literal_eval(node.value) for node in module.body if isinstance(node, ast.Assign)
                and any(isinstance(name, ast.Name) and name.id == "LANG_TABLE" for name in node.targets))


def validate_settings(settings, cli):
    languages = language_codes(cli)
    for prefix in ("update", "download"):
        for suffix, allowed in (("os", {"windows", "linux", "mac"}), ("lang", languages)):
            include = f"{prefix}_{suffix}"
            exclude = f"{prefix}_skip{suffix}"
            for key in (include, exclude):
                settings[key] = settings[key].lower()
                if invalid := set(settings[key].split()).difference(allowed):
                    raise ValueError("Неизвестные коды: " + ", ".join(sorted(invalid)))
            if settings[include] and settings[exclude]:
                raise ValueError("Для ОС и языков заполните либо список включения, либо список исключения.")
    if settings["update_ids"] and settings["update_skipids"]:
        raise ValueError("Для обновления заполните либо список выбранных игр, либо список исключений.")
    for key in ("update_wait", "download_wait", "download_limit"):
        if settings[key]:
            settings[key] = settings[key].replace(",", ".")
            try:
                number = float(settings[key])
            except ValueError:
                number = -1
            if not math.isfinite(number) or number < 0 or (key == "download_limit" and number == 0):
                raise ValueError("Задержка должна быть неотрицательной, а лимит — положительным числом.")
    for field in (*UPDATE_FIELDS, *DOWNLOAD_FIELDS):
        if field.choices and settings[field.key] not in dict(field.choices):
            raise ValueError(f"Выберите значение для поля «{field.label}».")
        if field.flag and isinstance(settings[field.key], str) and any(
            part.startswith("-") for part in settings[field.key].replace(";", " ").split()
        ):
            raise ValueError(f"Проверьте значение поля «{field.label}».")
