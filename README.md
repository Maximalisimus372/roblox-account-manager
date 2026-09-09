# Roblox Account Manager

A small Windows desktop tool for keeping several of your own Roblox accounts in
one place and launching them into a game — including several clients at once.

No dependencies: Python 3.9+ with tkinter, which the python.org installer
includes by default.

## Running it

```bash
python -m rbxmanager
```

or double-click `run.bat`.

## How it works

* **Accounts** are stored as their `.ROBLOSECURITY` cookie in
  `%LOCALAPPDATA%\RobloxAccountManager\accounts.json`. Each cookie is encrypted
  with Windows DPAPI, so the file is only readable by your Windows user on this
  machine. Nothing is uploaded anywhere; the only host the manager talks to is
  roblox.com.
* **Launching** follows the same path as the website's Play button: the manager
  asks `auth.roblox.com` for a one-shot authentication ticket with the account's
  cookie, then passes that ticket to `RobloxPlayerBeta.exe` through the
  `roblox-player:` URI. The cookie itself never reaches the client.
* **Several clients**: a starting client waits on `ROBLOX_singletonMutex` in
  its `waitForNewPlayerProcess` check, and once that wait returns it signals
  `ROBLOX_singletonEvent`, which is what makes the client already running shut
  itself down (`SingleSurfaceApp shutDown`, disconnect reason 285). The manager
  therefore creates both objects and, importantly, creates the mutex **owned**
  (`bInitialOwner=True`): an unowned mutex is signalled immediately and the
  check sails straight through. Owned, the wait never returns, and as many
  clients as your PC can handle may run. Unticking the box releases them, and
  so does closing the manager.

  They must exist **before the first client starts**, and they only exist
  while the manager is open — closing it hands the limit straight back to
  Roblox. Because both are easy to get wrong without noticing, the manager
  tracks whether the objects are actually its own: the Clients page says
  "the manager holds the limit" or "Roblox still holds the limit", a launch
  into a limit it does not hold asks first, closing the clients that were
  started too early takes the objects back, and closing the manager while
  several clients run warns that they will not survive the next launch.

## Adding an account

**Log in...** — the normal way. The manager opens a browser window on Roblox's
own login page with a profile directory of its own, you log in there as usual
(password, captcha and 2FA stay between you and Roblox), and as soon as the
session exists the cookie is picked up and the account appears in the list.
Firefox, Chrome, Edge and Brave are supported.

**Create account...** — the same thing pointed at Roblox's sign-up page. You
fill the form in yourself; the manager types nothing and does not touch the
captcha. The new account is added once Roblox signs it in, and the window stays
open so you can finish setting the account up.

**Log in again** — reopens the browser profile belonging to the selected
account, for when its cookie has expired. It refuses to overwrite the account
if you log in as somebody else.

**Paste cookie...** — the manual fallback: `F12` → Application/Storage →
Cookies → `https://www.roblox.com` → `.ROBLOSECURITY`, paste the value.

Every route validates the cookie against `users.roblox.com` before saving, so a
truncated paste or a dead session is caught right away.

### Why a browser profile per account

