"""
kiosk_ui.py

Reusable themed UI components for the Liberty Kiosk system.
This helps keep the main GUI file cleaner and allows the visitor tool
(and future tools) to share consistent styling.
"""

import tkinter as tk
from .kiosk_config import BG_COLOR, USMC_GOLD, USMC_DARK, USMC_RED


class ThemedDialogs:
    """Mixin or base class providing consistent red/gold themed dialogs."""

    def _create_themed_toplevel(self, title, bg=BG_COLOR):
        dlg = tk.Toplevel(self)
        dlg.title(title)
        dlg.configure(bg=bg)
        dlg.geometry("700x420")
        dlg.grab_set()
        dlg.lift()
        dlg.focus_force()
        dlg.transient(self)
        return dlg

    def themed_showinfo(self, title, message):
        dlg = self._create_themed_toplevel(title, BG_COLOR)
        tk.Label(dlg, text=message, fg=USMC_GOLD, bg=BG_COLOR,
                 font=("Helvetica", 16, "bold"), wraplength=620).pack(pady=40)
        tk.Button(dlg, text="OK", bg=USMC_GOLD, fg=USMC_DARK,
                  font=("Helvetica", 14, "bold"), width=15, height=2,
                  command=dlg.destroy).pack(pady=20)
        dlg.bind("<Return>", lambda e: dlg.destroy())
        dlg.wait_window(dlg)

    def themed_showerror(self, title, message):
        dlg = self._create_themed_toplevel(title, USMC_RED)
        tk.Label(dlg, text=message, fg="white", bg=USMC_RED,
                 font=("Helvetica", 16, "bold"), wraplength=620).pack(pady=40)
        tk.Button(dlg, text="OK", bg=USMC_GOLD, fg=USMC_DARK,
                  font=("Helvetica", 14, "bold"), width=15, height=2,
                  command=dlg.destroy).pack(pady=20)
        dlg.bind("<Return>", lambda e: dlg.destroy())
        dlg.wait_window(dlg)

    def themed_askyesno(self, title, message):
        dlg = self._create_themed_toplevel(title, BG_COLOR)
        result = [False]

        tk.Label(dlg, text=message, fg=USMC_GOLD, bg=BG_COLOR,
                 font=("Helvetica", 16, "bold"), wraplength=620).pack(pady=40)

        def yes():
            result[0] = True
            dlg.destroy()

        def no():
            result[0] = False
            dlg.destroy()

        btn_frame = tk.Frame(dlg, bg=BG_COLOR)
        btn_frame.pack(pady=20)
        tk.Button(btn_frame, text="YES", bg=USMC_GOLD, fg=USMC_DARK,
                  font=("Helvetica", 14, "bold"), width=12, height=2,
                  command=yes).pack(side="left", padx=30)
        tk.Button(btn_frame, text="NO", bg=USMC_RED, fg="white",
                  font=("Helvetica", 14, "bold"), width=12, height=2,
                  command=no).pack(side="left", padx=30)

        dlg.bind("<Return>", lambda e: yes())
        dlg.bind("<Escape>", lambda e: no())
        dlg.wait_window(dlg)
        return result[0]

    def themed_askstring(self, title, prompt, show=None):
        dlg = self._create_themed_toplevel(title, BG_COLOR)
        result = [None]

        tk.Label(dlg, text=prompt, fg=USMC_GOLD, bg=BG_COLOR,
                 font=("Helvetica", 18, "bold"), wraplength=650).pack(pady=30)

        entry = tk.Entry(dlg, font=("Helvetica", 18), width=40,
                         show=show, justify="center")
        entry.pack(pady=10)

        def submit():
            result[0] = entry.get()
            dlg.destroy()

        def cancel():
            result[0] = None
            dlg.destroy()

        btn_frame = tk.Frame(dlg, bg=BG_COLOR)
        btn_frame.pack(pady=20)
        tk.Button(btn_frame, text="OK", bg=USMC_GOLD, fg=USMC_DARK,
                  font=("Helvetica", 14, "bold"), width=12, height=2,
                  command=submit).pack(side="left", padx=20)
        tk.Button(btn_frame, text="Cancel", bg=USMC_RED, fg="white",
                  font=("Helvetica", 14, "bold"), width=12, height=2,
                  command=cancel).pack(side="left", padx=20)

        entry.bind("<Return>", lambda e: submit())
        dlg.bind("<Return>", lambda e: submit())
        dlg.bind("<Escape>", lambda e: cancel())

        def force_focus():
            entry.focus_force()
            entry.select_range(0, tk.END)
            entry.icursor(tk.END)

        dlg.after(100, force_focus)
        dlg.wait_window(dlg)
        return result[0]