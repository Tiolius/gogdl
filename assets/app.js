"use strict";
const bridge = window.chrome.webview;
const get = (id) => document.getElementById(id);
const button = (id) => get(id);
const send = (action, value) => bridge.postMessage(JSON.stringify({ action, value }));
function setIconLabel(control, name, label) {
    const icon = document.createElement("span");
    icon.classList.add("material", name + "-symbol");
    icon.setAttribute("aria-hidden", "true");
    control.replaceChildren(icon, label);
}
const search = get("search");
const matches = get("matches");
const selected = new Set();
let selectedGame;
let games = [];
let settings;
let draft = {};
let activeTab = "Аккаунт GOG";
let lastQueue = "";
let lastLog = "";
let resumePrompt = false;
let state;
const russian = {
    "Save your settings first.": "Сначала сохраните настройки.",
    "Cancel": "Отмена", "Continue": "Продолжить", "OK": "ОК",
    "GOG game catalog": "Каталог игр GOG",
    "Settings": "Настройки", "Updates": "Обновления", "Refresh catalog": "Обновить каталог",
    "Refresh the catalog first": "Сначала обновите каталог", "Selected size: 0 B": "Объём выбранных: 0 Б",
    "Download selected": "Скачать выбранные", "Download one game": "Одна игра из каталога",
    "Download game": "Скачать игру", "Reading catalog…": "Чтение каталога…", "Activity log": "Журнал выполнения",
    "Ready": "Готово к запуску", "Open project folder": "Открыть папку проекта", "Stop": "Остановить",
    "Back": "Назад", "Settings sections": "Разделы настроек", "Switch to English": "Переключить на английский",
    "GOGDL version": "Версия GOGDL", "Author": "Автор", "Version date": "Дата версии", "Save": "Сохранить",
    "Update": "Обновить", "Updates list": "Список обновлений",
    "Search by title or ID": "Поиск по названию или ID", "Show games": "Показать список игр",
    "Light theme": "Светлая тема", "Dark theme": "Тёмная тема",
    "Free disk space: ": "Свободно на диске: ", "Selected size: ": "Объём выбранных: ", "Game size: ": "Объём игры: ",
    "GOG token saved": "Токен GOG сохранён", "Not signed in": "Вход ещё не выполнен",
    "Updates: ": "Обновлений: ", ". Select the games to download.": ". Отметьте игры для загрузки.",
    "No updates in the queue": "В очереди нет обновлений",
    "The previous update is incompatible. Discard it and continue?": "Предыдущее обновление несовместимо. Сбросить его и продолжить?",
    "GOG access token": "Токен доступа GOG",
    "Paste an access token or token JSON": "Вставьте токен доступа или JSON с токеном",
    "Save token": "Сохранить токен", "Remove token": "Удалить токен",
    "Remove the saved GOG token from this device?": "Удалить сохранённый токен GOG с этого устройства?",
    "Sign in with browser": "Войти через браузер", "Cancel sign-in": "Отменить вход",
    "Remove the password saved by an older version": "Удалить пароль, сохранённый в прежней версии",
    "Browse…": "Обзор…", "Stop the current operation?": "Остановить текущую операцию?",
    "Install the update from GitHub main and restart GOGDL?": "Установить обновление из ветки main на GitHub и перезапустить GOGDL?",
};
const english = {
    "Аккаунт GOG": "GOG account", "Каталог": "Catalog", "Загрузка": "Downloads",
    "Журнал": "Log", "Версия": "Version",
    "ОС": "Operating systems", "Исключить ОС": "Exclude operating systems",
    "Языки": "Languages", "Исключить языки": "Exclude languages",
    "Режим обновления": "Refresh mode", "Новые игры и обновления": "New games and updates",
    "Только новые игры": "New games only", "Только обновления": "Updates only", "Весь каталог": "Entire catalog",
    "Незавершённое обновление": "Incomplete refresh", "Продолжить при наличии": "Resume if available",
    "Начать заново": "Start over", "Только продолжить": "Resume only",
    "Тип установщиков": "Installer type", "Автономные": "Standalone", "Автономные и Galaxy": "Standalone and Galaxy",
    "Обновить только эти ID или slug": "Refresh only these IDs or slugs", "Исключить ID или slug": "Exclude IDs or slugs",
    "Задержка перед проверкой, ч": "Delay before refresh, hours", "Пропускать скрытые игры": "Skip hidden games",
    "Пропускать списки изменений": "Skip changelogs", "Сохранять файлы контрольных сумм MD5": "Save MD5 checksum files",
    "Сохранять статус проверки только при совпадении MD5": "Keep verification status only if MD5 matches",
    "При поиске дубликатов учитывать отсутствие MD5": "Check for missing MD5 when finding duplicates",
    "Мягкая проверка изменений установщиков": "Lenient installer change detection",
    "Строгая проверка изменений дополнительных материалов": "Strict change detection for extras",
    "Папка загрузки": "Download folder", "Исключить файлы или шаблоны через ;": "Exclude files or patterns separated by semicolons",
    "Задержка перед каждой игрой, ч": "Delay before each game, hours", "Лимит на игру, МиБ": "Limit per game, Mb",
    "Скачивать обложки": "Download covers", "Скачивать фоны": "Download backgrounds",
    "Удалять старые обложки и фоны вместо переноса в !orphaned": "Delete old covers and backgrounds instead of moving them to !orphaned",
    "Пропускать дополнительные материалы": "Skip extras", "Пропускать автономные установщики": "Skip standalone installers",
    "Пропускать установщики Galaxy": "Skip Galaxy installers", "Пропускать общие установщики": "Skip shared installers",
    "Не резервировать место под файлы заранее": "Skip file preallocation",
    "Не записывать вывод в gogrepo.log": "Disable writing to gogrepo.log", "Показывать отладочные сообщения": "Show debug messages",
    "Вход отменён": "Sign-in canceled", "Готово к запуску": "Ready",
    "Не удалось открыть браузер": "Could not open a browser",
    "Войдите в GOG в браузере. Приложение получит токен автоматически": "Sign in to GOG in your browser. GOGDL will obtain the token automatically",
    "Не удалось отследить завершение входа в браузере": "Could not detect completed sign-in in the browser",
    "Время ожидания входа истекло": "Sign-in timed out",
    "Введите токен доступа GOG или JSON с токеном.": "Enter a GOG access token or token JSON.",
    "Не удалось сохранить токен GOG": "Could not save the GOG token",
    "Токен GOG сохранён": "GOG token saved", "Токен GOG удалён": "GOG token removed",
    "Не удалось удалить токен GOG": "Could not remove the GOG token",
    "Чтение каталога…": "Reading catalog…", "Сначала обновите каталог": "Refresh the catalog first",
    "Не удалось прочитать каталог": "Could not read the catalog", "недоступно": "unavailable",
    "Проверка каталога…": "Refreshing catalog…", "Загрузка…": "Downloading…",
    "Укажите полный путь к папке загрузки.": "Enter the full path to the download folder.",
    "Выберите существующую папку загрузки в настройках.": "Choose an existing download folder in Settings.",
    "Получение токена GOG…": "Obtaining GOG token…",
    "Вход в GOG выполнен": "Signed in to GOG", "Не удалось получить токен GOG": "Could not obtain GOG token",
    "Остановлено": "Stopped", "Проверяем обновление GOGDL…": "Checking for a GOGDL update…",
    "Перезапускаем GOGDL…": "Restarting GOGDL…", "Установлена актуальная версия GOGDL": "GOGDL is up to date",
    "Для ОС и языков заполните либо список включения, либо список исключения.": "For each operating system or language filter, use either the inclusion or exclusion list.",
    "Для обновления заполните либо список выбранных игр, либо список исключений.": "For catalog refresh, use either the selected games or the exclusions list.",
    "Задержка должна быть неотрицательной, а лимит — положительным числом.": "Enter a nonnegative delay and a positive limit.",
    "Некорректный формат настроек": "Invalid settings format",
};
const englishPrefixes = [
    ["Не удалось отследить завершение входа в браузере · ", "Could not detect completed sign-in in the browser · "],
    ["Игр в каталоге: ", "Games in catalog: "], ["Ошибка запуска: ", "Launch error: "],
    ["Процесс завершён · код ", "Process finished · exit code "],
    ["Не удалось прочитать настройки: ", "Could not read settings: "],
    ["Не удалось обновить GOGDL: ", "Could not update GOGDL: "],
    ["Неизвестные коды: ", "Unknown codes: "],
];
const sizeUnits = {
    en: ["B", "KiB", "Mb", "Gb", "TiB"],
    ru: ["Б", "КиБ", "Mb", "Gb", "ТиБ"],
};
const backendUnits = ["Б", "КиБ", "МиБ", "ГиБ", "ТиБ"];
const locale = () => settings?.language === "ru" ? "ru-RU" : "en-US";
const tr = (label) => settings?.language === "ru" ? russian[label] ?? label : label;
function translate(value) {
    const disk = /^(\d+(?:[.,]\d+)?) (Б|КиБ|МиБ|ГиБ|Mb|Gb|ТиБ)$/.exec(value);
    if (disk) {
        const units = sizeUnits[settings?.language ?? "en"];
        const unit = units.includes(disk[2]) ? disk[2] : units[backendUnits.indexOf(disk[2])];
        return Number(disk[1].replace(",", ".")).toLocaleString(locale(), { maximumFractionDigits: 2 }) + " " + unit;
    }
    if (settings?.language === "ru")
        return value.replace("Лимит на игру, МиБ", "Лимит на игру, Mb");
    if (Object.hasOwn(english, value))
        return english[value];
    for (const [prefix, label] of englishPrefixes) {
        if (value.startsWith(prefix))
            return label + translate(value.slice(prefix.length));
    }
    const fieldError = /^(Проверьте значение поля|Выберите значение для поля) «(.+)»[.]$/.exec(value);
    if (fieldError) {
        const verb = fieldError[1] === "Проверьте значение поля" ? "Check the value for" : "Choose a value for";
        return verb + ' "' + translate(fieldError[2]) + '".';
    }
    return value;
}
const appDialog = get("appDialog");
let dialogQueue = Promise.resolve();
function showDialog(message, action) {
    const result = dialogQueue.then(() => new Promise(resolve => {
        const cancel = button("dialogCancel");
        const accept = button("dialogAccept");
        get("appDialogMessage").textContent = message;
        cancel.textContent = tr("Cancel");
        cancel.hidden = !action;
        accept.textContent = tr(action ?? "OK");
        cancel.onclick = () => appDialog.close("cancel");
        accept.onclick = () => appDialog.close("accept");
        appDialog.returnValue = "";
        appDialog.onclose = () => resolve(appDialog.returnValue === "accept");
        appDialog.showModal();
        (action ? cancel : accept).focus();
    }));
    dialogQueue = result.then(() => undefined, () => undefined);
    return result;
}
function localizePage() {
    document.documentElement.lang = settings?.language ?? "en";
    const language = button("language");
    language.textContent = document.documentElement.lang.toUpperCase();
    language.title = settings?.language === "ru" ? tr("Switch to English") : "Switch to Russian";
    language.setAttribute("aria-label", language.title);
    document.querySelectorAll("[data-text]").forEach(element => {
        element.textContent = tr(element.dataset.text ?? "");
    });
    for (const [id, label] of [["queue", "Updates list"], ["showGames", "Show games"], ["tabs", "Settings sections"], ["search", "Search by title or ID"]]) {
        get(id).setAttribute("aria-label", tr(label));
    }
    search.placeholder = tr("Search by title or ID");
}
function size(bytes) {
    const units = sizeUnits[settings?.language ?? "en"];
    let unit = 0;
    while (bytes >= 1024 && unit < units.length - 1) {
        bytes /= 1024;
        unit++;
    }
    return bytes.toLocaleString(locale(), { maximumFractionDigits: 2 }) + " " + units[unit];
}
function refreshSelection() {
    const total = games.reduce((sum, game) => sum + (selected.has(game[0]) ? game[3] : 0), 0);
    const free = tr("Free disk space: ") + translate(state?.free ?? "…");
    get("queueSize").textContent = tr("Selected size: ") + size(total) + " · " + free;
    get("gameSize").textContent = tr("Game size: ") + (selectedGame ? size(selectedGame[3]) : "—") + " · " + free;
    button("downloadQueue").disabled = !selected.size || !!state?.busy;
    button("downloadGame").disabled = !selectedGame || !!state?.busy;
}
function refreshAccount() {
    const account = document.getElementById("accountStatus");
    const login = document.querySelector("#accountLogin");
    const cancel = document.querySelector("#cancelLogin");
    if (!account || !login || !cancel)
        return;
    account.textContent = translate(state?.loginStatus ?? "") || (state?.signedIn ? tr("GOG token saved") : tr("Not signed in"));
    login.disabled = !!state?.busy;
    login.hidden = !!state?.authenticating;
    cancel.hidden = !state?.awaitingLogin;
    if (cancel.hidden)
        cancel.disabled = false;
    const remove = button("removeAccountToken");
    remove.hidden = !state?.signedIn || !!state?.authenticating;
    remove.disabled = !!state?.busy;
    const credential = get("accountCredential");
    const authenticating = !!state?.authenticating;
    get("accountCredentialLabel").hidden = authenticating;
    get("accountCredentialField").hidden = authenticating;
    if (authenticating)
        credential.value = "";
    credential.placeholder = state?.signedIn ? "••••••••" : tr("Paste an access token or token JSON");
    credential.disabled = !!state?.busy;
    button("saveAccountCredential").disabled = credential.disabled || !credential.value.trim();
}
function renderState(next) {
    const old = state;
    state = next;
    if (old && old.queueGeneration !== next.queueGeneration)
        selected.clear();
    button("update").disabled = next.busy;
    button("settings").disabled = next.busy && !next.authenticating;
    button("stop").disabled = !next.busy || next.authenticating || next.updatingApp;
    get("status").textContent = translate(next.status);
    button("updateApp").disabled = next.busy;
    get("appUpdateStatus").textContent = translate(next.appUpdateStatus);
    get("catalogStatus").textContent = translate(next.catalogStatus);
    get("queueHint").textContent = next.queue.length
        ? tr("Updates: ") + next.queue.length + tr(". Select the games to download.")
        : next.catalogStatus === "Сначала обновите каталог" ? translate(next.catalogStatus) : tr("No updates in the queue");
    const signature = JSON.stringify([next.queueGeneration, next.queue]);
    if (signature !== lastQueue) {
        lastQueue = signature;
        const remaining = new Set(next.queue.map(([id]) => id));
        for (const id of selected)
            if (!remaining.has(id))
                selected.delete(id);
        get("queue").replaceChildren(...next.queue.map(([id, title]) => {
            const row = document.createElement("label");
            const checkbox = document.createElement("input");
            checkbox.type = "checkbox";
            checkbox.checked = selected.has(id);
            checkbox.disabled = next.busy;
            checkbox.onchange = () => {
                if (checkbox.checked)
                    selected.add(id);
                else
                    selected.delete(id);
                refreshSelection();
            };
            row.append(checkbox, title);
            return row;
        }));
    }
    else if (old?.busy !== next.busy) {
        get("queue").querySelectorAll("input").forEach(field => { field.disabled = next.busy; });
    }
    if (lastLog !== next.log) {
        const log = get("log");
        const follow = log.scrollHeight - log.scrollTop - log.clientHeight < 25;
        lastLog = next.log;
        log.textContent = next.log.split("\n").map(translate).join("\n");
        if (follow)
            log.scrollTop = log.scrollHeight;
    }
    if (next.resume && !resumePrompt) {
        resumePrompt = true;
        void showDialog(tr("The previous update is incompatible. Discard it and continue?"), "Continue").then(confirmed => {
            if (state?.resume)
                send("resume", confirmed);
        });
    }
    else if (!next.resume) {
        resumePrompt = false;
    }
    refreshSelection();
    refreshAccount();
}
function showMatches(query) {
    const filter = query.trim().toLocaleLowerCase();
    const filtered = games.filter(([id, title, slug]) => id.includes(filter) || title.toLocaleLowerCase().includes(filter) || slug.toLocaleLowerCase().includes(filter));
    matches.replaceChildren(...filtered.map(game => {
        const option = document.createElement("button");
        option.textContent = game[1];
        option.onclick = () => {
            selectedGame = game;
            search.value = game[1];
            matches.hidden = true;
            refreshSelection();
        };
        option.onkeydown = event => {
            if (event.key !== "ArrowDown" && event.key !== "ArrowUp")
                return;
            event.preventDefault();
            const sibling = event.key === "ArrowDown" ? option.nextElementSibling : option.previousElementSibling;
            sibling?.focus();
        };
        return option;
    }));
    matches.hidden = !filtered.length;
}
function renderSettings() {
    if (!settings)
        return;
    const names = ["Аккаунт GOG", ...Object.keys(settings.groups), "Версия"];
    get("tabs").replaceChildren(...names.map(name => {
        const tab = document.createElement("button");
        tab.textContent = translate(name);
        tab.setAttribute("aria-current", String(name === activeTab));
        tab.onclick = () => {
            activeTab = name;
            renderSettings();
        };
        return tab;
    }));
    const form = get("settingsForm");
    form.replaceChildren();
    const showVersion = activeTab === "Версия";
    get("versionInfo").hidden = !showVersion;
    form.hidden = showVersion;
    get("settingsFooter").hidden = showVersion;
    if (showVersion)
        return;
    if (activeTab === "Аккаунт GOG") {
        const account = document.createElement("p");
        account.id = "accountStatus";
        account.setAttribute("role", "status");
        const login = document.createElement("button");
        login.id = "accountLogin";
        login.className = "primary";
        setIconLabel(login, "login", tr("Sign in with browser"));
        login.onclick = () => {
            login.disabled = true;
            send("login");
        };
        const cancel = document.createElement("button");
        cancel.id = "cancelLogin";
        cancel.textContent = tr("Cancel sign-in");
        cancel.onclick = () => {
            cancel.disabled = true;
            send("cancelLogin");
        };
        const credentialLabel = document.createElement("label");
        credentialLabel.id = "accountCredentialLabel";
        credentialLabel.htmlFor = "accountCredential";
        credentialLabel.textContent = tr("GOG access token");
        const credential = document.createElement("input");
        credential.id = "accountCredential";
        credential.type = "password";
        credential.autocomplete = "new-password";
        const saveCredential = document.createElement("button");
        saveCredential.id = "saveAccountCredential";
        saveCredential.textContent = tr("Save token");
        saveCredential.onclick = () => {
            send("saveToken", credential.value.trim());
            credential.value = "";
            saveCredential.disabled = true;
        };
        credential.oninput = refreshAccount;
        credential.onkeydown = event => {
            if (event.key === "Enter" && !saveCredential.disabled)
                saveCredential.click();
        };
        const field = document.createElement("div");
        field.id = "accountCredentialField";
        field.className = "actions account-credential";
        field.append(credential, saveCredential);
        const remove = document.createElement("button");
        remove.id = "removeAccountToken";
        remove.textContent = tr("Remove token");
        remove.onclick = async () => {
            if (await showDialog(tr("Remove the saved GOG token from this device?"), "Remove token"))
                send("removeToken");
        };
        const actions = document.createElement("div");
        actions.className = "actions";
        actions.append(login, cancel, remove);
        form.append(account, actions, credentialLabel, field);
        refreshAccount();
        if (settings.savedLogin) {
            const forget = document.createElement("button");
            forget.textContent = tr("Remove the password saved by an older version");
            forget.onclick = () => send("forgetLogin");
            form.append(" ", forget);
        }
        return;
    }
    for (const field of settings.groups[activeTab] ?? []) {
        const row = document.createElement("label");
        const value = draft[field.key] ?? field.value;
        row.className = "setting";
        if (typeof value === "boolean") {
            const input = document.createElement("input");
            input.type = "checkbox";
            input.checked = value;
            input.onchange = () => { draft[field.key] = input.checked; };
            row.classList.add("check");
            row.append(input, translate(field.label));
        }
        else {
            const label = document.createElement("span");
            label.textContent = translate(field.label);
            const editor = field.choices.length ? document.createElement("select") : document.createElement("input");
            if (editor instanceof HTMLSelectElement) {
                for (const [name] of field.choices)
                    editor.add(new Option(translate(name), name));
            }
            editor.value = value;
            editor.oninput = () => { draft[field.key] = editor.value; };
            row.append(label);
            if (field.key === "destination") {
                const path = document.createElement("span");
                path.className = "folder";
                const browse = document.createElement("button");
                setIconLabel(browse, "folder", tr("Browse…"));
                browse.onclick = () => send("browse");
                path.append(editor, browse);
                row.append(path);
            }
            else {
                row.append(editor);
            }
        }
        form.append(row);
    }
}
function closeSettings() {
    get("preferences").hidden = true;
    get("home").hidden = false;
    draft = {};
    button("settings").focus();
}
search.oninput = () => { selectedGame = undefined; showMatches(search.value); refreshSelection(); };
search.onkeydown = event => {
    if (event.key === "ArrowDown") {
        event.preventDefault();
        if (matches.hidden)
            showMatches(selectedGame ? "" : search.value);
        matches.querySelector("button")?.focus();
    }
};
document.addEventListener("click", event => {
    if (!event.target.closest(".field"))
        matches.hidden = true;
});
document.addEventListener("keydown", event => {
    if (event.key !== "Escape" || appDialog.open)
        return;
    if (!matches.hidden) {
        matches.hidden = true;
        search.focus();
    }
    else if (!get("preferences").hidden)
        closeSettings();
});
button("showGames").onclick = () => {
    if (matches.hidden)
        showMatches(selectedGame ? "" : search.value);
    else
        matches.hidden = true;
};
button("theme").onclick = () => send("theme");
button("settings").onclick = () => {
    if (!settings)
        return;
    get("preferences").hidden = false;
    get("home").hidden = true;
    renderSettings();
};
button("language").onclick = () => send("language", settings?.language === "ru" ? "en" : "ru");
button("updateApp").onclick = async () => {
    if (Object.keys(draft).length) {
        void showDialog(tr("Save your settings first."));
        return;
    }
    if (await showDialog(tr("Install the update from GitHub main and restart GOGDL?"), "Update") && !state?.busy) {
        button("updateApp").disabled = true;
        send("updateApplication");
    }
};
button("back").onclick = closeSettings;
button("save").onclick = () => send("settings", draft);
button("update").onclick = () => send("update");
button("openFolder").onclick = () => send("openFolder");
button("stop").onclick = async () => {
    if (await showDialog(tr("Stop the current operation?"), "Stop"))
        send("stop");
};
button("downloadQueue").onclick = () => send("queue", state?.queue.filter(([id]) => selected.has(id)).map(([id]) => id));
button("downloadGame").onclick = () => { if (selectedGame)
    send("download", [selectedGame[0]]); };
