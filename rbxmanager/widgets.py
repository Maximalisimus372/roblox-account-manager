"""Rounded, flat widgets drawn on a canvas.

Ttk has no rounded corners, no gradients and no control over a checkbox's
looks, so the pieces that carry the design - buttons, nav items, cards,
checkboxes, radio pills - are drawn by hand here. Each one is a `tk.Canvas`
that repaints itself on resize, hover and click, and takes its colours from
the palette it is handed, so switching theme is a matter of rebuilding them.
"""

import tkinter as tk


_scale = 1.0


def set_scale(value):
    """Pixel sizes here are written for a 96-dpi screen; scale them elsewhere.

    Called once at start-up from the display's real dpi, which the process
    only learns after declaring itself dpi-aware. Fonts are in points and Tk
    scales those itself.
    """
    global _scale
    _scale = max(1.0, float(value))


def px(value):
    """A 96-dpi pixel size in this display's pixels, rounded to whole ones."""
    return int(round(value * _scale))


def snap(value):
    """Round to a whole pixel.

    Tk anti-aliases canvas text around fractional coordinates, which smears a
    glyph across roughly half again as many pixels and reads as blurry next to
    the same text in a Label. Every text position here goes through this.
    """
    return int(round(value))


def rounded_points(x1, y1, x2, y2, radius):
    """A rounded rectangle as a smoothed polygon."""
    radius = max(0, min(radius, (x2 - x1) / 2, (y2 - y1) / 2))
    return [
        x1 + radius, y1, x2 - radius, y1, x2, y1, x2, y1 + radius,
        x2, y2 - radius, x2, y2, x2 - radius, y2, x1 + radius, y2,
        x1, y2, x1, y2 - radius, x1, y1 + radius, x1, y1,
    ]


def draw_round_rect(canvas, x1, y1, x2, y2, radius, **options):
    return canvas.create_polygon(rounded_points(x1, y1, x2, y2, radius),
                                 smooth=True, splinesteps=24, **options)


