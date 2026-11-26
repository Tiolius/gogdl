# GOGDL

[English](#english) · [Русский](#русский)

## English

GOGDL is a Windows app for updating a local GOG catalog and downloading games you own. It uses a Python backend, a TypeScript interface and Microsoft Edge WebView2.

1. Install Python 3.11 or newer and the Microsoft Edge WebView2 Runtime if they are missing.
2. Run `Setup-GOGDL.cmd` once to install dependencies, then open `Start-GOGDL.cmd`.
3. Open **Настройки → Аккаунт GOG → Войти в GOG** for the official sign-in form, then click **Обновить каталог** to update the catalog. Use the update queue or the catalog search to choose games to download.

The catalog, access token, settings, WebView2 profile, logs and downloads are stored locally and ignored by Git. Never upload these files. Download settings include platform and language filters, installer type, images, and the destination folder.

The compiled JavaScript is included in `assets`. To rebuild it after editing TypeScript, run `npx --yes --package typescript@5.9.3 tsc -p ui`. Node.js is only needed to rebuild the interface.

The included [gogrepoc](https://github.com/Kalanyr/gogrepoc) is a modified copy distributed under GPL-3.0-or-later. See `LICENSE-gogrepoc.txt`. Font and icon licenses are in `assets`.

## Русский

На Windows нужны Python 3.11 или новее и среда выполнения Microsoft Edge WebView2. На новой установке один раз запустите `Setup-GOGDL.cmd`, затем откройте `Start-GOGDL.cmd`. Интерфейс на TypeScript и HTML/CSS открывается в окне WebView2. Python запускает локальный `gogrepoc.py`. Каталог, токен, журнал и загрузки по умолчанию сохраняются в папке `Gogdl App`.

1. Откройте **⚙ Настройки → Аккаунт GOG → Войти в GOG**. Форма GOG начинает загружаться в фоне при открытии вкладки аккаунта. Введите данные и пройдите проверку Cloudflare. Если проверка задерживается, нажмите **Перезагрузить форму**. После подтверждения приложение вернётся к каталогу и сохранит токен. Кнопка **Вернуться в GOGDL** отменяет вход до завершения формы.
2. **Обновить каталог** запускает проверку с параметрами вкладки **Каталог**. По умолчанию проверяются новые и обновлённые игры для Windows и языков `en ru`.
3. После проверки в списке появятся игры, которые GOG отметил как обновлённые и которые успешно записаны в каталог. Отметьте нужные игры и нажмите **Скачать выбранные**. Загрузка идёт по порядку списка. При ошибке очередь останавливается, оставшиеся игры можно запустить повторно.
4. В блоке **Одна игра из каталога** введите название или ID прямо в раскрывающееся поле. Выберите игру из подсказок и нажмите **Скачать игру**.

## Настройки

Настройки открываются в главном окне. Кнопка **Сохранить** записывает параметры в `gogdl-settings.json` рядом с приложением. При закрытии приложения там же сохраняются положение, размер и состояние главного окна.

- **Каталог** — режим обновления, продолжение прерванной проверки, тип установщиков, фильтры ОС, языков и игр, скрытые игры, списки изменений, параметры MD5 и задержка.
- **Загрузка** — папка, включение и исключение ОС и языков, исключения игр и файлов, типы установщиков, дополнительные материалы, обложки, фоны, предварительное выделение места, задержка и лимит объёма. Пути с пробелами поддерживаются. Для списков ОС, языков и игр используйте пробелы. Шаблоны файлов разделяйте точкой с запятой.
- **Журнал** — запись в `gogrepo.log` и отладочные сообщения.

Параметры загрузки применяются и к очереди, и к отдельной игре. Задержка и лимит рассчитываются на каждую игру. Если игра не помещается в заданный лимит, очередь приостанавливается. Оценка объёма учитывает фильтры и известные размеры файлов в манифесте. Она не вычитает уже скачанные файлы и не учитывает обложки и фоны.

Поля пароля принадлежат официальной форме GOG. GOGDL не читает введённые на ней логин, пароль или код подтверждения. Если WebView2 запомнил данные, они находятся в его профиле `.gogdl-profile\EBWebView\Default`. Старый зашифрованный пароль из версии Tkinter хранится в поле `saved_login` файла `gogdl-settings.json` и удаляется кнопкой во вкладке **Аккаунт GOG**. Токен доступа самого скрипта хранится отдельно в `gog-token.dat`.

Список обновлений формируется при каждой проверке в открытом окне. Журнал показывает результат входа и вывод обновления и загрузки. Кнопка **Остановить** прерывает текущий процесс сразу. Для продолжения загрузки используйте ту же папку, чтобы скрипт мог найти частичные файлы.

Оформление использует Inter, JetBrains Mono и Material Symbols Outlined. Значки загружаются из `assets/material`, лицензии находятся в `assets`.

## Сборка интерфейса

Готовый JavaScript входит в папку `assets`. Для изменения TypeScript соберите его командой `npx --yes --package typescript@5.9.3 tsc -p ui`. Node.js при обычном запуске не нужен.

В репозитории находится изменённая версия [gogrepoc](https://github.com/Kalanyr/gogrepoc) под лицензией GPL-3.0-or-later. Текст лицензии — в `LICENSE-gogrepoc.txt`. Каталог, токен, настройки, профиль WebView2, журналы и загрузки остаются локально и исключены из Git.
