"""Two-language text: English and Russian.

The code is written with English strings, and each user-facing one is wrapped
in `tr(...)`. `tr` returns the string unchanged in English mode, or its Russian
counterpart from the table below in Russian mode. A string with no entry falls
back to the English text, so a missing translation shows through rather than
crashing.

Format strings keep their %-placeholders: translate the words around them and
leave the placeholders in the same order, e.g. tr("Launched %d account(s)").
"""

_lang = "en"


def set_language(lang):
    global _lang
    _lang = "ru" if lang == "ru" else "en"


def current():
    return _lang


def tr(text):
    if _lang == "en":
        return text
    return _RU.get(text, text)


_RU = {
    # window / titles
    "Roblox Account Manager": "Менеджер аккаунтов Roblox",
    "Ready": "Готово",

    # pages: labels and hints
    "Accounts": "Аккаунты",
    "Every account you have added": "Все добавленные аккаунты",
    "Clients": "Клиенты",
    "How many Roblox windows may run": "Сколько окон Roblox можно запускать",
    "Settings": "Настройки",
    "Look, login browser and data": "Оформление, браузер входа, данные",
    "About": "О программе",
    "What this does, and where it keeps things": "Как работает и где хранит данные",

    # accounts toolbar
    "Log in": "Войти",
    "Create account": "Создать аккаунт",
    "Paste cookie": "Вставить cookie",
    "Filter": "Поиск",
    "No accounts yet — press “Log in” to add one":
        "Аккаунтов пока нет — нажмите «Войти», чтобы добавить",
    "Nothing matches this filter": "Ничего не найдено",

    # column titles
    "ACCOUNT": "АККАУНТ",
    "USER ID": "USER ID",
    "ROBUX": "ROBUX",
    "LAST LAUNCHED": "ЗАПУЩЕН",
    "STATUS": "СТАТУС",

    # account action buttons
    "Refresh": "Обновить",
    "Log in again": "Войти заново",
    "Rename": "Переименовать",
    "Rename…": "Переименовать…",
    "Profile": "Профиль",
    "Open profile": "Профиль",
    "Copy cookie": "Копировать cookie",
    "Remove": "Удалить",
    "Launch": "Запустить",

    # launch card
    "Place ID or game link": "Place ID или ссылка на игру",
    "Job ID / private-server code": "Job ID / код приватного сервера",
    "Launch selected": "Запустить выбранные",
    "it is a private-server code": "это код приватного сервера",
    "each account in its own server": "каждый аккаунт на своём сервере",
    "Select an account to launch it": "Выберите аккаунт для запуска",
    "%d accounts selected — they start one after another":
        "выбрано аккаунтов: %d — запустятся по очереди",

    # subtitles
    "No accounts yet": "Аккаунтов пока нет",
    "%d of %d accounts": "%d из %d аккаунтов",
    "%d account": "аккаунтов: %d",
    "%d accounts": "аккаунтов: %d",

    # status bar
    "%d Roblox client(s) running  ·  %s": "запущено клиентов Roblox: %d  ·  %s",
    "one client at a time": "по одному клиенту",
    "several allowed — the manager holds the limit":
        "несколько разрешено — лимит держит менеджер",
    "several NOT allowed yet — Roblox still holds the limit":
        "ещё НЕ разрешено — лимит держит Roblox",

    # theme footer + settings
    "☀  Light theme": "☀  Светлая тема",
    "☾  Dark theme": "☾  Тёмная тема",
    "Switched to the %s theme": "Тема переключена",
    "Appearance": "Оформление",
    "Dark": "Тёмная",
    "Light": "Светлая",
    "Language": "Язык",
    "Login browser": "Браузер для входа",
    "Ask each time": "Спрашивать каждый раз",
    "Data": "Данные",
    "Open data folder": "Открыть папку данных",
    "Open browser profiles": "Открыть профили браузера",

    # clients page
    "Several clients at once": "Несколько клиентов сразу",
    "Allow several clients at once": "Разрешить несколько клиентов сразу",
    "Close all clients": "Закрыть все клиенты",
    "Delay between launches": "Задержка между запусками",
    "seconds": "секунд",
    ("A starting Roblox client waits on a named mutex to find out whether "
     "another one is already running, and then tells it to quit. While this "
     "is on, the manager owns that mutex, so the wait never finishes and as "
     "many clients as your PC can handle may run. It is released when the "
     "manager closes.\n\nIt has to be switched on before the first client "
     "starts."):
        ("Запускаемый клиент Roblox ждёт именованный мьютекс, чтобы понять, "
         "запущен ли уже другой, и тогда велит ему закрыться. Пока это "
         "включено, мьютексом владеет менеджер, ожидание не завершается, и "
         "можно запустить столько клиентов, сколько потянет ПК. Он "
         "освобождается при закрытии менеджера.\n\nВключать нужно до запуска "
         "первого клиента."),
    ("Roblox rate-limits the ticket endpoint if launches are hammered, and "
     "each client needs a moment to start."):
        ("Roblox ограничивает частоту запросов тикетов, а каждому клиенту "
         "нужно время на запуск, поэтому не спешите."),

    # about page
    ("Accounts are kept as their .ROBLOSECURITY cookie, encrypted with "
     "Windows DPAPI, so the file is readable only by your Windows user on "
     "this machine. Nothing is uploaded anywhere; the only host the manager "
     "talks to is roblox.com.\n\n"
     "Logging in opens Roblox's own login page in a browser profile of its "
     "own — password, captcha and 2FA stay between you and Roblox — and the "
     "cookie is read out of that profile afterwards.\n\n"
     "Launching follows the same path as the website's Play button: a "
     "one-shot authentication ticket is fetched with the cookie and handed "
     "to RobloxPlayerBeta.exe, which never sees the cookie itself.\n\n"
     "Alt accounts are allowed on Roblox; automating them is not. This is a "
     "launcher — what the accounts do afterwards is on you."):
        ("Аккаунты хранятся как их cookie .ROBLOSECURITY, зашифрованные через "
         "Windows DPAPI, поэтому файл читается только вашей учётной записью "
         "Windows на этом ПК. Ничего никуда не загружается; единственный "
         "адрес, с которым работает менеджер — roblox.com.\n\n"
         "Вход открывает настоящую страницу входа Roblox в отдельном профиле "
         "браузера — пароль, капча и 2FA остаются между вами и Roblox — а "
         "cookie считывается из этого профиля потом.\n\n"
         "Запуск идёт тем же путём, что кнопка Play на сайте: одноразовый "
         "тикет получается по cookie и передаётся в RobloxPlayerBeta.exe, "
         "который саму cookie никогда не видит.\n\n"
         "Альт-аккаунты в Roblox разрешены; автоматизация — нет. Это лаунчер — "
         "что аккаунты делают дальше, на вашей ответственности."),

    # dialogs — cookie
    "Paste a cookie": "Вставить cookie",
    "Paste a cookie first.": "Сначала вставьте cookie.",
    "Nickname (optional)": "Имя (необязательно)",
    "Save": "Сохранить",
    "Cancel": "Отмена",
    ("Where to get the cookie:\n\n"
     "1. Log into the account in a browser (a separate browser profile per "
     "account, otherwise logging in again invalidates the previous session)."
     "\n"
     "2. F12 -> Application (Storage) -> Cookies -> https://www.roblox.com\n"
     "3. Copy the whole value of .ROBLOSECURITY and paste it below.\n\n"
     "Anyone holding that value is logged into the account, so the manager "
     "stores it encrypted with your Windows account and never sends it "
     "anywhere except roblox.com."):
        ("Где взять cookie:\n\n"
         "1. Войдите в аккаунт в браузере (отдельный профиль браузера на "
         "каждый аккаунт, иначе повторный вход обнулит прошлую сессию).\n"
         "2. F12 -> Application (Storage) -> Cookies -> "
         "https://www.roblox.com\n"
         "3. Скопируйте всё значение .ROBLOSECURITY и вставьте ниже.\n\n"
         "Любой, у кого есть это значение, залогинен в аккаунт, поэтому "
         "менеджер хранит его зашифрованным под вашей учётной записью Windows "
         "и никуда не отправляет, кроме roblox.com."),

    # dialogs — login
    "Open the Roblox login page in": "Открыть страницу входа Roblox в браузере",
    "Open": "Открыть",
    "Waiting for Roblox": "Ожидание Roblox",

    # login flow
    "No supported browser was found.\n\nFirefox, Chrome, Edge or Brave is "
    "needed to log in from here. Install one of them, or use 'Paste cookie' "
    "instead.":
        "Поддерживаемый браузер не найден.\n\nДля входа отсюда нужен Firefox, "
        "Chrome, Edge или Brave. Установите один из них или используйте "
        "«Вставить cookie».",
    ("This opens Roblox's own sign-up page in a fresh browser profile. You "
     "fill the form in yourself — the manager does not type anything and does "
     "not touch the captcha.\n\n"
     "As soon as the new account is signed in, it is added to the list. "
     "Roblox allows alt accounts, but creating them in bulk or using them for "
     "botting is against its rules.\n\nContinue?"):
        ("Откроется настоящая страница регистрации Roblox в новом профиле "
         "браузера. Форму заполняете вы сами — менеджер ничего не вводит и не "
         "трогает капчу.\n\n"
         "Как только новый аккаунт войдёт, он добавится в список. Roblox "
         "разрешает альты, но массовое создание или ботоводство — против "
         "правил.\n\nПродолжить?"),
    "Log in to Roblox in the browser window.":
        "Войдите в Roblox в окне браузера.",
    "Create the account in the browser window.":
        "Создайте аккаунт в окне браузера.",
    "Log in as %s in the browser window.":
        "Войдите как %s в окне браузера.",
    "%s\n\nThe account is added by itself once Roblox signs you in.":
        "%s\n\nАккаунт добавится сам, как только Roblox выполнит вход.",
    "Waiting for the login in %s…": "Ожидание входа в %s…",
    "Login %s": "Вход %s",
    "cancelled": "отменён",
    "the browser was closed before the login finished":
        "браузер закрыли до завершения входа",
    "Could not start %s: %s": "Не удалось запустить %s: %s",
    "Captured a cookie but Roblox rejected it: %s":
        "Cookie получена, но Roblox её отклонил: %s",
    "You logged in as %s, but %s was selected.":
        "Вы вошли как %s, а выбран был %s.",
    "Signed in as %s": "Выполнен вход: %s",

    # add / refresh / rename / copy / remove
    "Checking cookie…": "Проверка cookie…",
    "Could not add the account: %s": "Не удалось добавить аккаунт: %s",
    "Added %s": "Добавлен %s",
    "Checking %d account(s)…": "Проверка аккаунтов: %d…",
    "Checked %d account(s)": "Проверено аккаунтов: %d",
    "Select exactly one account.": "Выберите ровно один аккаунт.",
    "Rename": "Переименовать",
    "Nickname for %s:": "Имя для %s:",
    "Copy cookie": "Копировать cookie",
    "This cookie is a full login to %s. Put it on the clipboard?":
        "Эта cookie — полный доступ к %s. Скопировать в буфер обмена?",
    "Cookie for %s copied to the clipboard":
        "Cookie для %s скопирована в буфер",
    "Remove %s from the manager?\n(The Roblox account itself is untouched.)":
        "Удалить %s из менеджера?\n(Сам аккаунт Roblox не затрагивается.)",
    "Removed %s": "Удалён %s",
    "Private-server link recognised": "Ссылка на приватный сервер распознана",

    # several-clients
    "Several clients": "Несколько клиентов",
    "Several clients allowed while the manager stays open":
        "Несколько клиентов разрешены, пока менеджер открыт",
    "Back to one client at a time": "Снова по одному клиенту",
    ("Roblox was already running when this was switched on, and that client "
     "still holds the one-client limit itself — so the next launch would "
     "close it.\n\n"
     "The manager is holding the limit open now, so closing the clients that "
     "are open and launching them again from here is all it takes.\n\n"
     "Close the running client(s) now?"):
        ("Roblox уже был запущен на момент включения, и тот клиент сам держит "
         "лимит одного клиента — поэтому следующий запуск закроет его.\n\n"
         "Сейчас лимит держит менеджер, поэтому достаточно закрыть открытые "
         "клиенты и запустить их заново отсюда.\n\n"
         "Закрыть запущенные клиенты сейчас?"),
    "Closed %d client(s) — the manager holds the limit now, launch again "
    "from here":
        "Закрыто клиентов: %d — лимит теперь у менеджера, запускайте заново "
        "отсюда",
    "Closed %d client(s), but the limit is still held elsewhere":
        "Закрыто клиентов: %d, но лимит всё ещё держит другой процесс",
    "Closed %d client(s)": "Закрыто клиентов: %d",

    # launch validation
    "Select at least one account.": "Выберите хотя бы один аккаунт.",
    ("Enter the place ID, or paste the game's link and let the manager pick "
     "the ID out of it.\n\n"
     "The place ID is the number in roblox.com/games/<place id>/..."):
        ("Введите Place ID или вставьте ссылку на игру, и менеджер сам "
         "возьмёт из неё ID.\n\n"
         "Place ID — это число в roblox.com/games/<place id>/..."),
    ("Several accounts are selected but only one client at a time is "
     "allowed, so each launch would replace the previous one.\n\nAllow "
     "several clients?"):
        ("Выбрано несколько аккаунтов, но разрешён только один клиент, "
         "поэтому каждый запуск будет закрывать предыдущий.\n\nРазрешить "
         "несколько клиентов?"),
    ("The one-client limit is not held by the manager right now, so this "
     "launch would close the client that is already open.\n\n"
     "That happens when Roblox was started before the manager, or the "
     "manager was closed in between.\n\nLaunch anyway?"):
        ("Лимит одного клиента сейчас держит не менеджер, поэтому этот запуск "
         "закроет уже открытый клиент.\n\n"
         "Так бывает, если Roblox запустили раньше менеджера или менеджер "
         "закрывали.\n\nВсё равно запустить?"),
    "Could not list servers (%s) — letting Roblox choose":
        "Не удалось получить список серверов (%s) — выбор за Roblox",
    "Only %d free server(s) found — the rest join wherever Roblox puts them":
        "Найдено свободных серверов: %d — остальные зайдут куда решит Roblox",
    "Launching %s… (%d of %d)": "Запуск %s… (%d из %d)",
    "Launched %d account(s)": "Запущено аккаунтов: %d",

    # on close
    "Close the manager?": "Закрыть менеджер?",
    ("The manager is what holds the one-client limit open. Closing it hands "
     "the limit back to Roblox: the windows that are open stay open, but the "
     "next client to start will close them.\n\nClose anyway?"):
        ("Именно менеджер держит лимит одного клиента открытым. При закрытии "
         "лимит вернётся к Roblox: открытые окна останутся, но следующий "
         "запуск клиента закроет их.\n\nВсё равно закрыть?"),

    # context menu / entry menu
    "Paste": "Вставить",
    "Copy": "Копировать",
    "Cut": "Вырезать",
    "Select all": "Выделить всё",
}
