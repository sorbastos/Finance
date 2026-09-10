"""Painéis com cantos arredondados, desenhados pelo próprio Tk."""
import tkinter as tk


def rounded_surface(canvas, width, height, fill, radius=18):
    r = min(radius, width / 2, height / 2)
    return canvas.create_polygon(
        r, 0, width-r, 0, width, 0, width, r,
        width, height-r, width, height, width-r, height,
        r, height, 0, height, 0, height-r, 0, r, 0, 0,
        smooth=True, splinesteps=24, fill=fill, outline='', tags='rounded_surface')


class RoundedPanel(tk.Canvas):
    def __init__(self, master):
        super().__init__(master, bg='#f2f6fc', highlightthickness=0, width=220, height=100)
        self.body = tk.Frame(self, bg='white')
        self._window = self.create_window(14, 16, window=self.body, anchor='nw')
        self.bind('<Configure>', self.redraw)
        self.body.bind('<Configure>', self._fit_height)

    def _fit_height(self, event=None):
        height = self.body.winfo_reqheight() + 32
        if int(self.cget('height')) != height:
            self.configure(height=height)

    def redraw(self, event=None):
        self.delete('rounded_surface')
        rounded_surface(self, self.winfo_width(), self.winfo_height(),
                        '#1e293b' if getattr(self, 'dark_theme', False) else 'white')
        self.tag_lower('rounded_surface')
        self.itemconfigure(self._window, width=max(1, self.winfo_width()-28))
