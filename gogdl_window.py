"""Windows host for the local TypeScript UI with sign-in in an external browser."""

import base64
import ctypes
import json
import os
import queue
import re
import subprocess
import sys
from ctypes import wintypes
from pathlib import Path

from gogdl_backend import Backend, PROJECT
from gogdl_updater import install_and_restart, restart

HOME = "https://gogdl.local/index.html"


def installed_chrome():
    import winreg

    app_path = r"Software\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe"
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            try:
                with winreg.OpenKey(hive, app_path, 0, winreg.KEY_READ | view) as key:
                    value, _ = winreg.QueryValueEx(key, None)
            except OSError:
                continue
            if isinstance(value, str):
                path = Path(os.path.expandvars(value.strip('"')))
                if path.is_absolute() and path.is_file():
                    return path

    for folder in ("LOCALAPPDATA", "ProgramFiles", "ProgramFiles(x86)", "ProgramW6432"):
        if root := os.environ.get(folder):
            path = Path(root) / "Google" / "Chrome" / "Application" / "chrome.exe"
            if path.is_absolute() and path.is_file():
                return path
    return None


def open_login_browser(url):
    chrome = installed_chrome()
    if chrome:
        try:
            subprocess.Popen([str(chrome), url])
        except OSError:
            pass
        else:
            return
    os.startfile(url)


def browser_callback_windows():
    """Find ordinary Chromium and Firefox windows showing the GOG return page."""
    win = ctypes.WinDLL("user32")
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    win.EnumWindows.argtypes = (callback_type, wintypes.LPARAM)
    win.IsWindowVisible.argtypes = (wintypes.HWND,)
    win.GetClassNameW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
    win.GetWindowTextW.argtypes = win.GetClassNameW.argtypes
    windows = []

    @callback_type
    def inspect_window(handle, _):
        if not win.IsWindowVisible(handle):
            return True
        name = ctypes.create_unicode_buffer(64)
        win.GetClassNameW(handle, name, len(name))
        if name.value not in {"Chrome_WidgetWin_1", "MozillaWindowClass"}:
            return True
        title = ctypes.create_unicode_buffer(64)
        win.GetWindowTextW(handle, title, len(title))
        if re.match(r"^(?:https://)?embed[.]gog[.]com(?:[/\s]|$)", title.value, re.IGNORECASE):
            windows.append(handle)
        return True

    win.EnumWindows(inspect_window, 0)
    return windows


# Windows PowerShell loads the Windows UI Automation assemblies in .NET Framework.
# Read only browser chrome. Documents can contain passwords or other form inputs.
READ_BROWSER_ADDRESS = r"""
$ErrorActionPreference = 'Stop'
try {
    Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
    $walker = [System.Windows.Automation.TreeWalker]::ControlViewWalker
} catch {
    exit 21
}

foreach ($window in $windows) {
    try {
        $root = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr][long]$window)
        if ($null -eq $root) { continue }
        $stack = [System.Collections.Stack]::new()
        $stack.Push($walker.GetFirstChild($root))
        $visited = 0
        while ($stack.Count -and $visited -lt 256) {
            $element = $stack.Pop()
            if ($null -eq $element) { continue }
            $visited++
            $stack.Push($walker.GetNextSibling($element))
            $control = $element.Current.ControlType
            if ($control -eq [System.Windows.Automation.ControlType]::Document) { continue }
            if ($control -eq [System.Windows.Automation.ControlType]::Edit) {
                $pattern = $null
                if ($element.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern, [ref]$pattern)) {
                    $address = $pattern.Current.Value
                    if ($address -cmatch '^(?:https://)?embed[.]gog[.]com/on_login_success[?]') {
                        [Console]::WriteLine($address)
                    }
                }
            }
            $stack.Push($walker.GetFirstChild($element))
        }
    } catch [System.Windows.Automation.ElementNotAvailableException] {
        continue
    } catch [System.ArgumentException] {
        continue
    } catch {
        exit 22
    }
}
"""


def browser_callback_urls():
    windows = browser_callback_windows()
    if not windows:
        return
    script = "$windows = @(" + ",".join(str(int(handle)) for handle in windows) + ")\n" + READ_BROWSER_ADDRESS
    command = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    powershell = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    try:
        result = subprocess.run(
            [str(powershell), "-NoLogo", "-NoProfile", "-NonInteractive", "-EncodedCommand", command],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW, timeout=8,
        )
    except subprocess.TimeoutExpired:
        return
    except OSError:
        raise RuntimeError("UIA-20") from None
    if result.returncode:
        raise RuntimeError({21: "UIA-21", 22: "UIA-22"}.get(result.returncode, "UIA-23"))
    for address in result.stdout.decode("ascii", errors="ignore").splitlines():
        if address.startswith("https://embed.gog.com/on_login_success?"):
            yield address
        elif address.startswith("embed.gog.com/on_login_success?"):
            yield "https://" + address


