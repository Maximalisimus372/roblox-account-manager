"""The window: a sidebar of pages, and cards inside each one."""

import os
import queue
import re
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
import webbrowser
from tkinter import messagebox, simpledialog, ttk

from . import api, browser_login, launcher, theme, widgets
from . import i18n
from .i18n import tr
from .storage import Account, Store, data_dir, load_settings, save_settings

COOKIE_HELP = (
    "Where to get the cookie:\n\n"
    "1. Log into the account in a browser (a separate browser profile per "
    "account, otherwise logging in again invalidates the previous session).\n"
    "2. F12 -> Application (Storage) -> Cookies -> https://www.roblox.com\n"
    "3. Copy the whole value of .ROBLOSECURITY and paste it below.\n\n"
    "Anyone holding that value is logged into the account, so the manager "
    "stores it encrypted with your Windows account and never sends it "
    "anywhere except roblox.com.")

EMPTY_HINT = "No accounts yet — press “Log in” to add one"

PLACE_IN_URL = re.compile(r"roblox\.com/games/(\d+)", re.I)
PRIVATE_CODE_IN_URL = re.compile(r"privateServerLinkCode=([A-Za-z0-9_-]+)", re.I)

PAGES = (("accounts", "👤", "Accounts", "Every account you have added"),
         ("clients", "🎮", "Clients", "How many Roblox windows may run"),
         ("settings", "⚙️", "Settings", "Look, login browser and data"),
         ("about", "💡", "About", "What this does, and where it keeps things"))


# ------------------------------------------------------------------ dialogs

