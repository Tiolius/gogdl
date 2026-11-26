"""Download and install the application's GitHub main snapshot."""

import io
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.request import urlopen
from zipfile import ZipFile

ARCHIVE_URL = "https://codeload.github.com/Tiolius/gogdl/zip/refs/heads/main"
MAX_SIZE = 32 * 1024 * 1024
ROOT_FILES = {
    "gogdl_backend.py", "gogdl_settings.py", "gogdl_updater.py", "gogdl_window.py",
    "gogrepoc.py", "Start-GOGDL.cmd", "Setup-GOGDL.cmd", "requirements.txt",
    "README.md", "LICENSE-gogrepoc.txt",
}
REQUIRED = ROOT_FILES | {"assets/index.html", "assets/app.css", "assets/app.js"}


def application_file(name):
    parts = name.split("/")
    return (name in ROOT_FILES or
            len(parts) == 2 and parts[0] == "assets" and
            Path(name).suffix in {".css", ".js", ".html", ".ttf", ".txt", ".json"} or
            len(parts) == 3 and parts[:2] == ["assets", "material"] and name.endswith(".svg"))


def read_archive(data):
    files = {}
    seen = set()
    total = 0
    with ZipFile(io.BytesIO(data)) as archive:
        for entry in archive.infolist():
            if entry.is_dir():
                continue
            _, _, name = entry.filename.partition("/")
            if not application_file(name):
                continue
            parts = name.split("/")
            if (any(not part or part in {".", ".."} or part.endswith((".", " ")) or
                    any(char in part for char in '\\:<>"|?*') for part in parts)
                    or stat.S_ISLNK(entry.external_attr >> 16)
                    or name.lower() in seen):
                raise ValueError("Invalid path in GitHub archive")
            seen.add(name.lower())
            total += entry.file_size
            if total > MAX_SIZE:
                raise ValueError("GitHub archive is too large")
            files[name] = archive.read(entry)
    if not REQUIRED <= files.keys():
        raise ValueError("The main branch does not yet contain a compatible app update")
    return files


def target_file(project, name):
    target = project / name
    if target.resolve() != target:
        raise ValueError("Application file redirects outside its expected path")
    return target


def download_update(project):
    with urlopen(ARCHIVE_URL, timeout=20) as response:
        data = response.read(MAX_SIZE + 1)
    if len(data) > MAX_SIZE:
        raise ValueError("GitHub archive is too large")
    files = read_archive(data)
    changed = {}
    for name, content in files.items():
        target = target_file(project, name)
        if not target.is_file() or target.read_bytes() != content:
            changed[name] = content
    return changed


def install_and_restart(project, files):
    """Apply the staged files after the application window has closed."""
    applied = []
    work = Path(tempfile.mkdtemp(prefix=".gogdl-update-", dir=project))
    keep_backup = False
    try:
        for index, data in enumerate(files.values()):
            (work / f"new-{index}").write_bytes(data)

        try:
            for index, name in enumerate(files):
                target = target_file(project, name)
                backup = work / f"old-{index}"
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists():
                    os.replace(target, backup)
                applied.append((target, backup))
                os.replace(work / f"new-{index}", target)
            restart(project)
        except (OSError, ValueError):
            for target, backup in reversed(applied):
                try:
                    if backup.exists():
                        os.replace(backup, target)
                    else:
                        target.unlink(missing_ok=True)
                except OSError:
                    keep_backup = True
            if keep_backup:
                raise OSError(f"Could not restore all application files. Backups: {work}")
            raise
    finally:
        if not keep_backup:
            shutil.rmtree(work, ignore_errors=True)


def restart(project):
    subprocess.Popen([sys.executable, str(project / "gogdl_window.py")], cwd=project)
