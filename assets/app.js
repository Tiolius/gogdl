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
function size(bytes) {
    const units = ["Б", "КиБ", "МиБ", "ГиБ", "ТиБ"];
    let unit = 0;
    while (bytes >= 1024 && unit < units.length - 1) {
        bytes /= 1024;
        unit++;
    }
    return bytes.toLocaleString("ru-RU", { maximumFractionDigits: 2 }) + " " + units[unit];
}
function refreshSelection() {
    const total = games.reduce((sum, game) => sum + (selected.has(game[0]) ? game[3] : 0), 0);
    const free = "Свободно на диске: " + (state?.free ?? "…");
    get("queueSize").textContent = "Объём выбранных: " + size(total) + " · " + free;
    get("gameSize").textContent = (selectedGame ? "Объём игры: " + size(selectedGame[3]) + " · " : "") + free;
    button("downloadQueue").disabled = !selected.size || !!state?.busy;
    button("downloadGame").disabled = !selectedGame || !!state?.busy;
}
function refreshAccount() {
    const account = document.getElementById("accountStatus");
    const login = document.querySelector("#accountLogin");
    if (!account || !login)
        return;
    if (state?.authenticating) {
        account.textContent = "Завершается вход в GOG…";
    }
    else {
        account.textContent = state?.signedIn ? "Токен GOG сохранён" : "Вход ещё не выполнен";
    }
    login.disabled = !!state?.busy;
}
function renderState(next) {
    const old = state;
    state = next;
    if (old && old.queueGeneration !== next.queueGeneration)
        selected.clear();
    button("update").disabled = button("settings").disabled = next.busy;
    button("stop").disabled = !next.busy;
    get("status").textContent = next.status;
    get("catalogStatus").textContent = next.catalogStatus;
    get("queueHint").textContent = next.queue.length
        ? "Обновлений: " + next.queue.length + ". Отметьте игры для загрузки."
        : next.catalogStatus === "Сначала обновите каталог" ? next.catalogStatus : "В очереди нет обновлений";
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
        log.textContent = lastLog = next.log;
        if (follow)
            log.scrollTop = log.scrollHeight;
    }
    if (next.resume && !resumePrompt) {
        resumePrompt = true;
        send("resume", confirm("Предыдущее обновление несовместимо. Сбросить его и продолжить?"));
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
    const names = ["Аккаунт GOG", ...Object.keys(settings.groups)];
    get("tabs").replaceChildren(...names.map(name => {
        const tab = document.createElement("button");
        tab.textContent = name;
        tab.setAttribute("aria-current", String(name === activeTab));
        tab.onclick = () => {
            activeTab = name;
            renderSettings();
            if (name === "Аккаунт GOG")
                send("warmLogin");
        };
        return tab;
    }));
    const form = get("settingsForm");
    form.replaceChildren();
    if (activeTab === "Аккаунт GOG") {
        const account = document.createElement("p");
        account.id = "accountStatus";
        account.setAttribute("role", "status");
        const login = document.createElement("button");
        login.id = "accountLogin";
        login.className = "primary";
        setIconLabel(login, "login", "Войти в GOG");
        login.onclick = () => {
            login.disabled = true;
            setIconLabel(login, "login", "Открывается форма GOG…");
            send("login");
        };
        form.append(account, login);
        refreshAccount();
        if (settings.savedLogin) {
            const forget = document.createElement("button");
            forget.textContent = "Удалить пароль, сохранённый в прежней версии";
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
            row.append(input, field.label);
        }
        else {
            const label = document.createElement("span");
            label.textContent = field.label;
            const editor = field.choices.length ? document.createElement("select") : document.createElement("input");
            if (editor instanceof HTMLSelectElement) {
                for (const [name] of field.choices)
                    editor.add(new Option(name, name));
            }
            editor.value = value;
            editor.oninput = () => { draft[field.key] = editor.value; };
            row.append(label);
            if (field.key === "destination") {
                const path = document.createElement("span");
                path.className = "folder";
                const browse = document.createElement("button");
                setIconLabel(browse, "folder", "Обзор…");
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
    if (event.key !== "Escape")
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
    if (activeTab === "Аккаунт GOG")
        send("warmLogin");
};
button("back").onclick = closeSettings;
button("save").onclick = () => send("settings", draft);
button("update").onclick = () => send("update");
button("openFolder").onclick = () => send("openFolder");
button("stop").onclick = () => { if (confirm("Остановить текущую операцию?"))
    send("stop"); };
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
        document.documentElement.dataset.theme = settings.theme;
        const theme = button("theme");
        const dark = settings.theme === "dark";
        theme.title = dark ? "Светлая тема" : "Тёмная тема";
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
    else if (kind === "authReturned") {
        if (!get("preferences").hidden)
            renderSettings();
    }
    else if (kind === "error") {
        if (!get("preferences").hidden)
            renderSettings();
        alert(String(data));
    }
});
send("ready");
