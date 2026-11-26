"""Windows host for the local TypeScript UI and the real GOG sign-in page."""

import ctypes
import json
import os
import queue
import re
import secrets
import sys
import time
from urllib.parse import parse_qs, urlsplit

from gogdl_backend import Backend, GOG_PAGES, PROJECT, auth_url, callback_code

HOME = "https://gogdl.local/index.html"


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
        Application, Button, DialogResult, DockStyle, FolderBrowserDialog, Form,
        FormStartPosition, FormWindowState, Label, MessageBox, MessageBoxButtons, Panel, Timer,
    )

    failures = queue.Queue()

    def window_loop():
        try:
            show_window()
        except Exception as error:
            failures.put(error)

    def show_window():
        Application.EnableVisualStyles()
        backend = Backend()
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
        view.DefaultBackgroundColor = Color.FromArgb(17, 18, 20) if backend.settings["theme"] == "dark" else Color.White
        properties = CoreWebView2CreationProperties()
        properties.UserDataFolder = str(PROJECT / ".gogdl-profile")
        view.CreationProperties = properties
        form.Controls.Add(view)
        auth_view = WebView2()
        auth_view.Dock = DockStyle.Fill
        auth_view.DefaultBackgroundColor = view.DefaultBackgroundColor
        auth_bar = Panel()
        auth_bar.Dock = DockStyle.Top
        auth_bar.Height = 42
        auth_bar.Visible = False
        back = Button()
        back.Text = "Вернуться в GOGDL"
        back.Width = 160
        back.Height = 28
        back.Location = Point(8, 6)
        auth_bar.Controls.Add(back)
        retry = Button()
        retry.Text = "Перезагрузить форму"
        retry.Size = Size(155, 28)
        retry.Location = Point(175, 6)
        auth_bar.Controls.Add(retry)
        auth_status = Label()
        auth_status.AutoEllipsis = True
        auth_status.Location = Point(340, 8)
        auth_status.Height = 24
        auth_bar.Resize += lambda _sender, _event: setattr(auth_status, "Width", max(0, auth_bar.Width - 345))
        auth_bar.Controls.Add(auth_status)
        form.Controls.Add(auth_bar)
        auth_bar.BringToFront()

        ready = False
        auth_state = None
        auth_url_pending = None
        auth_blank_pending = False
        auth_active = False
        auth_ready = False
        auth_initializing = False
        auth_started = 0.0
        auth_probe = None
        auth_probe_at = 0.0
        auth_challenge_status = None
        disk_ticks = 0

        def push(kind, data):
            if ready and str(view.Source) == HOME:
                view.CoreWebView2.PostWebMessageAsString(json.dumps({"kind": kind, "data": data}, ensure_ascii=False))

        def go_home():
            nonlocal auth_state, auth_url_pending, auth_blank_pending, auth_active, auth_ready, auth_probe
            auth_state = None
            auth_url_pending = None
            auth_active = False
            auth_ready = False
            auth_probe = None
            auth_bar.Visible = False
            view.BringToFront()
            auth_blank_pending = True
            push("authReturned", None)

        def cancel_login(_sender, _event):
            backend.authenticating = False
            backend.status = "Вход отменён"
            backend.dirty = True
            go_home()

        back.Click += cancel_login

        def auth_navigate(_sender, args):
            nonlocal auth_state, auth_ready, auth_challenge_status
            url = str(args.Uri)
            if url == "about:blank" and not auth_state:
                return
            if not auth_state:
                args.Cancel = True
                return
            parsed = urlsplit(url)
            code = callback_code(url)
            if code:
                args.Cancel = True
                if not auth_active:
                    auth_ready = False
                    auth_state = None
                    return
                state = parse_qs(parsed.query).get("state", [""])[0]
                if secrets.compare_digest(state.encode(), auth_state.encode()):
                    backend.exchange_code(code)
                else:
                    backend.authenticating = False
                    backend.status = "GOG вернул ответ без подтверждения текущего входа"
                    backend.dirty = True
                go_home()
            elif parsed.scheme != "https" or parsed.netloc not in GOG_PAGES:
                args.Cancel = True
            else:
                auth_challenge_status = None

        def show_auth():
            auth_view.BringToFront()
            auth_bar.BringToFront()
            auth_view.Focus()

        def auth_loaded(_sender, _args):
            nonlocal auth_ready
            if not auth_state or not auth_view.Source or auth_view.Source.Host not in GOG_PAGES:
                return
            auth_ready = True
            if auth_active:
                auth_status.Text = "Проверка GOG…"
                show_auth()

        def auth_completed(_sender, args):
            nonlocal auth_ready, auth_state
            if auth_state and not args.IsSuccess and str(args.WebErrorStatus) != "OperationCanceled":
                auth_ready = False
                auth_state = None
                if auth_active:
                    auth_status.Text = "GOG не открылся. Перезагрузите форму."

        def auth_resource(_sender, args):
            nonlocal auth_challenge_status
            if (urlsplit(str(args.Request.Uri)).hostname == "challenges.cloudflare.com"
                and args.Response.StatusCode >= 400):
                auth_challenge_status = args.Response.StatusCode

        def auth_initialized(_sender, args):
            nonlocal auth_initializing, auth_state, auth_url_pending
            auth_initializing = False
            if not args.IsSuccess:
                auth_state = None
                auth_url_pending = None
                if auth_active:
                    auth_status.Text = "Не удалось открыть форму GOG."
                return
            core = auth_view.CoreWebView2
            core.Settings.AreHostObjectsAllowed = False
            core.Settings.AreDevToolsEnabled = False
            core.Settings.IsWebMessageEnabled = False
            core.Settings.IsPasswordAutosaveEnabled = True
            core.NavigationStarting += auth_navigate
            core.DOMContentLoaded += auth_loaded
            core.NavigationCompleted += auth_completed
            core.WebResourceResponseReceived += auth_resource
            core.NewWindowRequested += block_popup

        def prepare_auth(force=False):
            nonlocal auth_state, auth_url_pending, auth_blank_pending, auth_ready, auth_started, auth_initializing, auth_probe
            if auth_state and not force and time.monotonic() - auth_started < 90:
                return
            auth_state = secrets.token_urlsafe(24)
            auth_blank_pending = False
            auth_url_pending = auth_url(auth_state)
            auth_started = time.monotonic()
            auth_ready = False
            auth_probe = None
            if auth_view.CoreWebView2:
                auth_view.CoreWebView2.Stop()
            elif not auth_initializing:
                auth_initializing = True
                if not auth_view.Parent:
                    form.Controls.Add(auth_view)
                auth_view.SendToBack()
                auth_view.EnsureCoreWebView2Async(view.CoreWebView2.Environment)

        def begin_auth():
            nonlocal auth_active
            prepare_auth()
            auth_active = True
            backend.authenticating = True
            backend.dirty = True
            auth_status.Text = "Загружается форма GOG…"
            auth_bar.Visible = True
            auth_bar.BringToFront()
            if auth_ready:
                show_auth()

        def retry_auth(_sender, _event):
            view.BringToFront()
            auth_bar.BringToFront()
            auth_status.Text = "Загружается форма GOG…"
            prepare_auth(force=True)

        retry.Click += retry_auth
        auth_view.CoreWebView2InitializationCompleted += auth_initialized

        def message(_sender, args):
            nonlocal ready
            # Only the bundled document can invoke host commands.
            if str(args.Source) != HOME or str(view.Source) != HOME or auth_active:
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
                elif action == "theme":
                    backend.save(theme="light" if backend.settings["theme"] == "dark" else "dark")
                    view.DefaultBackgroundColor = (Color.FromArgb(17, 18, 20)
                                                   if backend.settings["theme"] == "dark" else Color.White)
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
                elif action == "warmLogin" and not backend.process and not backend.authenticating:
                    prepare_auth()
                elif action == "login" and not backend.process and not backend.authenticating:
                    begin_auth()
            except (OSError, ValueError, TypeError) as error:
                push("error", str(error))

        def block_popup(_sender, args):
            args.Handled = True

        def local_navigate(_sender, args):
            if str(args.Uri) != HOME:
                args.Cancel = True

        def initialized(_sender, args):
            if not args.IsSuccess:
                MessageBox.Show("Не удалось запустить Microsoft Edge WebView2.", "GOGDL")
                form.Close()
                return
            core = view.CoreWebView2
            core.SetVirtualHostNameToFolderMapping(
                "gogdl.local", str(PROJECT / "assets"), CoreWebView2HostResourceAccessKind.Deny
            )
            core.Settings.AreDevToolsEnabled = False
            core.Settings.AreDefaultContextMenusEnabled = True
            core.Settings.AreHostObjectsAllowed = False
            core.Settings.IsPasswordAutosaveEnabled = True
            core.NavigationStarting += local_navigate
            core.NewWindowRequested += block_popup
            core.WebMessageReceived += message
            core.Navigate(HOME)
            backend.load_catalog()
            backend.refresh_disk()

        def tick(_sender, _event):
            nonlocal auth_url_pending, auth_blank_pending, auth_probe, auth_probe_at, disk_ticks
            if auth_blank_pending and auth_view.CoreWebView2:
                auth_blank_pending = False
                auth_view.CoreWebView2.Stop()
                auth_view.CoreWebView2.Navigate("about:blank")
            if auth_url_pending and auth_view.CoreWebView2:
                url, auth_url_pending = auth_url_pending, None
                auth_view.CoreWebView2.Navigate(url)
            if auth_active and auth_ready and auth_view.CoreWebView2:
                now = time.monotonic()
                if auth_probe is not None and auth_probe.IsCompleted:
                    if not auth_probe.IsFaulted and not auth_probe.IsCanceled:
                        result = str(auth_probe.Result)
                        if result == '"waiting"':
                            if auth_challenge_status:
                                auth_status.Text = f"Turnstile: HTTP {auth_challenge_status}. Перезагрузите форму."
                            else:
                                auth_status.Text = ("Проверка GOG задерживается. Можно перезагрузить форму."
                                                    if now - auth_started > 22 else "Ожидаем проверку GOG…")
                        elif result == '"ready"':
                            auth_status.Text = ""
                    auth_probe = None
                if auth_probe is None and now - auth_probe_at >= 2:
                    auth_probe_at = now
                    auth_probe = auth_view.CoreWebView2.ExecuteScriptAsync(
                        """(() => {
                            const form = document.querySelector('form[name="login"]');
                            if (!form) return 'ready';
                            const widget = form.querySelector('#turnstile_captcha_login');
                            const submit = form.querySelector('[type="submit"]');
                            return widget && submit?.disabled ? 'waiting' : 'ready';
                        })()"""
                    )
            elif auth_active and auth_state and time.monotonic() - auth_started > 18:
                auth_status.Text = "GOG долго отвечает. Можно перезагрузить форму."
            backend.poll()
            for kind, data in backend.messages:
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
            if backend.authenticating and not auth_active:
                MessageBox.Show("Подождите завершения входа в GOG.", "GOGDL")
                args.Cancel = True
                return
            if backend.process and backend.process.poll() is None:
                if MessageBox.Show("Остановить текущую операцию?", "GOGDL",
                                   MessageBoxButtons.YesNo) != DialogResult.Yes:
                    args.Cancel = True
                    return
                backend.stop()
            bounds = form.Bounds if form.WindowState == FormWindowState.Normal else form.RestoreBounds
            try:
                backend.save(window_geometry=f"{bounds.Width}x{bounds.Height}+{bounds.X}+{bounds.Y}",
                             window_maximized=form.WindowState == FormWindowState.Maximized)
            except OSError:
                MessageBox.Show("Не удалось сохранить положение окна.", "GOGDL")
            timer.Stop()

        timer = Timer()
        timer.Interval = 150
        timer.Tick += tick
        form.FormClosing += closing
        view.CoreWebView2InitializationCompleted += initialized
        form.Shown += lambda _sender, _event: view.EnsureCoreWebView2Async(None)
        timer.Start()
        Application.Run(form)

    thread = Thread(ThreadStart(window_loop))
    thread.SetApartmentState(ApartmentState.STA)
    thread.Start()
    thread.Join()
    if not failures.empty():
        raise failures.get()


if __name__ == "__main__":
    try:
        run()
    except Exception as error:
        ctypes.windll.user32.MessageBoxW(
            None, f"Не удалось запустить WebView2.\n\n{error}", "GOGDL", 0x10,
        )