class Dialog(tk.Toplevel):
    """Shared look for the small windows: palette colours, centred, Escape."""

    def __init__(self, master, title, fonts):
        super().__init__(master)
        self.colours = theme.current()
        self.fonts = fonts
        self.title(title)
        self.resizable(False, False)
        self.transient(master)
        self.configure(background=self.colours["bg"])
        self.body = tk.Frame(self, background=self.colours["bg"],
                             padx=22, pady=20)
        self.body.pack(fill="both", expand=True)
        self.bind("<Escape>", lambda _event: self.destroy())

    def heading(self, text):
        tk.Label(self.body, text=text, font=self.fonts["section"],
                 background=self.colours["bg"],
                 foreground=self.colours["text"]).pack(anchor="w", pady=(0, 10))

    def paragraph(self, text, width=470):
        tk.Message(self.body, text=text, width=width, justify="left",
                   font=self.fonts["base"], background=self.colours["bg"],
                   foreground=self.colours["muted"]).pack(anchor="w",
                                                          pady=(0, 14))

    def centre(self):
        self.update_idletasks()
        try:
            x = (self.master.winfo_rootx()
                 + (self.master.winfo_width() - self.winfo_width()) // 2)
            y = (self.master.winfo_rooty()
                 + (self.master.winfo_height() - self.winfo_height()) // 3)
            self.geometry("+%d+%d" % (max(x, 0), max(y, 0)))
        except tk.TclError:
            pass


class AddAccountDialog(Dialog):
    """Ask for a cookie, and an optional nickname."""

    def __init__(self, master, fonts):
        super().__init__(master, tr("Paste a cookie"), fonts)
        self.result = None
        colours = self.colours

        self.heading(tr("Paste a cookie"))
        self.paragraph(tr(COOKIE_HELP))

        self.cookie = tk.Text(self.body, width=62, height=5, wrap="char",
                              font=fonts["base"],
                              background=colours["field"],
                              foreground=colours["text"],
                              insertbackground=colours["text"],
                              relief="flat", padx=10, pady=8,
                              highlightthickness=1,
                              highlightbackground=colours["border"],
                              highlightcolor=colours["accent"])
        self.cookie.pack(fill="x", pady=(0, 12))

        row = tk.Frame(self.body, background=colours["bg"])
        row.pack(fill="x")
        tk.Label(row, text=tr("Nickname (optional)"), font=fonts["base"],
                 background=colours["bg"],
                 foreground=colours["muted"]).pack(side="left")
        self.alias = ttk.Entry(row, width=26, font=fonts["base"])
        self.alias.pack(side="left", padx=(10, 0))

        buttons = tk.Frame(self.body, background=colours["bg"])
        buttons.pack(fill="x", pady=(18, 0))
        widgets.Button(buttons, colours, tr("Save"), self._accept, kind="primary",
                       font=fonts["bold"],
                       background=colours["bg"]).pack(side="right")
        widgets.Button(buttons, colours, tr("Cancel"), self.destroy, kind="ghost",
                       font=fonts["base"],
                       background=colours["bg"]).pack(side="right", padx=(0, 8))

        self.cookie.focus_set()
        self.centre()
        self.grab_set()
        self.wait_window(self)

    def _accept(self):
        cookie = api.clean_cookie(self.cookie.get("1.0", "end"))
        if not cookie:
            messagebox.showwarning(tr("Paste a cookie"), tr("Paste a cookie first."),
                                   parent=self)
            return
        self.result = (cookie, self.alias.get().strip())
        self.destroy()


class BrowserChooser(Dialog):
    """Which of the installed browsers to log in with."""

    def __init__(self, master, fonts, browsers):
        super().__init__(master, tr("Log in"), fonts)
        self.result = None
        self._browsers = browsers
        colours = self.colours

        self.heading(tr("Open the Roblox login page in"))
        self._choice = tk.StringVar(value=browsers[0].name)
        for browser in browsers:
            widgets.RadioPill(self.body, colours, browser.name, self._choice,
                              browser.name, font=fonts["base"],
                              background=colours["bg"]).pack(anchor="w", pady=3)

        buttons = tk.Frame(self.body, background=colours["bg"])
        buttons.pack(fill="x", pady=(18, 0))
        widgets.Button(buttons, colours, tr("Open"), self._accept, kind="primary",
                       font=fonts["bold"],
                       background=colours["bg"]).pack(side="right")
        widgets.Button(buttons, colours, tr("Cancel"), self.destroy, kind="ghost",
                       font=fonts["base"],
                       background=colours["bg"]).pack(side="right", padx=(0, 8))
        self.centre()
        self.grab_set()
        self.wait_window(self)

    def _accept(self):
        self.result = next(b for b in self._browsers
                           if b.name == self._choice.get())
        self.destroy()


class WaitDialog(Dialog):
    """Shown while a browser window is open and being watched for a login."""

    def __init__(self, master, fonts, text, cancel_event):
        super().__init__(master, tr("Waiting for Roblox"), fonts)
        self._cancel = cancel_event

        self.heading(tr("Waiting for Roblox"))
        self.paragraph(text, width=400)
        bar = ttk.Progressbar(self.body, mode="indeterminate", length=400)
        bar.pack(fill="x", pady=(0, 16))
        bar.start(60)
        widgets.Button(self.body, self.colours, tr("Cancel"), self._on_cancel,
                       kind="ghost", font=fonts["base"],
                       background=self.colours["bg"]).pack(anchor="e")
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self.centre()

    def _on_cancel(self):
        self._cancel.set()
        self.close()

    def close(self):
        try:
            self.destroy()
        except tk.TclError:
            pass


# ---------------------------------------------------------------- main window

class App(tk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self.store = Store()
        self.settings = load_settings()
        self.events = queue.Queue()
        self._sort = (self.settings.get("sort_column", "account"),
                      bool(self.settings.get("sort_reverse", False)))
        self._client_count = 0
        self._wait = None
        self._edit_target = None
        self._launching = False
        self._launched_ids = set()

        family = ("Segoe UI" if "Segoe UI" in tkfont.families(master)
                  else tkfont.nametofont("TkDefaultFont").cget("family"))
        self.fonts = {
            "base": tkfont.Font(family=family, size=11),
            "bold": tkfont.Font(family=family, size=11, weight="bold"),
            "small": tkfont.Font(family=family, size=10),
            "section": tkfont.Font(family=family, size=12, weight="bold"),
            "title": tkfont.Font(family=family, size=19, weight="bold"),
            "brand": tkfont.Font(family=family, size=14, weight="bold"),
            "icon": tkfont.Font(
                family=("Segoe UI Emoji" if "Segoe UI Emoji"
                        in tkfont.families(master) else family), size=12),
        }

        i18n.set_language(self.settings.get("lang", "en"))
        self.lang = tk.StringVar(value=i18n.current())
        self.theme_name = tk.StringVar(value=self.settings.get("theme", "dark"))
        self.place_id = tk.StringVar(value=str(self.settings.get("place_id", "")))
        self.job_id = tk.StringVar(value=str(self.settings.get("job_id", "")))
        self.private = tk.BooleanVar(value=bool(self.settings.get("private")))
        self.separate = tk.BooleanVar(
            value=bool(self.settings.get("separate_servers")))
        self._used_jobs = set()   # servers handed out this session
        self.delay = tk.StringVar(value=str(self.settings.get("delay", 6)))
        self.filter_text = tk.StringVar()
        self.multi = tk.BooleanVar(value=False)
        self.browser_choice = tk.StringVar(
            value=self.settings.get("browser", "Ask each time"))
        self.status = tk.StringVar(value=tr("Ready"))
        self.clients = tk.StringVar(value="")
        self.subtitle = tk.StringVar(value="")
        self.page = self.settings.get("page", "accounts")

        self.colours = theme.apply(master, self.theme_name.get(), self.fonts)
        self.configure(background=self.colours["bg"])
        self.pack(fill="both", expand=True)

        self.filter_text.trace_add("write", lambda *_a: self.refresh_table())
        self.place_id.trace_add("write", lambda *_a: self._absorb_link())

        self._restore_geometry()
        self._title_bar_theme()
        self._build()
        self.refresh_table()
        self.after(120, self._drain_events)
        self.after(300, self._tick_client_count)

    # ----------------------------------------------------------------- shell

    def _title_bar_theme(self):
        """Ask Windows to draw the title bar dark, so it matches the window."""
        if os.name != "nt":
            return
        try:
            import ctypes
            self.master.update_idletasks()
            handle = ctypes.windll.user32.GetAncestor(
                self.master.winfo_id(), 2)  # GA_ROOT
            dark = ctypes.c_int(1 if self.colours["name"] == "dark" else 0)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                handle, 20, ctypes.byref(dark), ctypes.sizeof(dark))
        except (OSError, AttributeError):
            pass  # older Windows, or no dwmapi

    def _restore_geometry(self):
        self.master.title(tr("Roblox Account Manager"))
        self.master.minsize(widgets.px(1020), widgets.px(640))
        default = "%dx%d" % (widgets.px(1140), widgets.px(720))
        try:
            self.master.geometry(self.settings.get("geometry") or default)
        except tk.TclError:
            self.master.geometry(default)

    def _build(self):
        colours = self.colours
        self.configure(background=colours["bg"])

        self.sidebar = tk.Frame(self, background=colours["sidebar"],
                                width=widgets.px(214))
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)
        self._build_sidebar()

        right = tk.Frame(self, background=colours["bg"])
        right.pack(side="left", fill="both", expand=True)

        header = tk.Frame(right, background=colours["bg"])
        header.pack(fill="x", padx=26, pady=(22, 0))
        self.page_title = tk.Label(header, font=self.fonts["title"],
                                   background=colours["bg"],
                                   foreground=colours["text"])
        self.page_title.pack(anchor="w")
        tk.Label(header, textvariable=self.subtitle, font=self.fonts["base"],
                 background=colours["bg"],
                 foreground=colours["muted"]).pack(anchor="w", pady=(2, 0))

        # packed before the content so the expanding content cannot push the
        # status line off the bottom of the window
        self._build_status_bar(right)

        self.content = tk.Frame(right, background=colours["bg"])
        self.content.pack(fill="both", expand=True, padx=26, pady=(16, 0))
        self._build_menus()

        self.pages = {}
        for name, _icon, _label, _hint in PAGES:
            frame = tk.Frame(self.content, background=colours["bg"])
            self.pages[name] = frame
            getattr(self, "_page_" + name)(frame)
        self._bind_keys()          # needs the table, which a page builds
        self.show_page(self.page)

    def _build_sidebar(self):
        colours = self.colours
        brand = tk.Frame(self.sidebar, background=colours["sidebar"])
        brand.pack(fill="x", padx=18, pady=(22, 16))
        tk.Label(brand, text="Roblox", font=self.fonts["brand"],
                 background=colours["sidebar"],
                 foreground=colours["nav_from"]).pack(side="left")
        tk.Label(brand, text="Manager", font=self.fonts["brand"],
                 background=colours["sidebar"],
                 foreground=colours["text"]).pack(side="left", padx=(5, 0))

        self.nav = {}
        for name, icon, label, _hint in PAGES:
            item = widgets.NavItem(self.sidebar, colours, icon, tr(label),
                                   lambda n=name: self.show_page(n),
                                   font=self.fonts["base"],
                                   icon_font=self.fonts["icon"])
            item.pack(fill="x", padx=12, pady=2)
            self.nav[name] = item

        footer = tk.Frame(self.sidebar, background=colours["sidebar"])
        footer.pack(side="bottom", fill="x", padx=12, pady=16)
        label = (tr("☀  Light theme") if colours["name"] == "dark"
                 else tr("☾  Dark theme"))
        widgets.Button(footer, colours, label, self.toggle_theme, kind="ghost",
                       background=colours["sidebar"],
                       font=self.fonts["base"]).pack(fill="x")

    def _build_status_bar(self, parent):
        colours = self.colours
        bar = tk.Frame(parent, background=colours["bg"])
        bar.pack(side="bottom", fill="x", padx=26, pady=(12, 14))
        tk.Label(bar, textvariable=self.status, font=self.fonts["small"],
                 background=colours["bg"],
                 foreground=colours["muted"]).pack(side="left")
        tk.Label(bar, textvariable=self.clients, font=self.fonts["small"],
                 background=colours["bg"],
                 foreground=colours["muted"]).pack(side="right")

    def show_page(self, name):
        self.page = name
        for frame in self.pages.values():
            frame.pack_forget()
        self.pages[name].pack(fill="both", expand=True)
        for key, item in self.nav.items():
            item.set_active(key == name)
        for key, _icon, label, hint in PAGES:
            if key == name:
                self.page_title.configure(text=tr(label))
                self.subtitle.set(tr(hint))
        if name == "accounts":
            self._update_subtitle()

    # --------------------------------------------------------- accounts page

    def _page_accounts(self, parent):
        colours = self.colours
        # the launch card is packed first, from the bottom: pack hands out
        # space in packing order, so otherwise the expanding table above it
        # would squeeze it flat
        launch = widgets.Card(parent, colours)
        launch.pack(side="bottom", fill="x", pady=(14, 0))

        card = widgets.Card(parent, colours)
        card.pack(side="top", fill="both", expand=True)
        body = card.body

        top = tk.Frame(body, background=colours["card"])
        top.pack(fill="x", pady=(0, 14))
        widgets.Button(top, colours, tr("Log in"), self.login_browser,
                       kind="primary", icon="🔑", font=self.fonts["bold"],
                       icon_font=self.fonts["icon"],
                       background=colours["card"]).pack(side="left")
        widgets.Button(top, colours, tr("Create account"), self.create_account,
                       icon="✨", font=self.fonts["base"],
                       icon_font=self.fonts["icon"],
                       background=colours["card"]).pack(side="left", padx=8)
        widgets.Button(top, colours, tr("Paste cookie"), self.add_account,
                       icon="📋", font=self.fonts["base"],
                       icon_font=self.fonts["icon"],
                       background=colours["card"]).pack(side="left")

        filter_box = tk.Frame(top, background=colours["card"])
        filter_box.pack(side="right")
        tk.Label(filter_box, text=tr("Filter"), font=self.fonts["base"],
                 background=colours["card"],
                 foreground=colours["muted"]).pack(side="left", padx=(0, 8))
        ttk.Entry(filter_box, textvariable=self.filter_text, width=22,
                  font=self.fonts["base"]).pack(side="left")

        actions = tk.Frame(body, background=colours["card"])
        actions.pack(side="bottom", fill="x", pady=(14, 0))
        self.buttons = {}
        for key, text, icon, command, need, danger in (
                ("refresh", tr("Refresh"), "🔄", self.refresh_selected, "any", False),
                ("relogin", tr("Log in again"), "🔁", self.relogin, "one", False),
                ("rename", tr("Rename"), "✏", self.rename_selected, "one", False),
                ("profile", tr("Profile"), "🌐", self.open_profile, "one", False),
                ("cookie", tr("Copy cookie"), "🍪", self.copy_cookie, "one", False),
                ("remove", tr("Remove"), "🗑", self.remove_selected, "some", True)):
            button = widgets.Button(actions, colours, text, command, icon=icon,
                                    font=self.fonts["base"], danger=danger,
                                    icon_font=self.fonts["icon"],
                                    background=colours["card"])
            button.pack(side="left", padx=(0, 6))
            self.buttons[key] = (button, need)

        table = tk.Frame(body, background=colours["card"])
        table.pack(side="top", fill="both", expand=True)
        columns = ("account", "user_id", "robux", "last_used", "status")
        titles = {"account": tr("ACCOUNT"), "user_id": tr("USER ID"),
                  "robux": tr("ROBUX"), "last_used": tr("LAST LAUNCHED"),
                  "status": tr("STATUS")}
        widths = {"account": 260, "user_id": 110, "robux": 90,
                  "last_used": 160, "status": 220}
        self.tree = ttk.Treeview(table, columns=columns, show="headings",
                                 selectmode="extended")
        for key in columns:
            self.tree.heading(key, text=titles[key],
                              command=lambda k=key: self.sort_by(k))
            self.tree.column(key, width=widths[key],
                             stretch=key in ("account", "status"),
                             anchor="w" if key in ("account", "status")
                             else "center")
        self.tree.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")

        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._sync_buttons())
        self.tree.bind("<Double-1>", self._on_double_click)
        self.tree.bind("<Button-3>", self._on_row_right_click)

        self._launch_card(launch.body)
        self._sync_buttons()

    def _launch_card(self, body):
        colours = self.colours
        body.columnconfigure(1, weight=1)
        body.columnconfigure(3, weight=2)

        tk.Label(body, text=tr("Place ID or game link"), font=self.fonts["base"],
                 background=colours["card"],
                 foreground=colours["muted"]).grid(row=0, column=0, sticky="w")
        ttk.Entry(body, textvariable=self.place_id, font=self.fonts["base"],
                  width=20).grid(row=0, column=1, sticky="ew", padx=(12, 22))

        tk.Label(body, text=tr("Job ID / private-server code"),
                 font=self.fonts["base"], background=colours["card"],
                 foreground=colours["muted"]).grid(row=0, column=2, sticky="w")
        ttk.Entry(body, textvariable=self.job_id,
                  font=self.fonts["base"]).grid(row=0, column=3, sticky="ew",
                                                padx=(12, 22))

        self.launch_button = widgets.Button(
            body, colours, tr("Launch selected"), self.launch_selected,
            kind="primary", icon="🚀", font=self.fonts["bold"],
            icon_font=self.fonts["icon"], background=colours["card"])
        self.launch_button.grid(row=0, column=4, rowspan=2, sticky="nse")

        widgets.CheckBox(body, colours, tr("it is a private-server code"),
                         self.private, font=self.fonts["base"],
                         background=colours["card"]).grid(
                             row=1, column=0, columnspan=2, sticky="w",
                             pady=(12, 0))
        widgets.CheckBox(body, colours, tr("each account in its own server"),
                         self.separate, font=self.fonts["base"],
                         background=colours["card"]).grid(
                             row=2, column=0, columnspan=2, sticky="w",
                             pady=(6, 0))
        self.launch_hint = tk.Label(body, text="", font=self.fonts["small"],
                                    background=colours["card"],
                                    foreground=colours["muted"])
        self.launch_hint.grid(row=1, column=2, columnspan=2, rowspan=2,
                              sticky="w", pady=(12, 0))

    # ---------------------------------------------------------- clients page

    def _page_clients(self, parent):
        colours = self.colours
        card = widgets.Card(parent, colours)
        card.pack(fill="x")
        body = card.body

        tk.Label(body, text=tr("Several clients at once"),
                 font=self.fonts["section"], background=colours["card"],
                 foreground=colours["text"]).pack(anchor="w")
        tk.Message(body, width=680, justify="left", font=self.fonts["base"],
                   background=colours["card"], foreground=colours["muted"],
                   text=tr("A starting Roblox client waits on a named mutex to "
                        "find out whether another one is already running, and "
                        "then tells it to quit. While this is on, the manager "
                        "owns that mutex, so the wait never finishes and as "
                        "many clients as your PC can handle may run. It is "
                        "released when the manager closes.\n\nIt has to be "
                        "switched on before the first client starts.")).pack(
                            anchor="w", pady=(4, 12))
        widgets.CheckBox(body, colours, tr("Allow several clients at once"),
                         self.multi, command=self.toggle_multi,
                         font=self.fonts["base"],
                         background=colours["card"]).pack(anchor="w")

        row = tk.Frame(body, background=colours["card"])
        row.pack(fill="x", pady=(16, 0))
        widgets.Button(row, colours, tr("Close all clients"), self.close_clients,
                       icon="🛑", font=self.fonts["base"], danger=True,
                       icon_font=self.fonts["icon"],
                       background=colours["card"]).pack(side="left")
        self.clients_label = tk.Label(row, text="", font=self.fonts["base"],
                                      background=colours["card"],
                                      foreground=colours["muted"])
        self.clients_label.pack(side="left", padx=(14, 0))

        delay_card = widgets.Card(parent, colours)
        delay_card.pack(fill="x", pady=(14, 0))
        body = delay_card.body
        tk.Label(body, text=tr("Delay between launches"),
                 font=self.fonts["section"], background=colours["card"],
                 foreground=colours["text"]).pack(anchor="w")
        tk.Message(body, width=680, justify="left", font=self.fonts["base"],
                   background=colours["card"], foreground=colours["muted"],
                   text=tr("Roblox rate-limits the ticket endpoint if launches "
                        "are hammered, and each client needs a moment to "
                        "start.")).pack(anchor="w", pady=(4, 12))
        row = tk.Frame(body, background=colours["card"])
        row.pack(anchor="w")
        ttk.Spinbox(row, from_=0, to=120, width=5, textvariable=self.delay,
                    font=self.fonts["base"]).pack(side="left")
        tk.Label(row, text=tr("seconds"), font=self.fonts["base"],
                 background=colours["card"],
                 foreground=colours["muted"]).pack(side="left", padx=(10, 0))

    # --------------------------------------------------------- settings page

    def _page_settings(self, parent):
        colours = self.colours

        card = widgets.Card(parent, colours)
        card.pack(fill="x")
        tk.Label(card.body, text=tr("Appearance"), font=self.fonts["section"],
                 background=colours["card"],
                 foreground=colours["text"]).pack(anchor="w", pady=(0, 10))
        row = tk.Frame(card.body, background=colours["card"])
        row.pack(anchor="w")
        for value, label in (("dark", tr("Dark")), ("light", tr("Light"))):
            widgets.RadioPill(row, colours, label, self.theme_name, value,
                              command=lambda: self._apply_theme(
                                  self.theme_name.get()),
                              font=self.fonts["base"],
                              background=colours["card"]).pack(side="left",
                                                               padx=(0, 10))

        language = widgets.Card(parent, colours)
        language.pack(fill="x", pady=(14, 0))
        tk.Label(language.body, text=tr("Language"),
                 font=self.fonts["section"], background=colours["card"],
                 foreground=colours["text"]).pack(anchor="w", pady=(0, 10))
        row = tk.Frame(language.body, background=colours["card"])
        row.pack(anchor="w")
        for value, label in (("en", "English"), ("ru", "Русский")):
            widgets.RadioPill(row, colours, label, self.lang, value,
                              command=lambda: self._apply_language(
                                  self.lang.get()),
                              font=self.fonts["base"],
                              background=colours["card"]).pack(side="left",
                                                               padx=(0, 10))

        browsers = widgets.Card(parent, colours)
        browsers.pack(fill="x", pady=(14, 0))
        tk.Label(browsers.body, text=tr("Login browser"), font=self.fonts["section"],
                 background=colours["card"],
                 foreground=colours["text"]).pack(anchor="w", pady=(0, 10))
        row = tk.Frame(browsers.body, background=colours["card"])
        row.pack(anchor="w")
        names = (["Ask each time"]
                 + [b.name for b in browser_login.available_browsers()])
        for name in names:
            widgets.RadioPill(row, colours, tr(name), self.browser_choice, name,
                              font=self.fonts["base"],
                              background=colours["card"]).pack(side="left",
                                                               padx=(0, 10))

        data = widgets.Card(parent, colours)
        data.pack(fill="x", pady=(14, 0))
        tk.Label(data.body, text=tr("Data"), font=self.fonts["section"],
                 background=colours["card"],
                 foreground=colours["text"]).pack(anchor="w", pady=(0, 6))
        tk.Label(data.body, text=data_dir(), font=self.fonts["small"],
                 background=colours["card"],
                 foreground=colours["muted"]).pack(anchor="w", pady=(0, 12))
        row = tk.Frame(data.body, background=colours["card"])
        row.pack(anchor="w")
        widgets.Button(row, colours, tr("Open data folder"),
                       lambda: self._open_folder(data_dir()), icon="📁",
                       font=self.fonts["base"], icon_font=self.fonts["icon"],
                       background=colours["card"]).pack(side="left", padx=(0, 8))
        widgets.Button(row, colours, tr("Open browser profiles"),
                       lambda: self._open_folder(browser_login.profiles_dir()),
                       icon="🗂", font=self.fonts["base"],
                       icon_font=self.fonts["icon"],
                       background=colours["card"]).pack(side="left")

    # ------------------------------------------------------------ about page

    def _page_about(self, parent):
        colours = self.colours
        card = widgets.Card(parent, colours)
        card.pack(fill="both", expand=True)
        text = (
            "Accounts are kept as their .ROBLOSECURITY cookie, encrypted with "
            "Windows DPAPI, so the file is readable only by your Windows user "
            "on this machine. Nothing is uploaded anywhere; the only host the "
            "manager talks to is roblox.com.\n\n"
            "Logging in opens Roblox's own login page in a browser profile of "
            "its own — password, captcha and 2FA stay between you and Roblox — "
            "and the cookie is read out of that profile afterwards.\n\n"
            "Launching follows the same path as the website's Play button: a "
            "one-shot authentication ticket is fetched with the cookie and "
            "handed to RobloxPlayerBeta.exe, which never sees the cookie "
            "itself.\n\n"
            "Alt accounts are allowed on Roblox; automating them is not. This "
            "is a launcher — what the accounts do afterwards is on you.")
        tk.Message(card.body, text=tr(text), width=740, justify="left",
                   font=self.fonts["base"], background=colours["card"],
                   foreground=colours["muted"]).pack(anchor="w")

    def _open_folder(self, path):
        try:
            os.startfile(path)
        except (OSError, AttributeError):
            webbrowser.open("file:///" + path.replace("\\", "/"))

    # ----------------------------------------------------------------- theme

    def _apply_theme(self, name):
        if name == self.colours["name"]:
            return
        selection = list(self.tree.selection())
        page = self.page
        self.settings["theme"] = name
        self.colours = theme.apply(self.master, name, self.fonts)
        for child in list(self.winfo_children()):
            child.destroy()
        self.page = page
        self._title_bar_theme()
        self._build()
        self.refresh_table()
        for iid in selection:
            if self.tree.exists(iid):
                self.tree.selection_add(iid)
        self._set_status(tr("Switched to the %s theme") % name)

    def _apply_language(self, lang):
        if lang == i18n.current():
            return
        i18n.set_language(lang)
        self.settings["lang"] = i18n.current()
        # the whole window is rebuilt so every tr(...) is re-read, exactly
        # the way the theme switch already works
        selection = list(self.tree.selection())
        page = self.page
        self.colours = theme.apply(self.master, self.colours["name"],
                                   self.fonts)
        for child in list(self.winfo_children()):
            child.destroy()
        self.page = page
        self._title_bar_theme()
        self._build()
        self.refresh_table()
        for iid in selection:
            if self.tree.exists(iid):
                self.tree.selection_add(iid)

    def toggle_theme(self):
        other = "light" if self.colours["name"] == "dark" else "dark"
        self.theme_name.set(other)
        self._apply_theme(other)

    # ------------------------------------------------------------ menus/keys

    def _build_menus(self):
        colours = self.colours
        self.menu = tk.Menu(self, tearoff=0)
        for label, command in ((tr("Launch"), self.launch_selected),
                               (None, None),
                               (tr("Log in again"), self.relogin),
                               (tr("Refresh"), self.refresh_selected),
                               (tr("Rename…"), self.rename_selected),
                               (tr("Open profile"), self.open_profile),
                               (tr("Copy cookie"), self.copy_cookie),
                               (None, None),
                               (tr("Remove"), self.remove_selected)):
            if label is None:
                self.menu.add_separator()
            else:
                self.menu.add_command(label=label, command=command)

        self.entry_menu = tk.Menu(self, tearoff=0)
        for label, event in ((tr("Paste"), "<<Paste>>"), (tr("Copy"), "<<Copy>>"),
                             (tr("Cut"), "<<Cut>>")):
            self.entry_menu.add_command(
                label=label, command=lambda e=event: self._edit(e))
        self.entry_menu.add_separator()
        self.entry_menu.add_command(
            label=tr("Select all"),
            command=lambda: self._select_all(self._edit_target))

        for menu in (self.menu, self.entry_menu):
            menu.configure(background=colours["card"],
                           foreground=colours["text"],
                           activebackground=colours["select"],
                           activeforeground=colours["text"],
                           borderwidth=0, relief="flat",
                           font=self.fonts["base"])

    def _edit(self, virtual_event):
        widget = self._edit_target
        if widget:
            widget.focus_set()
            widget.event_generate(virtual_event)

    @staticmethod
    def _select_all(widget):
        if widget is None:
            return
        try:
            widget.select_range(0, "end")
            widget.icursor("end")
        except (AttributeError, tk.TclError):
            try:
                widget.tag_add("sel", "1.0", "end-1c")
            except tk.TclError:
                pass

    def _on_entry_right_click(self, event):
        self._edit_target = event.widget
        event.widget.focus_set()
        self.entry_menu.tk_popup(event.x_root, event.y_root)

    def _bind_clipboard(self):
        """Make Ctrl+C/V/X/A work on a Cyrillic keyboard layout too.

        Tk matches those shortcuts on the letter it receives, and with a
        Russian or Ukrainian layout the key next to Ctrl reports Cyrillic_em,
        not `v`, so nothing is pasted. Adding those keysyms to Tk's own
        virtual events fixes every entry at once - and, unlike a binding of
        our own, it cannot paste twice on a Latin layout, because it is still
        the one <<Paste>> event doing the work.
        """
        extra = {"<<Paste>>": ("Cyrillic_em", "Cyrillic_EM"),
                 "<<Copy>>": ("Cyrillic_es", "Cyrillic_ES"),
                 "<<Cut>>": ("Cyrillic_che", "Cyrillic_CHE"),
                 "<<SelectAll>>": ("Cyrillic_ef", "Cyrillic_EF")}
        for event, keysyms in extra.items():
            for keysym in keysyms:
                try:
                    self.master.event_add(event, "<Control-%s>" % keysym)
                except tk.TclError:
                    pass  # a Tk build that does not know the keysym

    def _bind_keys(self):
        self._bind_clipboard()
        for widget_class in ("TEntry", "Entry", "TSpinbox", "Spinbox",
                             "TCombobox", "Text"):
            self.master.bind_class(widget_class, "<Button-3>",
                                   self._on_entry_right_click)
        self.master.bind("<F5>", lambda _e: self.refresh_selected())
        self.master.bind("<Control-n>", lambda _e: self.login_browser())
        self.tree.bind("<Return>", lambda _e: self.launch_selected())
        self.tree.bind("<Delete>", lambda _e: self.remove_selected())
        self.tree.bind("<Control-a>",
                       lambda _e: self.tree.selection_set(
                           self.tree.get_children()) or "break")

    # -------------------------------------------------------------- settings

    def on_close(self):
        if (self.multi.get() and launcher.owns_singleton()
                and launcher.running_clients() > 1):
            if not messagebox.askyesno(
                    tr("Close the manager?"),
                    tr("The manager is what holds the one-client limit open. "
                       "Closing it hands the limit back to Roblox: the windows "
                       "that are open stay open, but the next client to start "
                       "will close them.\n\nClose anyway?")):
                return
        self.settings.update({
            "geometry": self.master.winfo_geometry(),
            "place_id": self.place_id.get().strip(),
            "job_id": self.job_id.get().strip(),
            "private": self.private.get(),
            "separate_servers": self.separate.get(),
            "delay": self.delay.get(),
            "theme": self.colours["name"],
            "lang": i18n.current(),
            "browser": self.browser_choice.get(),
            "page": self.page,
            "sort_column": self._sort[0],
            "sort_reverse": self._sort[1],
        })
        save_settings(self.settings)
        launcher.disable_multi_instance()
        self.master.destroy()

    # ------------------------------------------------------------ background

    def _run(self, func, *args):
        """Run a network call off the UI thread."""
        threading.Thread(target=func, args=args, daemon=True).start()

    def _post(self, kind, *payload):
        self.events.put((kind, payload))

    def _drain_events(self):
        while True:
            try:
                kind, payload = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "status":
                self._set_status(payload[0])
            elif kind == "refresh":
                self.refresh_table()
            elif kind == "wait_done":
                if self._wait:
                    self._wait.close()
                    self._wait = None
            elif kind == "launch_done":
                self._launching = False
                self._sync_buttons()
            elif kind == "error":
                messagebox.showerror(tr("Roblox Account Manager"), payload[0])
        self.after(120, self._drain_events)

    def _set_status(self, text):
        self.status.set(text)

    def _tick_client_count(self):
        self._client_count = launcher.running_clients()
        if not launcher.multi_instance_enabled():
            multi = tr("one client at a time")
        elif launcher.owns_singleton():
            multi = tr("several allowed — the manager holds the limit")
        else:
            multi = tr("several NOT allowed yet — Roblox still holds the limit")
        text = tr("%d Roblox client(s) running  ·  %s") % (self._client_count, multi)
        self.clients.set(text)
        if hasattr(self, "clients_label") and self.clients_label.winfo_exists():
            self.clients_label.configure(text=text)
        self.after(5000, self._tick_client_count)

    # ----------------------------------------------------------------- table

    def visible_accounts(self):
        needle = self.filter_text.get().strip().lower()
        accounts = [a for a in self.store.accounts
                    if not needle
                    or needle in a.label.lower()
                    or needle in a.username.lower()
                    or needle in str(a.user_id)]
        column, reverse = self._sort
        keys = {
            "account": lambda a: a.label.lower(),
            "user_id": lambda a: a.user_id,
            "robux": lambda a: _robux_value(a.note),
            "last_used": lambda a: a.last_used or 0,
            "status": lambda a: a.last_status.lower(),
        }
        return sorted(accounts, key=keys.get(column, keys["account"]),
                      reverse=reverse)

    def sort_by(self, column):
        current, reverse = self._sort
        self._sort = (column, not reverse if column == current else False)
        self.refresh_table()

    def refresh_table(self):
        if not hasattr(self, "tree") or not self.tree.winfo_exists():
            return
        colours = self.colours
        self.tree.tag_configure("odd", background=colours["row_alt"])
        self.tree.tag_configure("bad", foreground=colours["danger"])
        self.tree.tag_configure("empty", foreground=colours["muted"])

        selected = set(self.tree.selection())
        self.tree.delete(*self.tree.get_children())

        accounts = self.visible_accounts()
        if not accounts:
            message = (EMPTY_HINT if not self.store.accounts
                       else "Nothing matches this filter")
            self.tree.insert("", "end", iid="empty", tags=("empty",),
                             values=(message, "", "", "", ""))
            self._sync_buttons()
            self._update_subtitle()
            return

        for index, account in enumerate(accounts):
            last = (time.strftime("%d %b, %H:%M",
                                  time.localtime(account.last_used))
                    if account.last_used else "—")
            status = account.last_status or "—"
            tags = [] if status in ("ok", "launched", "—") else ["bad"]
            if index % 2:
                tags.append("odd")
            name = account.label
            if account.alias and account.alias != account.username:
                name = "%s  (%s)" % (account.alias, account.username)
            self.tree.insert("", "end", iid=str(account.user_id),
                             tags=tuple(tags),
                             values=(name, account.user_id,
                                     account.note or "—", last, status))
        for iid in selected:
            if self.tree.exists(iid):
                self.tree.selection_add(iid)
        self._sync_buttons()
        self._update_subtitle()

    def _update_subtitle(self):
        if self.page != "accounts":
            return
        total = len(self.store.accounts)
        shown = len(self.visible_accounts())
        if not total:
            text = tr("No accounts yet")
        elif shown != total:
            text = tr("%d of %d accounts") % (shown, total)
        else:
            text = (tr("%d account") if total == 1 else tr("%d accounts")) % total
        self.subtitle.set(text)

    def selected_accounts(self):
        chosen = []
        for iid in self.tree.selection():
            if iid.isdigit():
                account = self.store.find(int(iid))
                if account:
                    chosen.append(account)
        return chosen

    def _sync_buttons(self):
        if not hasattr(self, "buttons"):
            return
        count = len(self.selected_accounts())
        for button, need in self.buttons.values():
            button.set_enabled(count >= 1 if need == "some"
                               else count == 1 if need == "one"
                               else True)
        self.launch_button.set_enabled(bool(count))
        if count > 1:
            self.launch_hint.configure(
                text=tr("%d accounts selected — they start one after another")
                     % count)
        elif count == 1:
            self.launch_hint.configure(text="")
        else:
            self.launch_hint.configure(text=tr("Select an account to launch it"))

    def _require_one(self):
        chosen = self.selected_accounts()
        if len(chosen) != 1:
            messagebox.showinfo(tr("Roblox Account Manager"),
                                tr("Select exactly one account."))
            return None
        return chosen[0]

    def _on_double_click(self, event):
        if self.tree.identify_row(event.y):
            self.launch_selected()

    def _on_row_right_click(self, event):
        row = self.tree.identify_row(event.y)
        if not row or not row.isdigit():
            return
        if row not in self.tree.selection():
            self.tree.selection_set(row)
        self._sync_buttons()
        self.menu.tk_popup(event.x_root, event.y_root)

    def _absorb_link(self):
        """Let a pasted game link fill the launch fields in by itself."""
        text = self.place_id.get()
        if "roblox.com" not in text.lower():
            return
        match = PLACE_IN_URL.search(text)
        code = PRIVATE_CODE_IN_URL.search(text)
        if code:
            self.job_id.set(code.group(1))
            self.private.set(True)
            self._set_status(tr("Private-server link recognised"))
        if match:
            self.place_id.set(match.group(1))

    # --------------------------------------------------------- browser login

    def _pick_browser(self):
        """Which browser to open the Roblox login page in."""
        browsers = browser_login.available_browsers()
        if not browsers:
            messagebox.showerror(
                tr("Log in"),
                tr("No supported browser was found.\n\n"
                   "Firefox, Chrome, Edge or Brave is needed to log in "
                   "from here. Install one of them, or use 'Paste "
                   "cookie' instead."))
            return None
        chosen = self.browser_choice.get()
        for browser in browsers:
            if browser.name == chosen:
                return browser
        if len(browsers) == 1:
            return browsers[0]
        return BrowserChooser(self.master, self.fonts, browsers).result

    def login_browser(self):
        self._browser_flow(browser_login.LOGIN_URL, profile=None,
                           account=None, close_when_done=True,
                           waiting=tr("Log in to Roblox in the browser window."))

    def create_account(self):
        if not messagebox.askyesno(
                tr("Create account"),
                tr("This opens Roblox's own sign-up page in a fresh browser "
                   "profile. You fill the form in yourself — the manager does "
                   "not type anything and does not touch the captcha.\n\n"
                   "As soon as the new account is signed in, it is added to the "
                   "list. Roblox allows alt accounts, but creating them in bulk "
                   "or using them for botting is against its rules.\n\nContinue?")):
            return
        self._browser_flow(browser_login.SIGNUP_URL, profile=None,
                           account=None, close_when_done=False,
                           waiting=tr("Create the account in the browser window."))

    def relogin(self):
        account = self._require_one()
        if not account:
            return
        self._browser_flow(browser_login.LOGIN_URL,
                           profile=account.profile_dir or None,
                           account=account, close_when_done=True,
                           waiting=tr("Log in as %s in the browser window.")
                                   % account.label)

    def _browser_flow(self, url, profile, account, close_when_done, waiting):
        browser = self._pick_browser()
        if not browser:
            return
        cancel = threading.Event()
        self._wait = WaitDialog(
            self.master, self.fonts,
            tr("%s\n\nThe account is added by itself once Roblox signs you in.")
            % waiting, cancel)
        self._run(self._browser_worker, browser, url, profile, account,
                  close_when_done, cancel)

    def _browser_worker(self, browser, url, profile, account, close_when_done,
                        cancel):
        try:
            session = browser_login.open_session(browser, url, profile)
        except OSError as exc:
            self._post("wait_done")
            self._post("error", tr("Could not start %s: %s") % (browser.name, exc))
            return

        self._post("status", tr("Waiting for the login in %s…") % browser.name)
        cookie = None
        deadline = time.time() + 15 * 60
        while time.time() < deadline and not cancel.is_set():
            cookie = session.cookie()
            if cookie:
                break
            if not session.alive():
                # one last look: the browser may have written the cookie on
                # its way out, and losing a finished login to that would be
                # the worst possible moment to give up
                cookie = session.cookie()
                break
            time.sleep(2)

        self._post("wait_done")
        if cancel.is_set() or not cookie:
            session.close()
            reason = (tr("cancelled") if cancel.is_set()
                      else tr("the browser was closed before the login "
                              "finished"))
            self._post("status", tr("Login %s") % reason)
            return

        try:
            user = api.authenticated_user(cookie)
        except api.RobloxError as exc:
            session.close()
            self._post("status", "Ready")
            self._post("error", tr("Captured a cookie but Roblox rejected it: %s")
                       % exc)
            return

        if account and int(user["id"]) != account.user_id:
            session.close()
            self._post("status", "Ready")
            self._post("error", tr("You logged in as %s, but %s was selected.")
                       % (user.get("name"), account.username))
            return

        fresh = Account(username=user.get("name", "?"),
                        user_id=int(user["id"]),
                        cookie_enc="",
                        display_name=user.get("displayName", ""),
                        profile_dir=session.profile,
                        last_status="ok")
        fresh.set_cookie(cookie)
        balance = api.robux(cookie, fresh.user_id)
        if balance is not None:
            fresh.note = "R$ %s" % balance
        saved = self.store.add_or_update(fresh)
        if close_when_done:
            session.close()
        self._post("status", tr("Signed in as %s") % saved.label)
        self._post("refresh")

    # --------------------------------------------------------------- actions

    def add_account(self):
        dialog = AddAccountDialog(self.master, self.fonts)
        if not dialog.result:
            return
        cookie, alias = dialog.result
        self._set_status(tr("Checking cookie…"))
        self._run(self._add_account_worker, cookie, alias)

    def _add_account_worker(self, cookie, alias):
        try:
            user = api.authenticated_user(cookie)
        except api.RobloxError as exc:
            self._post("status", "Ready")
            self._post("error", tr("Could not add the account: %s") % exc)
            return
        account = Account(username=user.get("name", "?"),
                          user_id=int(user["id"]),
                          cookie_enc="",
                          alias=alias,
                          display_name=user.get("displayName", ""),
                          last_status="ok")
        account.set_cookie(cookie)
        balance = api.robux(cookie, account.user_id)
        if balance is not None:
            account.note = "R$ %s" % balance
        self.store.add_or_update(account)
        self._post("status", tr("Added %s") % account.label)
        self._post("refresh")

    def refresh_selected(self):
        chosen = self.selected_accounts() or list(self.store.accounts)
        if not chosen:
            return
        self._set_status(tr("Checking %d account(s)…") % len(chosen))
        self._run(self._refresh_worker, chosen)

    def _refresh_worker(self, accounts):
        for account in accounts:
            try:
                user = api.authenticated_user(account.cookie)
                account.username = user.get("name", account.username)
                account.display_name = user.get("displayName", "")
                account.last_status = "ok"
                balance = api.robux(account.cookie, account.user_id)
                if balance is not None:
                    account.note = "R$ %s" % balance
            except (api.RobloxError, OSError, ValueError) as exc:
                account.last_status = str(exc)
            self._post("refresh")
        self.store.save()
        self._post("status", tr("Checked %d account(s)") % len(accounts))

    def rename_selected(self):
        account = self._require_one()
        if not account:
            return
        alias = simpledialog.askstring(
            tr("Rename"), tr("Nickname for %s:") % account.username,
            initialvalue=account.alias, parent=self.master)
        if alias is None:
            return
        account.alias = alias.strip()
        self.store.save()
        self.refresh_table()

    def copy_cookie(self):
        account = self._require_one()
        if not account:
            return
        if not messagebox.askyesno(
                tr("Copy cookie"),
                tr("This cookie is a full login to %s. Put it on the clipboard?")
                % account.label):
            return
        self.clipboard_clear()
        self.clipboard_append(account.cookie)
        self._set_status(tr("Cookie for %s copied to the clipboard") % account.label)

    def open_profile(self):
        account = self._require_one()
        if account:
            webbrowser.open("https://www.roblox.com/users/%d/profile"
                            % account.user_id)

    def remove_selected(self):
        chosen = self.selected_accounts()
        if not chosen:
            return
        names = ", ".join(a.label for a in chosen)
        if not messagebox.askyesno(
                tr("Remove"), tr("Remove %s from the manager?\n"
                    "(The Roblox account itself is untouched.)") % names):
            return
        for account in chosen:
            self.store.remove(account.user_id)
        self.refresh_table()
        self._set_status(tr("Removed %s") % names)

    def toggle_multi(self):
        try:
            if self.multi.get():
                ours = launcher.enable_multi_instance()
                self._set_status(tr("Several clients allowed while the manager stays "
                                    "open"))
                if not ours:
                    self._warn_roblox_got_there_first()
            else:
                launcher.disable_multi_instance()
                self._set_status(tr("Back to one client at a time"))
        except (OSError, RuntimeError) as exc:
            self.multi.set(False)
            messagebox.showerror(tr("Several clients"), str(exc))

    def _warn_roblox_got_there_first(self):
        """Roblox created the singleton objects before the manager did.

        A client that is already running still enforces the one-client limit,
        so the next launch would close it. The manager now holds those objects
        open, so once the running clients are closed they stay alive and every
        launch after that is free of the limit.
        """
        if not messagebox.askyesno(
                tr("Several clients"),
                tr("Roblox was already running when this was switched on, and "
                   "that client still holds the one-client limit itself — so the "
                   "next launch would close it.\n\n"
                   "The manager is holding the limit open now, so closing the "
                   "clients that are open and launching them again from here is "
                   "all it takes.\n\n"
                   "Close the running client(s) now?")):
            return
        count = launcher.close_all_clients()
        for _ in range(20):          # give the processes a moment to go
            if not launcher.running_clients():
                break
            time.sleep(0.25)
        if launcher.reacquire():
            self._set_status(tr("Closed %d client(s) — the manager holds the limit "
                                "now, launch again from here") % count)
        else:
            self._set_status(tr("Closed %d client(s), but the limit is still held "
                                "elsewhere") % count)

    def close_clients(self):
        running = launcher.running_clients()
        if running and not messagebox.askyesno(
                tr("Close all clients"),
                tr("Force-close all %d running Roblox window(s)?") % running):
            return
        count = launcher.close_all_clients()
        self._set_status(tr("Closed %d client(s)") % count)

    def launch_selected(self):
        # A launch runs in a background thread with a pause between accounts,
        # so a second click while it is going would start a second thread and
        # launch the same accounts again — Roblox then kicks the duplicate
        # session (the same account cannot be in two places). One batch at a
        # time prevents that.
        if getattr(self, "_launching", False):
            self._set_status(tr("A launch is already in progress…"))
            return
        chosen = self.selected_accounts()
        if not chosen:
            messagebox.showinfo(tr("Launch"), tr("Select at least one account."))
            return
        # a defensive de-dupe: never launch the same account twice in one batch
        seen = set()
        unique = []
        for account in chosen:
            if account.user_id not in seen:
                seen.add(account.user_id)
                unique.append(account)
        chosen = unique
        place = self.place_id.get().strip()
        if not place.isdigit():
            messagebox.showinfo(
                tr("Launch"),
                tr("Enter the place ID, or paste the game's link and let the "
                   "manager pick the ID out of it.\n\n"
                   "The place ID is the number in "
                   "roblox.com/games/<place id>/..."))
            return
        if len(chosen) > 1 and not self.multi.get():
            if not messagebox.askyesno(
                    tr("Launch"),
                    tr("Several accounts are selected but only one client at a "
                       "time is allowed, so each launch would replace the "
                       "previous one.\n\nAllow several clients?")):
                return
            self.multi.set(True)
            self.toggle_multi()
        if self.multi.get() and not launcher.owns_singleton():
            if not messagebox.askyesno(
                    tr("Several clients"),
                    tr("The one-client limit is not held by the manager right "
                       "now, so this launch would close the client that is "
                       "already open.\n\n"
                       "That happens when Roblox was started before the manager, "
                       "or the manager was closed in between.\n\n"
                       "Launch anyway?")):
                self._warn_roblox_got_there_first()
                return
        already = [a for a in chosen if a.user_id in self._launched_ids]
        if already:
            names = ", ".join(a.label for a in already)
            if not messagebox.askyesno(
                    tr("Launch"),
                    tr("%s is already launched — Roblox will kick the "
                       "duplicate. Launch anyway?") % names):
                return
        try:
            delay = float(self.delay.get())
        except ValueError:
            delay = 6.0
        self._launching = True
        self.launch_button.set_enabled(False)
        self._run(self._launch_worker, chosen, int(place),
                  self.job_id.get().strip(), self.private.get(), delay,
                  self.separate.get())

    def _pick_servers(self, place_id, count):
        """A different public server for each account, freshest first.

        Servers already handed out this session are skipped, so launching the
        accounts one at a time spreads them out just as a batch launch does.
        """
        try:
            servers = api.public_servers(place_id)
        except api.RobloxError as exc:
            self._post("status", tr("Could not list servers (%s) — letting Roblox "
                                    "choose") % exc)
            return []
        fresh = [s["id"] for s in servers if s["id"] not in self._used_jobs]
        chosen = fresh[:count]
        self._used_jobs.update(chosen)
        if len(chosen) < count:
            self._post("status", tr("Only %d free server(s) found — the rest join "
                                    "wherever Roblox puts them")
                       % len(chosen))
        return chosen

    def _launch_worker(self, accounts, place_id, job, is_private, delay,
                       separate=False):
        # Whatever happens in here, the launch lock must be released and the
        # button re-enabled — otherwise a single failure would wedge the app
        # so nothing can be launched again.
        try:
            self._launch_all(accounts, place_id, job, is_private, delay,
                             separate)
        except Exception as exc:  # last-resort guard, never leave it wedged
            self._post("error", "%s" % exc)
        finally:
            self._post("launch_done")

    def _launch_all(self, accounts, place_id, job, is_private, delay,
                    separate=False):
        servers = []
        if separate and not job:
            servers = self._pick_servers(place_id, len(accounts))
        for index, account in enumerate(accounts):
            self._post("status", tr("Launching %s… (%d of %d)")
                       % (account.label, index + 1, len(accounts)))
            try:
                ticket = api.authentication_ticket(account.cookie)
                tracker = api.browser_tracker_id()
                own_server = servers[index] if index < len(servers) else None
                url = api.place_launcher_url(
                    place_id,
                    job_id=own_server or (None if is_private else (job or None)),
                    access_code=job if (is_private and job) else None,
                    tracker_id=tracker)
                launcher.launch(api.launch_uri(ticket, url, tracker_id=tracker))
                account.last_used = time.time()
                account.last_status = "launched"
                self._launched_ids.add(account.user_id)
            except (api.RobloxError, OSError, RuntimeError, ValueError) as exc:
                account.last_status = str(exc)
                self._post("error", "%s: %s" % (account.label, exc))
            self._post("refresh")
            if index < len(accounts) - 1 and delay > 0:
                time.sleep(delay)
        self.store.save()
        self._post("status", tr("Launched %d account(s)") % len(accounts))
        self._post("refresh")


def _robux_value(note):
    digits = "".join(c for c in note if c.isdigit())
    return int(digits) if digits else -1


def enable_dpi_awareness():
    """Tell Windows we scale ourselves, so it does not stretch the window.

    A dpi-unaware process on a scaled display is drawn at 96 dpi and blown up
    by the compositor, which softens every glyph. Must run before the first
    window exists.
    """
    if os.name != "nt":
        return
    import ctypes
    try:                                   # Windows 8.1+: per-monitor aware
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (OSError, AttributeError):
        try:                               # older: system-wide aware
            ctypes.windll.user32.SetProcessDPIAware()
        except (OSError, AttributeError):
            pass


def main():
    enable_dpi_awareness()
    root = tk.Tk()
    dpi = root.winfo_fpixels("1i")
    root.tk.call("tk", "scaling", dpi / 72.0)
    widgets.set_scale(dpi / 96.0)
    app = App(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()
