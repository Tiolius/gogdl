# GOGDL

## English

GOGDL is a Windows app for updating your GOG catalog and downloading games you own.

1. Install Python 3.11 or newer and the Microsoft Edge WebView2 Runtime.
2. Run `Setup-GOGDL.cmd`, then `Start-GOGDL.cmd`.
3. Sign in via **Settings → GOG account → Sign in with browser**. GOGDL opens Chrome if installed, otherwise your default browser. GOGDL saves the token after sign-in. You can also enter an access token manually in account settings. Then click **Refresh catalog**.
4. Select games in the update queue or find a game by title or ID. Set the download folder in **Settings → Downloads**.

Click **EN** or **RU** in the toolbar to switch languages. Use **Settings → Version → Update** to update GOGDL and restart it. If the update changes Python dependencies, run `Setup-GOGDL.cmd` again.

## Русский

GOGDL — приложение для Windows, которое обновляет каталог GOG и скачивает купленные игры.

1. Установите Python 3.11 или новее и Microsoft Edge WebView2 Runtime.
2. Запустите `Setup-GOGDL.cmd`, затем `Start-GOGDL.cmd`.
3. Войдите через **Настройки → Аккаунт GOG → Войти через браузер**. GOGDL откроет Chrome, если он установлен, или браузер по умолчанию. После входа GOGDL сохранит токен. Его также можно указать вручную во вкладке аккаунта. Затем нажмите **Обновить каталог**.
4. Отметьте игры в очереди обновлений или найдите игру по названию либо ID. Папку загрузки можно выбрать в **Настройки → Загрузка**.

Язык меняется кнопкой **EN** или **RU** в верхней панели. Кнопка **Настройки → Версия → Обновить** обновляет GOGDL и перезапускает приложение. Если изменились зависимости Python, снова запустите `Setup-GOGDL.cmd`.

## License

Includes a modified version of [gogrepoc](https://github.com/Kalanyr/gogrepoc) under [GPL-3.0-or-later](LICENSE-gogrepoc.txt).