Browsers keep one Roblox session per profile, so logging into a second account
in your everyday window signs the first one out — and invalidates the cookie
the manager saved for it. Each login therefore gets its own profile under
`%LOCALAPPDATA%\RobloxAccountManager\profiles\`, which is also what makes
"Log in again" possible later. Those profiles hold live logins: they are as
worth protecting as the account list itself.

### How the cookie is read

* Firefox stores cookie values in plain text, so its `cookies.sqlite` is copied
  and queried with sqlite3.
* Chrome, Edge and Brave encrypt theirs, so instead of decrypting anything the
  browser is started with `--remote-debugging-port` on that same private
  profile and asked for the cookie over the DevTools protocol
  (`Storage.getCookies`).

Neither path touches your everyday browser profile.

Waiting for the login does not watch the process that was started: Firefox
hands over to another process and exits within a second of being launched,
which used to look exactly like "the window was closed" and threw the finished
login away. The wait now goes by the file each browser keeps while a profile is
in use (`parent.lock`, `DevToolsActivePort`), confirms a lock left behind by a
killed browser against the process list, and takes one last look for the cookie
before giving up.

## Launching

* Put the **place ID** — the number in `roblox.com/games/<place id>/...` — into
  the Place ID box, or just paste the game's link: the ID is pulled out of it,
  and a private-server link fills the code field in and ticks the box too.
* Select one or more accounts and press **Launch selected** (or double-click a
  row).
* **Job ID / private-server code** is optional: paste a server's job ID to
  join that exact server, or tick *it is a private-server code* and paste the
  `privateServerLinkCode` value from a private-server link. Either way every
  selected account joins that same server.
* **each account in its own server** does the opposite: the manager asks
  `games.roblox.com` for the place's public servers and hands a different job
  ID to each account. Servers already used are remembered for the session, so
  launching the accounts one at a time spreads them out too. The endpoint
  answers 429 to anything but occasional calls, so the list is cached for two
  minutes; when there are fewer free servers than accounts, the rest join
  wherever Roblox puts them and the status line says so.
* **Delay between launches** spaces out the launches; Roblox rate-limits the
  ticket endpoint if you hammer it, and each client needs a moment to start.
  6 seconds is a sane default.

## Around the window

* The window is a sidebar of four pages — Accounts, Clients, Settings, About —
  with the work on cards inside each one.
* Buttons, sidebar items, cards, checkboxes and the radio pills are drawn on
  canvases in `rbxmanager/widgets.py`, because ttk has no rounded corners, no
  gradients and no say over how a checkbox looks. Everything else ttk still
  draws — the table, the scrollbars, the text inputs — is styled from the same
  palette in `rbxmanager/theme.py`.
* Dark by default; Settings → Appearance (or the button at the bottom of the
  sidebar) switches to light, and the choice is remembered. Switching rebuilds
  the window, which is why the widgets take their colours as an argument. The
  Windows title bar follows the theme too.
* Text sharpness: every label drawn on a canvas is placed on a whole pixel
  (`widgets.snap`) — Tk anti-aliases around fractional coordinates, which
  smears a glyph over about half again as many pixels and reads as blurry next
  to the same text in a Label. The process also declares itself
  per-monitor dpi-aware, so Windows does not stretch the window on a scaled
  display, and every pixel size goes through `widgets.px` to follow that
  scaling.
* Click a column heading to sort by it; click again to reverse. The **Filter**
  box narrows the list by nickname, username or user ID.
* Right-click a row for the same actions as the button row under the table.
  Buttons that need a selection stay greyed out until you make one.
* Keys: `Enter` launches the selected accounts, `F5` refreshes them, `Delete`
  removes them, `Ctrl+A` selects all, `Ctrl+N` starts a login.
* Right-click any text field for Paste/Copy/Cut. `Ctrl+V` also works on a
  Cyrillic keyboard layout: Tk matches those shortcuts on the letter it
  receives, which is `м` and not `v` there, so the Cyrillic keysyms are added
  to Tk's own `<<Paste>>`, `<<Copy>>`, `<<Cut>>` and `<<SelectAll>>` events —
  the same single handler, so nothing gets pasted twice on a Latin layout.
* Window size, sort order, place ID, job ID and delay are remembered in
  `settings.json` next to the account list.

## Notes and limits

* Cookies expire, and Roblox invalidates them when the account signs in from a
  browser again or changes its password. When a row shows a status other than
  `ok`, use **Log in again**.
* No password handling, no 2FA handling and no captcha solving — the login
  happens in a real browser window, by design. The manager only reads the
  cookie the browser was given afterwards.
* Robux balance is shown for information only and refreshes on **Refresh**.
* Alt accounts are allowed on Roblox, but automating them (bots, farming,
  botting a game's economy) is not. This is a launcher; what the accounts do
  afterwards is on you.
* Anything that reads a cookie is worth being careful with: keep
  `accounts.json` off shared drives and out of backups you do not control.

## Layout

| File | What it does |
| --- | --- |
| `rbxmanager/api.py` | Roblox web API: cookie validation, CSRF, auth ticket, launch URI |
| `rbxmanager/launcher.py` | Finding the client, the singleton mutex, starting/killing clients |
| `rbxmanager/storage.py` | The account list on disk |
| `rbxmanager/browser_login.py` | Login/sign-up windows and reading the cookie back |
| `rbxmanager/crypto.py` | DPAPI encryption of the cookies |
| `rbxmanager/gui.py` | The window: sidebar, pages, cards |
| `rbxmanager/widgets.py` | The rounded canvas-drawn buttons, cards and inputs |
| `rbxmanager/theme.py` | The palettes, and the ttk styling |
