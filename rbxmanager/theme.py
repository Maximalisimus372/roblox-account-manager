"""Colours for the window.

Buttons, nav items, cards and checkboxes are drawn on canvases (see
`widgets.py`), so what ttk still has to style is the table, the scrollbars and
the text inputs. Both live off one palette dictionary, which is what makes the
dark/light switch a one-liner.
"""

from tkinter import ttk

from . import widgets


def _row_height():
    """Table rows follow the display's scaling like everything else."""
    return widgets.px(36)

DARK = {
    "name": "dark",
    "bg": "#0f111a",            # content background
    "sidebar": "#151827",
    "sidebar_hover": "#1e2233",
    "card": "#191d2b",
    "card_alt": "#1f2434",
    "card_hover": "#262c40",
    "card_border": "#242938",
    "field": "#12151f",
    "border": "#2a3042",
    "text": "#eceef6",
    "muted": "#9aa1bb",          # readable, not washed out, on the dark cards
    "disabled_text": "#5f677f",
    "accent": "#3b7dfb",        # primary buttons
    "accent_hover": "#5b95fc",
    "accent_text": "#ffffff",
    "nav_from": "#f0566c",      # the active sidebar item's gradient
    "nav_to": "#f4854e",
    "danger": "#ff6b6b",
    "danger_hover": "#ff8585",
    "select": "#25304a",
    "row_alt": "#1c2130",
    "ok": "#4ade80",
    "heading": "#151927",
}

LIGHT = {
    "name": "light",
    "bg": "#f4f5f9",
    "sidebar": "#ffffff",
    "sidebar_hover": "#eef0f6",
    "card": "#ffffff",
    "card_alt": "#f1f3f8",
    "card_hover": "#e6e9f2",
    "card_border": "#e2e5ee",
    "field": "#ffffff",
    "border": "#d9dde8",
    "text": "#141826",
    "muted": "#5f6678",
    "disabled_text": "#a0a7b8",
    "accent": "#2f6bff",
    "accent_hover": "#4b82ff",
    "accent_text": "#ffffff",
    "nav_from": "#f0566c",
    "nav_to": "#f4854e",
    "danger": "#d64545",
    "danger_hover": "#e35c5c",
    "select": "#dfe8ff",
    "row_alt": "#f7f8fc",
    "ok": "#1f9254",
    "heading": "#ffffff",
}

PALETTES = {"dark": DARK, "light": LIGHT}

_current = DARK


def palette(name):
    return PALETTES.get(name, DARK)


def current():
    """The palette last applied, for the odd widget ttk cannot style."""
    return _current


def apply(root, name, fonts):
    """Repaint what ttk still draws, and return the palette that was used."""
    global _current
    colours = _current = palette(name)
    style = ttk.Style(root)
    style.theme_use("clam")
    root.configure(background=colours["bg"])

    style.configure(".",
                    background=colours["bg"],
                    foreground=colours["text"],
                    fieldbackground=colours["field"],
                    bordercolor=colours["border"],
                    lightcolor=colours["bg"],
                    darkcolor=colours["bg"],
                    troughcolor=colours["card"],
                    focuscolor=colours["accent"],
                    insertcolor=colours["text"],
                    arrowcolor=colours["muted"])

    # --- text inputs -----------------------------------------------------
    for widget in ("TEntry", "TSpinbox", "TCombobox"):
        style.configure(widget,
                        fieldbackground=colours["field"],
                        background=colours["field"],
                        foreground=colours["text"],
                        bordercolor=colours["border"],
                        lightcolor=colours["border"],
                        darkcolor=colours["border"],
                        insertcolor=colours["text"],
                        arrowcolor=colours["muted"],
                        borderwidth=1, padding=(10, 8))
        style.map(widget,
                  bordercolor=[("focus", colours["accent"])],
                  lightcolor=[("focus", colours["accent"])],
                  darkcolor=[("focus", colours["accent"])])

    # --- scrollbars ------------------------------------------------------
    for widget in ("TScrollbar", "Vertical.TScrollbar",
                   "Horizontal.TScrollbar"):
        style.configure(widget,
                        background=colours["card_alt"],
                        troughcolor=colours["card"],
                        bordercolor=colours["card"],
                        lightcolor=colours["card_alt"],
                        darkcolor=colours["card_alt"],
                        arrowcolor=colours["muted"],
                        borderwidth=0, arrowsize=13)
        style.map(widget,
                  background=[("disabled", colours["card"]),
                              ("pressed", colours["accent"]),
                              ("active", colours["card_hover"])],
                  arrowcolor=[("active", colours["text"])])

    # --- the table -------------------------------------------------------
    style.configure("Treeview",
                    background=colours["card"],
                    fieldbackground=colours["card"],
                    foreground=colours["text"],
                    bordercolor=colours["card"],
                    lightcolor=colours["card"],
                    darkcolor=colours["card"],
                    borderwidth=0, rowheight=_row_height())
    style.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
    style.map("Treeview",
              background=[("selected", colours["select"])],
              foreground=[("selected", colours["text"])])
    style.configure("Treeview.Heading",
                    background=colours["heading"],
                    foreground=colours["muted"],
                    bordercolor=colours["card_border"],
                    lightcolor=colours["heading"],
                    darkcolor=colours["heading"],
                    relief="flat", borderwidth=0,
                    font=fonts["small"], padding=(10, 10))
    style.map("Treeview.Heading",
              background=[("active", colours["card_alt"])],
              foreground=[("active", colours["text"])])

    style.configure("Card.TFrame", background=colours["card"])
    style.configure("Horizontal.TProgressbar",
                    background=colours["accent"],
                    troughcolor=colours["card_alt"],
                    bordercolor=colours["card_alt"],
                    lightcolor=colours["accent"], darkcolor=colours["accent"])
    return colours