def run():
    runtime = PROJECT / ".gogdl-runtime"
    sys.path.insert(0, str(runtime))
    import clr

    clr.AddReference("System.Windows.Forms")
    clr.AddReference("System.Drawing")
    clr.AddReference("System.Threading")
    lib = runtime / "webview" / "lib"
    clr.AddReference(str(lib / "Microsoft.Web.WebView2.Core.dll"))
    clr.AddReference(str(lib / "Microsoft.Web.WebView2.WinForms.dll"))

    from Microsoft.Web.WebView2.Core import CoreWebView2HostResourceAccessKind
    from Microsoft.Web.WebView2.WinForms import CoreWebView2CreationProperties, WebView2
    from System.Drawing import Color, Point, Size
    from System.Threading import ApartmentState, Thread, ThreadStart
    from System.Windows.Forms import (
        Application, DialogResult, DockStyle, FolderBrowserDialog, Form,
        FormStartPosition, FormWindowState, MessageBox, MessageBoxButtons, Timer,
    )

    failures = queue.Queue()
    pending_update = None
    language = "en"

    def window_loop():
        try:
            show_window()
        except Exception as error:
            failures.put(error)

    def show_window():
        nonlocal pending_update, language
        Application.EnableVisualStyles()
        backend = Backend()
        language = backend.settings["language"]

        def label(english, russian):
            return russian if language == "ru" else english
        form = Form()
        form.Text = "GOGDL"
        form.MinimumSize = Size(600, 475)
        form.Size = Size(920, 690)
        form.StartPosition = FormStartPosition.CenterScreen
        geometry = re.fullmatch(r"(\d+)x(\d+)\+(-?\d+)\+(-?\d+)", backend.settings["window_geometry"])
        if geometry:
            width, height, x, y = map(int, geometry.groups())
            form.StartPosition = FormStartPosition.Manual
            form.Size = Size(max(600, width), max(475, height))
            form.Location = Point(x, y)
        if backend.settings["window_maximized"]:
            form.WindowState = FormWindowState.Maximized

        view = WebView2()
        view.Dock = DockStyle.Fill
        view.DefaultBackgroundColor = Color.FromArgb(27, 26, 34) if backend.settings["theme"] == "dark" else Color.FromArgb(253, 253, 253)
        properties = CoreWebView2CreationProperties()
        properties.UserDataFolder = str(PROJECT / ".gogdl-profile")
        view.CreationProperties = properties
        form.Controls.Add(view)

        ready = False
        disk_ticks = 0

        def push(kind, data):
            if ready and str(view.Source) == HOME:
                view.CoreWebView2.PostWebMessageAsString(json.dumps({"kind": kind, "data": data}, ensure_ascii=False))

        def message(_sender, args):
            nonlocal ready, language
            # Only the bundled document can invoke host commands.
            if str(args.Source) != HOME or str(view.Source) != HOME:
                return
            try:
                item = json.loads(args.TryGetWebMessageAsString())
                if not isinstance(item, dict):
                    return
                action, value = item.get("action"), item.get("value")
                if action == "ready":
                    ready = True
                    push("settings", backend.settings_info())
                    push("catalog", backend.catalog_info())
                    push("state", backend.snapshot())
                elif action == "update":
                    backend.update()
                elif action in {"queue", "download"} and isinstance(value, list) and all(
                    isinstance(entry, str) for entry in value
                ):
                    backend.download(value, batch=action == "queue")
                elif action == "stop":
                    backend.stop()
                elif action == "resume" and isinstance(value, bool):
                    backend.resume_answer(value)
                elif action == "settings" and isinstance(value, dict):
                    backend.apply_settings(value)
                    push("settingsSaved", backend.settings_info())
                elif action == "language" and value in ("en", "ru"):
                    backend.save(language=value)
                    language = value
                    push("settings", backend.settings_info())
                elif action == "updateApplication":
                    backend.update_application()
                elif action == "theme":
                    backend.save(theme="light" if backend.settings["theme"] == "dark" else "dark")
                    view.DefaultBackgroundColor = (Color.FromArgb(27, 26, 34)
                                                   if backend.settings["theme"] == "dark" else Color.FromArgb(253, 253, 253))
                    push("settings", backend.settings_info())
                elif action == "forgetLogin":
                    backend.save(saved_login="")
                    push("settings", backend.settings_info())
                elif action == "browse":
                    picker = FolderBrowserDialog()
                    try:
                        picker.SelectedPath = backend.settings["destination"]
                        if picker.ShowDialog(form) == DialogResult.OK:
                            push("destination", picker.SelectedPath)
                    finally:
                        picker.Dispose()
                elif action == "openFolder":
                    os.startfile(PROJECT)
                elif action == "login":
                    backend.begin_login(open_login_browser, browser_callback_urls)
                elif action == "saveToken" and isinstance(value, str):
                    backend.save_manual_token(value)
                elif action == "cancelLogin":
                    backend.cancel_login()
            except (OSError, ValueError, TypeError) as error:
                push("error", str(error))

        def block_popup(_sender, args):
            args.Handled = True

        def local_navigate(_sender, args):
            if str(args.Uri) != HOME:
                args.Cancel = True

        def initialized(_sender, args):
            if not args.IsSuccess:
                MessageBox.Show(label("Could not start Microsoft Edge WebView2.", "Не удалось запустить Microsoft Edge WebView2."), "GOGDL")
                form.Close()
                return
            core = view.CoreWebView2
            core.SetVirtualHostNameToFolderMapping(
                "gogdl.local", str(PROJECT / "assets"), CoreWebView2HostResourceAccessKind.Deny
            )
            core.Settings.AreDevToolsEnabled = False
            core.Settings.AreDefaultContextMenusEnabled = True
            core.Settings.AreHostObjectsAllowed = False
            core.NavigationStarting += local_navigate
            core.NewWindowRequested += block_popup
            core.WebMessageReceived += message
            core.Navigate(HOME)
            backend.load_catalog()
            backend.refresh_disk()

        def tick(_sender, _event):
            nonlocal disk_ticks, pending_update
            backend.poll()
            for kind, data in backend.messages:
                if kind == "restartWithUpdate":
                    pending_update = data
                    form.Close()
                    return
                if kind == "focusAfterLogin":
                    if form.WindowState == FormWindowState.Minimized:
                        form.WindowState = FormWindowState.Normal
                    form.Activate()
                else:
                    push(kind, data)
            backend.messages.clear()
            if backend.dirty:
                push("state", backend.snapshot())
                backend.dirty = False
            disk_ticks += 1
            if disk_ticks >= 35:
                disk_ticks = 0
                backend.refresh_disk()

        def closing(_sender, args):
            if backend.updating_app and pending_update is None:
                MessageBox.Show(label("Please wait for the update check.", "Подождите завершения проверки обновления."), "GOGDL")
                args.Cancel = True
                return
            if backend.authenticating and not backend.login_state:
                MessageBox.Show(label("Please wait for GOG sign-in to finish.", "Подождите завершения входа в GOG."), "GOGDL")
                args.Cancel = True
                return
            if backend.process and backend.process.poll() is None:
                if MessageBox.Show(label("Stop the current operation?", "Остановить текущую операцию?"), "GOGDL",
                                   MessageBoxButtons.YesNo) != DialogResult.Yes:
                    args.Cancel = True
                    return
                backend.stop()
            bounds = form.Bounds if form.WindowState == FormWindowState.Normal else form.RestoreBounds
            try:
                backend.save(window_geometry=f"{bounds.Width}x{bounds.Height}+{bounds.X}+{bounds.Y}",
                             window_maximized=form.WindowState == FormWindowState.Maximized)
            except OSError:
                MessageBox.Show(label("Could not save the window position.", "Не удалось сохранить положение окна."), "GOGDL")
            backend.cancel_login()
            timer.Stop()

        timer = Timer()
        timer.Interval = 150
        timer.Tick += tick
        form.FormClosing += closing
        view.CoreWebView2InitializationCompleted += initialized
        form.Shown += lambda _sender, _event: view.EnsureCoreWebView2Async(None)
        timer.Start()
        try:
            Application.Run(form)
        finally:
            timer.Dispose()
            form.Dispose()

    thread = Thread(ThreadStart(window_loop))
    thread.SetApartmentState(ApartmentState.STA)
    thread.Start()
    thread.Join()
    if not failures.empty():
        raise failures.get()
    if pending_update:
        try:
            install_and_restart(PROJECT, pending_update)
        except (OSError, ValueError) as error:
            message = "Не удалось установить обновление." if language == "ru" else "Could not install the update."
            MessageBox.Show(f"{message}\n\n{error}", "GOGDL")
            restart(PROJECT)


if __name__ == "__main__":
    try:
        run()
    except Exception as error:
        ctypes.windll.user32.MessageBoxW(
            None, f"Could not start GOGDL.\n\n{error}", "GOGDL", 0x10,
        )