bridge.addEventListener("message", event => {
    const { kind, data } = JSON.parse(event.data);
    if (kind === "state")
        renderState(data);
    else if (kind === "catalog") {
        games = data;
        if (selectedGame)
            selectedGame = games.find(game => game[0] === selectedGame?.[0]);
        if (!matches.hidden)
            showMatches(search.value);
        refreshSelection();
    }
    else if (kind === "settings" || kind === "settingsSaved") {
        settings = data;
        localizePage();
        if (state) {
            lastLog = "";
            renderState(state);
        }
        const { number, author, date } = settings.version;
        get("versionNumber").textContent = number;
        get("versionAuthor").textContent = author;
        const releaseDate = get("versionDate");
        releaseDate.dateTime = date;
        releaseDate.textContent = new Intl.DateTimeFormat(locale(), {
            dateStyle: "long", timeZone: "UTC",
        }).format(new Date(date));
        document.documentElement.dataset.theme = settings.theme;
        const theme = button("theme");
        const dark = settings.theme === "dark";
        theme.title = dark ? tr("Light theme") : tr("Dark theme");
        theme.setAttribute("aria-label", theme.title);
        if (kind === "settingsSaved")
            closeSettings();
        else if (!get("preferences").hidden)
            renderSettings();
    }
    else if (kind === "destination") {
        draft.destination = String(data);
        renderSettings();
    }
    else if (kind === "error") {
        if (!get("preferences").hidden)
            renderSettings();
        void showDialog(translate(String(data)));
    }
});
send("ready");
