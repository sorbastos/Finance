"""Tema visual e preferência local."""
import tkinter as tk
from tkinter import ttk


def apply_theme(app):
    dark=app.dark_mode.get()
    bg,panel,fg,muted,line,active=('#111827','#1e293b','#e5edf7','#a8b7c9','#334155','#243f5d') if dark else ('#f2f6fc','white','#25364c','#78879a','#eaf0f8','#eaf3ff')
    style=ttk.Style(app)
    style.configure('.',background=bg,foreground=fg)
    for name in ('TFrame','TLabel','TNotebook','Main.TNotebook'):
        style.configure(name,background=bg)
    style.configure('TLabel',foreground=fg)
    style.configure('TButton',background=line,foreground=fg)
    style.map('TButton',background=[('active',active),('disabled',bg)],foreground=[('disabled',muted)])
    style.configure('Import.TButton',background='#258bd2',foreground='white')
    style.map('Import.TButton',background=[('active','#1477bb')],foreground=[('disabled',muted),('active','white')])
    for name in ('TEntry','TCombobox','TSpinbox'):
        style.configure(name,fieldbackground=panel,foreground=fg,background=line,insertcolor=fg,arrowcolor=fg)
        style.map(name,fieldbackground=[('readonly',panel),('disabled',bg)],foreground=[('readonly',fg),('disabled',muted)],selectbackground=[('!disabled',active)],selectforeground=[('!disabled',fg)])
    for name in ('TCheckbutton','TRadiobutton'):
        style.configure(name,background=bg,foreground=fg)
        style.map(name,background=[('active',bg)],foreground=[('disabled',muted)])
    style.configure('TNotebook.Tab',background=bg,foreground=muted)
    style.map('TNotebook.Tab',background=[('selected',panel)],foreground=[('selected',fg)])
    style.configure('Treeview',background=panel,fieldbackground=panel,foreground=fg)
    style.map('Treeview',background=[('selected',active)],foreground=[('selected',fg)])
    style.configure('Treeview.Heading',background=line,foreground=fg)
    style.map('Treeview.Heading',background=[('active',active)])
    style.configure('TScrollbar',background=line,troughcolor=bg,arrowcolor=fg)
    app.option_add('*TCombobox*Listbox.background',panel)
    app.option_add('*TCombobox*Listbox.foreground',fg)
    app.option_add('*TCombobox*Listbox.selectBackground',active)
    app.option_add('*TCombobox*Listbox.selectForeground',fg)
    def walk(widget):
        if isinstance(widget,(tk.Tk,tk.Toplevel,tk.Frame,tk.Label,tk.Button,tk.Canvas,tk.Checkbutton)):
            if not hasattr(widget,'_theme_original'):
                widget._theme_original={key:widget.cget(key) for key in ('background','foreground','activebackground','activeforeground','highlightbackground','selectcolor') if key in widget.keys()}
            settings={}
            for key,value in widget._theme_original.items():
                if key=='foreground' and widget in getattr(app,'metrics',{}).values(): continue
                if not dark:
                    settings[key]=value
                elif key in ('background','selectcolor'):
                    settings[key]=panel if value in ('white','#ffffff') else bg
                elif key=='activebackground':settings[key]=active
                elif key=='highlightbackground':settings[key]=line
                else:settings[key]=fg
            widget.configure(**settings)
        if isinstance(widget,ttk.Treeview):widget.tag_configure('negative',foreground='#fb8b99' if dark else '#aa293d')
        if isinstance(widget,tk.Canvas):widget.dark_theme=dark
        for child in widget.winfo_children():walk(child)
    walk(app)
    app.update_navigation()
    if hasattr(app,'chart_mode'): app.draw_dashboard()