def _mix(colour_a, colour_b, ratio):
    """Blend two #rrggbb colours."""
    a = [int(colour_a[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(colour_b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(
        int(round(a[i] + (b[i] - a[i]) * ratio)) for i in range(3))


def draw_gradient(canvas, x1, y1, x2, y2, radius, start, end):
    """A rounded rectangle filled with a top-to-bottom gradient.

    Tk cannot clip, so each scanline is inset by however much the rounded
    corner eats into it, which keeps the corners clean without a mask.
    """
    height = max(1, int(y2 - y1))
    ids = []
    for offset in range(height):
        y = y1 + offset
        inset = 0.0
        for corner in (offset, height - offset - 1):
            if corner < radius:
                inset = max(inset, radius - (radius ** 2
                                             - (radius - corner) ** 2) ** 0.5)
        ids.append(canvas.create_line(x1 + inset, y, x2 - inset, y,
                                      fill=_mix(start, end, offset / height)))
    return ids


class CanvasWidget(tk.Canvas):
    """Shared plumbing: no border, repaint on resize, palette colours."""

    def __init__(self, master, colours, background=None, **kwargs):
        self.colours = colours
        background = background or colours["bg"]
        super().__init__(master, highlightthickness=0, bd=0,
                         background=background, **kwargs)
        self.bind("<Configure>", lambda _event: self.redraw())

    def redraw(self):
        raise NotImplementedError

    def follow(self, variable):
        """Repaint when `variable` changes, and let go when destroyed.

        Without dropping the trace, a theme switch - which rebuilds every
        widget - leaves traces pointing at destroyed canvases, and the next
        write raises "invalid command name".
        """
        self._variable = variable
        self._trace = variable.trace_add("write", self._on_variable)
        self.bind("<Destroy>", self._on_destroy, add="+")

    def _on_variable(self, *_args):
        if self.winfo_exists():
            self.redraw()

    def _on_destroy(self, _event):
        trace = getattr(self, "_trace", None)
        if trace is not None:
            try:
                self._variable.trace_remove("write", trace)
            except (tk.TclError, ValueError):
                pass
            self._trace = None


class Button(CanvasWidget):
    """A flat rounded button: primary (filled), ghost or plain."""

    HEIGHTS = {"primary": 40, "secondary": 34, "ghost": 32}

    def __init__(self, master, colours, text, command=None, *, kind="secondary",
                 icon="", width=None, height=None, radius=10, font=None,
                 icon_font=None, background=None, danger=False):
        self.text = text
        self.icon = icon
        self.kind = kind
        self.command = command
        self.font = font
        self.icon_font = icon_font or font
        self.danger = danger
        self.enabled = True
        self._hover = False
        self._pressed = False
        self.icon_gap = px(27)
        self.radius = px(radius)
        height = height or px(self.HEIGHTS.get(kind, 34))
        if width is None:
            measure = font.measure(text) if font else 8 * len(text)
            width = measure + px(34 if kind == "primary" else 26)
            if icon:
                width += self.icon_gap
        super().__init__(master, colours, background=background,
                         width=width, height=height)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)

    # -- state ------------------------------------------------------------
    def set_enabled(self, enabled):
        if enabled != self.enabled:
            self.enabled = enabled
            self.configure(cursor="hand2" if enabled else "")
            self.redraw()

    def _on_enter(self, _event):
        self._hover = True
        self.configure(cursor="hand2" if self.enabled else "")
        self.redraw()

    def _on_leave(self, _event):
        self._hover = self._pressed = False
        self.redraw()

    def _on_press(self, _event):
        if self.enabled:
            self._pressed = True
            self.redraw()

    def _on_release(self, _event):
        was_pressed = self._pressed
        self._pressed = False
        self.redraw()
        if was_pressed and self.enabled and self.command:
            self.command()

    # -- painting ---------------------------------------------------------
    def _colours(self):
        c = self.colours
        if not self.enabled:
            return c["card_alt"], c["disabled_text"]
        if self.kind == "primary":
            base = c["danger"] if self.danger else c["accent"]
            hover = c["danger_hover"] if self.danger else c["accent_hover"]
            fill = hover if self._hover else base
            if self._pressed:
                fill = _mix(fill, "#000000", 0.15)
            return fill, c["accent_text"]
        if self.kind == "ghost":
            fill = c["card_alt"] if self._hover else self["background"]
            return fill, c["danger"] if self.danger else c["muted"]
        fill = c["card_hover"] if self._hover else c["card_alt"]
        if self._pressed:
            fill = _mix(fill, "#000000", 0.12)
        return fill, c["danger"] if self.danger else c["text"]

    def redraw(self):
        self.delete("all")
        width = self.winfo_width() or int(self["width"])
        height = self.winfo_height() or int(self["height"])
        fill, text_colour = self._colours()
        draw_round_rect(self, 1, 1, width - 1, height - 1, self.radius,
                        fill=fill, outline="")
        middle = snap(height / 2)
        text_width = (self.font.measure(self.text) if self.font
                      else 8 * len(self.text))
        if self.icon:
            start = snap((width - text_width - self.icon_gap) / 2)
            self.create_text(start, middle, text=self.icon, anchor="w",
                             fill=text_colour, font=self.icon_font)
            self.create_text(start + self.icon_gap, middle, text=self.text,
                             anchor="w", fill=text_colour, font=self.font)
        else:
            self.create_text(snap((width - text_width) / 2), middle,
                             text=self.text, anchor="w",
                             fill=text_colour, font=self.font)


class NavItem(CanvasWidget):
    """One row of the sidebar; the active one gets the gradient."""

    def __init__(self, master, colours, icon, text, command, *, font=None,
                 icon_font=None, width=None, height=None):
        width = width or px(190)
        height = height or px(42)
        self.icon = icon
        self.text = text
        self.command = command
        self.font = font
        self.icon_font = icon_font or font
        self.active = False
        self._hover = False
        super().__init__(master, colours, background=colours["sidebar"],
                         width=width, height=height)
        self.bind("<Enter>", lambda _e: self._set_hover(True))
        self.bind("<Leave>", lambda _e: self._set_hover(False))
        self.bind("<Button-1>", lambda _e: self.command())

    def _set_hover(self, hover):
        self._hover = hover
        self.configure(cursor="hand2" if hover else "")
        self.redraw()

    def set_active(self, active):
        self.active = active
        self.redraw()

    def redraw(self):
        self.delete("all")
        width = self.winfo_width() or int(self["width"])
        height = self.winfo_height() or int(self["height"])
        colours = self.colours
        if self.active:
            draw_gradient(self, 2, 2, width - 2, height - 2, px(12),
                          colours["nav_from"], colours["nav_to"])
            text_colour = colours["accent_text"]
        else:
            if self._hover:
                draw_round_rect(self, 2, 2, width - 2, height - 2, px(12),
                                fill=colours["sidebar_hover"], outline="")
            text_colour = colours["muted"]
        middle = snap(height / 2)
        self.create_text(px(20), middle, text=self.icon, anchor="w",
                         fill=text_colour, font=self.icon_font)
        self.create_text(px(48), middle, text=self.text, anchor="w",
                         fill=text_colour, font=self.font)


class Card(tk.Frame):
    """A rounded panel with an inner frame to put widgets in."""

    def __init__(self, master, colours, padding=(px(18), px(16))):
        super().__init__(master, background=colours["bg"],
                         highlightthickness=0, bd=0)
        self.colours = colours
        self.canvas = tk.Canvas(self, highlightthickness=0, bd=0,
                                background=colours["bg"])
        self.canvas.place(x=0, y=0, relwidth=1, relheight=1)
        self.body = tk.Frame(self, background=colours["card"])
        pad_x, pad_y = padding
        self.body.pack(fill="both", expand=True, padx=pad_x, pady=pad_y)
        self.bind("<Configure>", self._redraw)

    def _redraw(self, _event=None):
        self.canvas.delete("all")
        width = self.winfo_width()
        height = self.winfo_height()
        draw_round_rect(self.canvas, 1, 1, width - 1, height - 1, px(14),
                        fill=self.colours["card"],
                        outline=self.colours["card_border"])


class CheckBox(CanvasWidget):
    """A rounded checkbox with its label, tied to a BooleanVar."""

    def __init__(self, master, colours, text, variable, command=None, *,
                 font=None, background=None, width=None, height=None):
        height = height or px(26)
        self.text = text
        self.variable = variable
        self.command = command
        self.font = font
        self._hover = False
        if width is None:
            width = (font.measure(text) if font else 8 * len(text)) + px(40)
        super().__init__(master, colours, background=background,
                         width=width, height=height)
        self.bind("<Button-1>", self._toggle)
        self.bind("<Enter>", lambda _e: self._set_hover(True))
        self.bind("<Leave>", lambda _e: self._set_hover(False))
        self.follow(variable)

    def _set_hover(self, hover):
        self._hover = hover
        self.configure(cursor="hand2" if hover else "")
        self.redraw()

    def _toggle(self, _event):
        self.variable.set(not self.variable.get())
        if self.command:
            self.command()

    def redraw(self):
        self.delete("all")
        height = self.winfo_height() or int(self["height"])
        colours = self.colours
        checked = bool(self.variable.get())
        side = px(18)
        top = snap((height - side) / 2)
        box = (2, top, 2 + side, top + side)
        if checked:
            draw_round_rect(self, *box, px(6), fill=colours["accent"],
                            outline="")
            x, y = box[0], box[1]
            self.create_line(x + side * 0.25, y + side * 0.53,
                             x + side * 0.44, y + side * 0.72,
                             x + side * 0.75, y + side * 0.30,
                             fill=colours["accent_text"], width=max(2, px(2)),
                             capstyle="round", joinstyle="round")
        else:
            draw_round_rect(self, *box, px(6), fill=colours["field"],
                            outline=colours["muted"] if self._hover
                            else colours["card_border"])
        self.create_text(px(30), snap(height / 2), text=self.text, anchor="w",
                         fill=colours["text"], font=self.font)


class RadioPill(CanvasWidget):
    """One option of a radio group, drawn like the mock-up's pills."""

    def __init__(self, master, colours, text, variable, value, command=None, *,
                 font=None, background=None, height=None):
        height = height or px(38)
        self.text = text
        self.variable = variable
        self.value = value
        self.command = command
        self.font = font
        self._hover = False
        width = (font.measure(text) if font else 8 * len(text)) + px(56)
        super().__init__(master, colours, background=background,
                         width=width, height=height)
        self.bind("<Button-1>", self._choose)
        self.bind("<Enter>", lambda _e: self._set_hover(True))
        self.bind("<Leave>", lambda _e: self._set_hover(False))
        self.follow(variable)

    def _set_hover(self, hover):
        self._hover = hover
        self.configure(cursor="hand2" if hover else "")
        self.redraw()

    def _choose(self, _event):
        self.variable.set(self.value)
        if self.command:
            self.command()

    def redraw(self):
        self.delete("all")
        width = self.winfo_width() or int(self["width"])
        height = self.winfo_height() or int(self["height"])
        colours = self.colours
        chosen = self.variable.get() == self.value
        draw_round_rect(self, 1, 1, width - 1, height - 1, height / 2,
                        fill=colours["card_hover"] if (self._hover or chosen)
                        else colours["card_alt"],
                        outline=colours["accent"] if chosen else "")
        middle = snap(height / 2)
        self.create_oval(px(14), middle - px(8), px(30), middle + px(8),
                         outline=colours["accent"] if chosen
                         else colours["muted"], width=2)
        if chosen:
            self.create_oval(px(18), middle - px(4), px(26), middle + px(4),
                             fill=colours["accent"], outline="")
        self.create_text(px(40), middle, text=self.text, anchor="w",
                         fill=colours["text"], font=self.font)
