import csv
import datetime
import hashlib
import random
import signal
import shutil
import subprocess
import sys
import time
import threading
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, simpledialog, filedialog, scrolledtext

# ====================== SHARED UTILITIES ======================
# All common colors, hashing, CAC parsing, profile loading, liberty status checks,
# and visitor logging now live in liberty_common.py so the standalone visitor
# tool and future utilities can reuse the exact same logic.
from liberty_common import (
    USMC_RED,
    USMC_GOLD,
    USMC_DARK,
    BG_COLOR,
    DATA_DIR,
    PROFILES_FILE,
    hash_secret,
    verify_secret,
    _csv_safe,
    parse_cac_barcode,
    load_profiles,
    find_open_entry,
    log_visitor_signin,
    format_phone,
    find_profile_by_edipi,
)

from kiosk_config import (
    ensure_data_directories,
    get_daily_log_path,
    get_visitor_log_path,
    DAILY_LOGS_DIR,
    VISITOR_LOGS_DIR,
    BACKUPS_DIR,
    SUPERUSER_HASH_FILE,
    AUDIT_FILE,
    DEFAULT_ADMIN_PASSWORD,
)

# ====================== MAIN-KIOSK SPECIFIC CONSTANTS ======================
ZYN_PUNS = [
    "Monica Lewzynsky is NOT authorized for liberty!",
    "Thomas Jefferzyn is NOT authorized for liberty!",
    "Lynyrd Zynyrd is NOT authorized for liberty!",
    "Zynjamin Franklin is NOT authorized for liberty!",
    "Zyn Diesel is NOT authorized for liberty!",
    "Zyndaya is NOT authorized for liberty!",
    "Frank Zynatra is NOT authorized for liberty!",
]

ZYN_UPC_CODES = {
    # Common Zyn 6mg and 3mg cans (U.S.)
    "609249900036", "609249900425", "609249900418", "609249901415",
    "609249902412", "609249902429", "609249903013", "609249903419",
    "609249903426", "609249904416", "609249904423", "609249906410",
    "609249906427", "609249907417", "609249907424", "609249914415",
    "609249914422",

    # Zyn 6mg Wintergreen (confirmed)
    "609249903020",

    # Other / older variants
    "781138807159",
}

ADMIN_HASH_FILE = DATA_DIR / "admin.hash"
DEFAULT_ADMIN_PASSWORD = "LibertyKiosk2026!"

# ==================== SUPERUSER (BREAK-GLASS) ====================
SUPERUSER_HASH_FILE = "superuser_hash.txt"
AUDIT_FILE = DATA_DIR / "admin_audit.csv"


class LibertyKiosk(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MARDET-MONTEREY LIBERTY KIOSK")
        self.attributes("-fullscreen", True)
        self.configure(bg=BG_COLOR)
        self.protocol("WM_DELETE_WINDOW", self.ignore_close)
        self.bind("<Escape>", lambda e: self.show_admin_menu())

        self.init_files()
        self.profiles = load_profiles()   # from liberty_common
        self.current_user = None

        self.build_main_screen()
        self.start_daily_backup_scheduler()

    def ignore_close(self): pass

    def init_files(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        (DATA_DIR / "daily_logs").mkdir(parents=True, exist_ok=True)
        (DATA_DIR / "backups").mkdir(parents=True, exist_ok=True)

        if not PROFILES_FILE.exists():
            with open(PROFILES_FILE, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Raw_ID", "EDIPI", "Rank", "Last_Name", "First_Name", "Middle_Initial", "Phone", "PIN_hash"])

        if not ADMIN_HASH_FILE.exists():
            default_hash = hash_secret(DEFAULT_ADMIN_PASSWORD)
            with open(ADMIN_HASH_FILE, "w", encoding="utf-8") as f:
                f.write(default_hash)

    def get_log_file(self):
        today = datetime.date.today()
        return DATA_DIR / "daily_logs" / f"liberty_log_{today.isoformat()}.csv"

    def log_admin_action(self, action, detail="", actor="admin"):
        """Append an entry to the standalone admin audit trail.

        Kept separate from the liberty logs so it never corrupts their column
        layout and gives a real record of who did what (logins, password
        changes, force check-ins, exports)."""
        try:
            new_file = not AUDIT_FILE.exists()
            with open(AUDIT_FILE, "a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                if new_file:
                    writer.writerow(["Timestamp", "Actor", "Action", "Detail"])
                writer.writerow([
                    datetime.datetime.now().isoformat(timespec="seconds"),
                    actor, action, _csv_safe(detail),
                ])
        except Exception as e:
            print(f"[AUDIT ERROR] {e}")

    def save_profile(self, raw_id, edipi, rank, last, first, mi, phone, pin_hash):
        mi = str(mi or "").strip()
        full_name = f"{last}, {first}"
        if mi: full_name += f" {mi}"

        self.profiles[raw_id] = {
            "Raw_ID": raw_id, "EDIPI": edipi, "Rank": rank,
            "Last_Name": last, "First_Name": first, "Middle_Initial": mi,
            "Phone": phone, "PIN_hash": pin_hash, "Full_Name": full_name
        }
        with open(PROFILES_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["Raw_ID","EDIPI","Rank","Last_Name","First_Name","Middle_Initial","Phone","PIN_hash"])
            writer.writeheader()
            for p in self.profiles.values():
                row = {k: p[k] for k in ["Raw_ID","EDIPI","Rank","Last_Name","First_Name","Middle_Initial","Phone","PIN_hash"]}
                writer.writerow(row)

    def find_profile_by_search(self, search):
        if not search: return None, None
        search = search.strip().lower()
        for raw_id, p in self.profiles.items():
            if (search in p.get("Full_Name", "").lower() or
                search == p.get("EDIPI") or
                search == raw_id):
                return raw_id, p
        return None, None

    # ==================== FULLY WORKING ADMIN FUNCTIONS ====================
    def admin_view_out(self):
        win = tk.Toplevel(self)
        win.title("Marines Currently on Liberty")
        win.configure(bg=BG_COLOR)
        win.geometry("1100x700")

        tk.Label(win, text="MARINES CURRENTLY ON LIBERTY", fg=USMC_GOLD, bg=BG_COLOR, font=("Helvetica", 20, "bold")).pack(pady=10)

        # Scrollable container
        canvas = tk.Canvas(win, bg=BG_COLOR, highlightthickness=0)
        scrollbar = tk.Scrollbar(win, orient="vertical", command=canvas.yview)
        scroll_frame = tk.Frame(canvas, bg=BG_COLOR)

        scroll_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True, padx=20, pady=10)
        scrollbar.pack(side="right", fill="y")

        # ==================== MOUSE WHEEL / TRACKPAD SUPPORT ====================
        def on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        def on_linux_scroll(event):
            if event.num == 4:
                canvas.yview_scroll(-1, "units")
            elif event.num == 5:
                canvas.yview_scroll(1, "units")

        canvas.bind_all("<MouseWheel>", on_mousewheel)      # Windows + macOS
        canvas.bind_all("<Button-4>", on_linux_scroll)      # Linux scroll up
        canvas.bind_all("<Button-5>", on_linux_scroll)      # Linux scroll down
        # ======================================================================

        found = False
        marine_count = 0

        for i in range(7):
            d = datetime.date.today() - datetime.timedelta(days=i)
            log_file = DATA_DIR / "daily_logs" / f"liberty_log_{d.isoformat()}.csv"
            if not log_file.exists():
                continue

            with open(log_file, "r", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if not row.get("Time_in") or row.get("Time_in").strip() == "":
                        found = True
                        marine_count += 1

                        row_frame = tk.Frame(scroll_frame, bg="#001F3F", relief="ridge", bd=2)
                        row_frame.pack(fill="x", pady=6, padx=10)

                        info = tk.Frame(row_frame, bg="#001F3F")
                        info.pack(side="left", fill="both", expand=True, padx=12, pady=8)

                        tk.Label(info, text=f"MARINE #{marine_count}", fg=USMC_GOLD, bg="#001F3F",
                                 font=("Helvetica", 11, "bold")).pack(anchor="w")
                        tk.Label(info, text=f"{row['Rank']} {row['Name']}", fg="white", bg="#001F3F",
                                 font=("Helvetica", 13, "bold")).pack(anchor="w")
                        tk.Label(info, text=f"EDIPI: {row['EDIPI']}", fg="#AAAAAA", bg="#001F3F",
                                 font=("Helvetica", 11)).pack(anchor="w")

                        # Look up phone from profiles using the proper EDIPI lookup
                        phone = "N/A"
                        prof = find_profile_by_edipi(row.get("EDIPI"))
                        if prof and prof.get("Phone"):
                            phone = format_phone(prof["Phone"])   # ensure nice formatting
                        tk.Label(info, text=f"Phone: {phone}", fg="#AAAAAA", bg="#001F3F",
                                 font=("Helvetica", 11)).pack(anchor="w")

                        tk.Label(info, text=f"Destination: {row.get('Destination', 'N/A')}", fg="white", bg="#001F3F",
                                 font=("Helvetica", 11)).pack(anchor="w")
                        tk.Label(info, text=f"Time Out: {row['Time_out']}", fg="#AAAAAA", bg="#001F3F",
                                 font=("Helvetica", 11)).pack(anchor="w")

                        buddy_name = row.get("Buddy_Name", "")
                        if buddy_name and buddy_name != "Self":
                            buddy_edipi = row.get("Buddy_EDIPI", "")
                            tk.Label(info, text=f"Buddy → {buddy_name} ({buddy_edipi})", fg=USMC_GOLD, bg="#001F3F",
                                     font=("Helvetica", 10)).pack(anchor="w")

                        # Small red Force button
                        btn_frame = tk.Frame(row_frame, bg="#001F3F")
                        btn_frame.pack(side="right", padx=12, pady=8)
                        tk.Button(btn_frame, text="FORCE\nCHECK-IN", bg="#8B0000", fg="white",
                                  font=("Helvetica", 9, "bold"), width=12, height=2,
                                  command=lambda e=row['EDIPI'], w=win: self.force_check_in_with_password(e, w)).pack()

        if not found:
            tk.Label(scroll_frame, text="No Marines currently on liberty.", fg=USMC_GOLD, bg=BG_COLOR,
                     font=("Helvetica", 14)).pack(pady=40)

        tk.Button(win, text="Close", bg=USMC_GOLD, fg=USMC_DARK, command=win.destroy).pack(pady=10)
    
    def admin_update_profile(self):
        search = self.themed_askstring("Update Profile", "Enter Name or EDIPI to search:")
        if not search: return
        raw_id, profile = self.find_profile_by_search(search)
        if not profile:
            self.themed_showerror("Not Found", "No matching Marine found.")
            return

        win = tk.Toplevel(self)
        win.title("Update Marine Profile")
        win.configure(bg=BG_COLOR)
        win.geometry("700x600")

        tk.Label(win, text=f"Editing: {profile['Full_Name']}", fg=USMC_GOLD, bg=BG_COLOR, font=("Helvetica", 16, "bold")).pack(pady=10)

        rank_var = tk.StringVar(value=profile["Rank"])
        last_var = tk.StringVar(value=profile["Last_Name"])
        first_var = tk.StringVar(value=profile["First_Name"])
        mi_var = tk.StringVar(value=profile.get("Middle_Initial",""))
        phone_var = tk.StringVar(value=profile["Phone"])

        for label, var in [("Rank", rank_var), ("Last Name", last_var), ("First Name", first_var),
                           ("Middle Initial", mi_var), ("Phone Number", phone_var)]:
            tk.Label(win, text=label + ":", fg=USMC_GOLD, bg=BG_COLOR, font=("Helvetica", 12)).pack(anchor="w", padx=50, pady=(10,0))
            tk.Entry(win, textvariable=var, font=("Helvetica", 14), width=40).pack(padx=50, pady=5)

        def save():
            formatted_phone = format_phone(phone_var.get())
            self.save_profile(raw_id, profile["EDIPI"], rank_var.get().strip(), last_var.get().strip(),
                              first_var.get().strip(), mi_var.get().strip(), formatted_phone,
                              profile["PIN_hash"])
            self.profiles = load_profiles()
            self.themed_showinfo("Success", "Profile updated successfully!")
            win.destroy()

        tk.Button(win, text="SAVE CHANGES", bg=USMC_GOLD, fg=USMC_DARK, font=("Helvetica", 14, "bold"), command=save).pack(pady=20)

    def admin_reset_pin(self):
        search = self.themed_askstring("Reset PIN", "Enter Name or EDIPI to search:")
        if not search: return
        raw_id, profile = self.find_profile_by_search(search)
        if not profile:
            self.themed_showerror("Not Found", "No matching Marine found.")
            return

        if not self.themed_askyesno("Confirm", f"Reset PIN for {profile['Full_Name']}?"):
            return

        new_pin = self.themed_askstring("New PIN", "Enter NEW 5-9 digit PIN:", show="*")
        if not new_pin or not new_pin.isdigit() or not (5 <= len(new_pin) <= 9):
            self.themed_showerror("Error", "PIN must be 5-9 digits.")
            return

        confirm = self.themed_askstring("Confirm PIN", "Re-enter the new PIN:", show="*")
        if new_pin != confirm:
            self.themed_showerror("Error", "PINs do not match.")
            return

        pin_hash = hash_secret(new_pin)
        self.save_profile(raw_id, profile["EDIPI"], profile["Rank"], profile["Last_Name"],
                          profile["First_Name"], profile.get("Middle_Initial",""),
                          profile["Phone"], pin_hash)
        self.profiles = load_profiles()
        self.themed_showinfo("Success", f"PIN for {profile['Full_Name']} has been reset.")

    def is_zyn_code(self, barcode):
        return barcode in ZYN_UPC_CODES

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
        tk.Label(dlg, text=message, fg=USMC_GOLD, bg=BG_COLOR, font=("Helvetica", 16, "bold"), wraplength=620).pack(pady=40)
        tk.Button(dlg, text="OK", bg=USMC_GOLD, fg=USMC_DARK, font=("Helvetica", 14, "bold"), width=15, height=2, command=dlg.destroy).pack(pady=20)
        dlg.bind("<Return>", lambda e: dlg.destroy())
        dlg.wait_window(dlg)

    def themed_showerror(self, title, message):
        dlg = self._create_themed_toplevel(title, USMC_RED)
        tk.Label(dlg, text=message, fg="white", bg=USMC_RED, font=("Helvetica", 16, "bold"), wraplength=620).pack(pady=40)
        tk.Button(dlg, text="OK", bg=USMC_GOLD, fg=USMC_DARK, font=("Helvetica", 14, "bold"), width=15, height=2, command=dlg.destroy).pack(pady=20)
        dlg.bind("<Return>", lambda e: dlg.destroy())
        dlg.wait_window(dlg)

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
        btn_frame.pack(pady=30)
        tk.Button(btn_frame, text="OK", bg=USMC_GOLD, fg=USMC_DARK,
                  font=("Helvetica", 14, "bold"), width=12, height=2,
                  command=submit).pack(side="left", padx=20)
        tk.Button(btn_frame, text="Cancel", bg=USMC_RED, fg="white",
                  font=("Helvetica", 14, "bold"), width=12, height=2,
                  command=cancel).pack(side="left", padx=20)

        # ==================== AUTO-FOCUS FIX ====================
        entry.bind("<Return>", lambda e: submit())
        dlg.bind("<Return>", lambda e: submit())
        dlg.bind("<Escape>", lambda e: cancel())

        # Force focus on the entry box AFTER the dialog is fully drawn
        def force_focus():
            entry.focus_force()
            entry.select_range(0, tk.END)   # selects the whole field (ready to type)
            entry.icursor(tk.END)

        dlg.after(10, force_focus)          # small delay guarantees it works
        dlg.grab_set()
        dlg.focus_force()
        dlg.wait_window(dlg)
        return result[0]
    
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

        # Improved Enter key support
        dlg.bind("<Return>", lambda e: yes())
        dlg.bind("<Escape>", lambda e: no())

        dlg.grab_set()
        dlg.focus_force()
        dlg.wait_window(dlg)
        return result[0]
    
    def build_main_screen(self):
        for widget in self.winfo_children(): widget.destroy()
        header = tk.Frame(self, bg=USMC_RED, height=140)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="UNITED STATES MARINE CORPS", fg=USMC_GOLD, bg=USMC_RED, font=("Helvetica", 28, "bold")).pack(pady=8)
        tk.Label(header, text="MARDET-MONTEREY LIBERTY KIOSK", fg="white", bg=USMC_RED, font=("Helvetica", 36, "bold")).pack()

        main = tk.Frame(self, bg=BG_COLOR)
        main.pack(fill="both", expand=True, padx=40, pady=20)
        self.main_frame = main

        tk.Label(main, text="SCAN THE FRONT OF YOUR CAC", fg=USMC_GOLD, bg=BG_COLOR, font=("Helvetica", 48, "bold")).pack(pady=40)
        tk.Label(main, text="Hold the FRONT of your CAC in front of the scanner", fg="white", bg=BG_COLOR, font=("Helvetica", 24)).pack()
        self.scan_entry = tk.Entry(main, font=("Helvetica", 12), width=80, justify="center")
        self.scan_entry.pack(pady=30)
        self.scan_entry.bind("<Return>", self.process_scan)
        self.status_label = tk.Label(main, text="", fg=USMC_GOLD, bg=BG_COLOR, font=("Helvetica", 18, "bold"), wraplength=1100)
        self.status_label.pack(pady=40)

        # ==================== FOOTER ====================
        footer = tk.Frame(self, bg=BG_COLOR)
        footer.pack(side="bottom", fill="x", pady=20, padx=30)

        tk.Label(footer, text="Scanner ready - FRONT of CAC only", fg="#666666", bg=BG_COLOR, font=("Helvetica", 12)).pack(side="left")

        # Left side - Visitor related buttons (gold to match other buttons)
        tk.Button(footer, text="VIEW VISITOR LIST", bg=USMC_GOLD, fg=USMC_DARK,
                  font=("Helvetica", 11, "bold"), width=18, height=1,
                  command=self.view_visitor_list).pack(side="left", padx=10)

        tk.Button(footer, text="CHECK IN/OUT VISITOR", bg=USMC_GOLD, fg=USMC_DARK,
                  font=("Helvetica", 11, "bold"), width=20, height=1,
                  command=self.launch_visitor_signin).pack(side="left")

        # Right side
        tk.Button(footer, text="VIEW MARINES OUT", bg=USMC_GOLD, fg=USMC_DARK,
                  font=("Helvetica", 11, "bold"), width=18, height=1,
                  command=self.admin_view_out).pack(side="right", padx=(0, 10))

        tk.Button(footer, text="ADMIN MENU", bg=USMC_GOLD, fg=USMC_DARK,
                  font=("Helvetica", 11, "bold"), width=14, height=1,
                  command=self.show_admin_menu).pack(side="right")

        self.focus_scan_entry()
    
    def focus_scan_entry(self):
        self.scan_entry.focus_set()
        self.scan_entry.delete(0, tk.END)

    def show_message(self, text, color=USMC_GOLD, seconds=8):
        self.status_label.config(text=text, fg=color)
        self.after(seconds*1000, lambda: self.status_label.config(text=""))

    def process_scan(self, event=None):
        raw = self.scan_entry.get()
        barcode = raw.strip()
        self.focus_scan_entry()

        if not barcode: return
        if barcode.upper() == "ADMIN":
            self.show_admin_menu()
            return
        if len(barcode) == 99:
            try:
                parsed = parse_cac_barcode(barcode)
            except Exception:
                self.show_message("❌ Parse error. Try scanning the front again.", USMC_RED)
                return

            if barcode in self.profiles:
                self.current_user = self.profiles[barcode].copy()
                self.handle_check_in_out()
            else:
                self.current_user = {"Raw_ID": barcode, "EDIPI": None, "Rank": parsed["Rank"], "Full_Name": parsed["Full_Name"], **parsed}
                self.show_registration_screen(parsed)

        elif self.is_zyn_code(barcode):
            self.show_zyn_easter_egg(barcode)
            return
        else:
            self.show_message("❌ Please scan the FRONT of your CAC only", USMC_RED)

    def show_registration_screen(self, parsed):
        reg_win = tk.Toplevel(self)
        reg_win.title("Register New Marine")
        reg_win.configure(bg=BG_COLOR)
        reg_win.geometry("900x700")
        reg_win.grab_set()
        reg_win.lift()
        reg_win.focus_force()

        tk.Label(reg_win, text="🆕 FIRST-TIME REGISTRATION", fg=USMC_GOLD, bg=BG_COLOR, font=("Helvetica", 24, "bold")).pack(pady=20)
        tk.Label(reg_win, text=f"Detected: {parsed['Rank']} {parsed['Full_Name']}", fg="white", bg=BG_COLOR, font=("Helvetica", 18)).pack(pady=10)

        last_var = tk.StringVar(value=parsed["Last_Name"])
        first_var = tk.StringVar(value=parsed["First_Name"])
        mi_var = tk.StringVar(value=parsed["Middle_Initial"])

        tk.Label(reg_win, text="Last Name:", fg=USMC_GOLD, bg=BG_COLOR, font=("Helvetica", 14)).pack(anchor="w", padx=50)
        tk.Entry(reg_win, textvariable=last_var, font=("Helvetica", 16), width=40).pack(pady=5)
        tk.Label(reg_win, text="First Name:", fg=USMC_GOLD, bg=BG_COLOR, font=("Helvetica", 14)).pack(anchor="w", padx=50)
        tk.Entry(reg_win, textvariable=first_var, font=("Helvetica", 16), width=40).pack(pady=5)
        tk.Label(reg_win, text="Middle Initial:", fg=USMC_GOLD, bg=BG_COLOR, font=("Helvetica", 14)).pack(anchor="w", padx=50)
        tk.Entry(reg_win, textvariable=mi_var, font=("Helvetica", 16), width=40).pack(pady=5)

        tk.Label(reg_win, text="10-digit EDIPI (from your CAC):", fg=USMC_GOLD, bg=BG_COLOR, font=("Helvetica", 14)).pack(anchor="w", padx=50, pady=(20,5))
        edipi_var = tk.StringVar()
        tk.Entry(reg_win, textvariable=edipi_var, font=("Helvetica", 16), width=40).pack(pady=5)

        tk.Label(reg_win, text="Phone Number:", fg=USMC_GOLD, bg=BG_COLOR, font=("Helvetica", 14)).pack(anchor="w", padx=50, pady=(20,5))
        phone_var = tk.StringVar()
        tk.Entry(reg_win, textvariable=phone_var, font=("Helvetica", 16), width=40).pack(pady=5)

        def finish_registration():
            try:
                edipi = edipi_var.get().strip()
                if not edipi.isdigit() or len(edipi) != 10:
                    self.themed_showerror("Error", "EDIPI must be exactly 10 digits")
                    return
                if not phone_var.get().strip():
                    self.themed_showerror("Error", "Phone number is required")
                    return

                pin = self.themed_askstring("PIN", "Choose 5-9 digit PIN:", show='*')
                if not pin or not pin.isdigit() or not (5 <= len(pin) <= 9):
                    self.themed_showerror("Error", "PIN must be 5-9 digits")
                    return

                pin_hash = hash_secret(pin)
                formatted_phone = format_phone(phone_var.get())
                self.save_profile(parsed["Raw_ID"], edipi, parsed["Rank"], last_var.get().strip(),
                                  first_var.get().strip(), mi_var.get().strip(),
                                  formatted_phone, pin_hash)

                self.profiles = load_profiles()
                self.current_user["EDIPI"] = edipi
                self.current_user["Raw_ID"] = parsed["Raw_ID"]

                reg_win.destroy()
                self.show_message(f"✅ {first_var.get()} {last_var.get()} registered! Oorah!", USMC_GOLD, 6)
                self.after(1500, self.handle_check_in_out)
            except Exception as e:
                self.themed_showerror("Error", f"Failed to save profile:\n{e}")

        tk.Button(reg_win, text="REGISTER MARINE", bg=USMC_GOLD, fg=USMC_DARK, font=("Helvetica", 18, "bold"), command=finish_registration).pack(pady=40)

    def handle_check_in_out(self):
        raw_id = self.current_user.get("Raw_ID")
        profile = self.profiles.get(raw_id)
        if not profile:
            self.show_message("❌ Profile not found. Please register again.", USMC_RED)
            self.after(2000, self.build_main_screen)
            return

        edipi = profile["EDIPI"]
        open_entry, log_file = find_open_entry(edipi)

        full_name = profile.get("Full_Name") or f"{profile.get('Last_Name', '')}, {profile.get('First_Name', '')}"

        if open_entry:
            pin = self.themed_askstring("CHECK IN", f"Enter PIN to CHECK IN\n{full_name}", show='*')
            if pin and self.verify_pin(profile, pin):
                self.update_check_in(edipi, log_file)
                self.show_message(f"✅ {full_name} CHECKED IN", USMC_GOLD, 6)
            else:
                self.themed_showerror("Invalid PIN", "❌ Invalid PIN")
        else:
            pin = self.themed_askstring("CHECK OUT", f"Enter PIN to CHECK OUT\n{full_name}", show='*')
            if not pin or not self.verify_pin(profile, pin):
                self.themed_showerror("Invalid PIN", "❌ Invalid PIN")
                return

            group = [self.current_user.copy()]
            while True:
                buddy_input = self.themed_askstring("BUDDY SCAN", "Scan next buddy's CAC\n(or leave blank to finish)")
                if not buddy_input or buddy_input.strip() == "":
                    break
                buddy = buddy_input.strip()
                if self.is_zyn_code(buddy):
                    self.show_zyn_easter_egg(buddy)
                    continue
                if len(buddy) != 99:
                    self.themed_showerror("Invalid Scan", "❌ Please scan the FRONT of a valid CAC only.")
                    continue
                try:
                    b_parsed = parse_cac_barcode(buddy)
                    b_raw_id = b_parsed["Raw_ID"]
                    if b_raw_id == raw_id:
                        self.themed_showerror("Duplicate", "You cannot add yourself as a buddy.")
                        continue
                    if b_raw_id in self.profiles:
                        # Pull FULL buddy data from profile (correct EDIPI, names, etc.)
                        buddy_data = self.profiles[b_raw_id].copy()
                    else:
                        # New buddy not yet registered. Do NOT create a profile with a
                        # guessable default PIN (the old code seeded "00000", which would
                        # let anyone check that Marine in/out). Log them from the parsed
                        # CAC data only; they register and pick their own PIN the first
                        # time they use the kiosk themselves.
                        buddy_data = dict(b_parsed)
                        buddy_data["EDIPI"] = ""  # unknown until they register in person
                    group.append(buddy_data)
                    self.show_message(f"✅ {buddy_data['Full_Name']} added to group", USMC_GOLD, 2)
                except Exception:
                    self.themed_showerror("Parse Error", "❌ Could not read CAC barcode.")
                    continue

            while True:
                destination = self.themed_askstring("DESTINATION", "Where are you going?")
                if destination and destination.strip():
                    break
                self.themed_showerror("Required Field", "Destination cannot be blank.")

            self.log_check_out(group, profile, destination)
            self.show_message(f"✅ Group of {len(group)} checked OUT", USMC_GOLD, 6)

        self.current_user = None
        self.after(3000, self.build_main_screen)

    def verify_pin(self, profile, pin):
        valid, needs_upgrade = verify_secret(pin, profile.get("PIN_hash", ""))
        if valid and needs_upgrade:
            try:
                self.save_profile(profile["Raw_ID"], profile["EDIPI"], profile["Rank"],
                                  profile["Last_Name"], profile["First_Name"],
                                  profile.get("Middle_Initial", ""), profile["Phone"],
                                  hash_secret(pin))
                self.profiles = load_profiles()
            except Exception as e:
                print(f"[PIN UPGRADE ERROR] {e}")
        return valid

    def find_open_entry(self, edipi):
        for i in range(7):
            d = datetime.date.today() - datetime.timedelta(days=i)
            log_file = DATA_DIR / "daily_logs" / f"liberty_log_{d.isoformat()}.csv"
            if not log_file.exists():
                continue
            with open(log_file, "r", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                for row in reversed(rows):
                    if row.get("EDIPI") == edipi and (row.get("Time_in") == "" or row.get("Time_in") is None or str(row.get("Time_in")).strip() == ""):
                        return row, log_file
        return None, None

    def update_check_in(self, edipi, log_file):
        rows = []
        updated = False
        with open(log_file, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            rows = list(reader)
            for row in rows:
                if row["EDIPI"] == edipi and (row.get("Time_in") == "" or row.get("Time_in") is None or str(row.get("Time_in")).strip() == "") and not updated:
                    row["Time_in"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    updated = True
        if updated:
            with open(log_file, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)

    def log_check_out(self, group_members, sponsor_profile, destination):
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_file = self.get_log_file()
        file_exists = log_file.exists()

        # Enhanced CSV with buddy's full identifying data (EDIPI, Last, First)
        fieldnames = [
            "Rank", "Name", "EDIPI", "Last_Name", "First_Name",
            "Buddy_Name", "Buddy_EDIPI", "Buddy_Last_Name", "Buddy_First_Name",
            "Destination", "Time_out", "Time_in"
        ]
        with open(log_file, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()

            sponsor_edipi = sponsor_profile.get("EDIPI", "")
            sponsor_last = sponsor_profile.get("Last_Name", "")
            sponsor_first = sponsor_profile.get("First_Name", "")
            sponsor_name = sponsor_profile.get("Full_Name", "")

            for member in group_members:
                member_edipi = member.get("EDIPI", "")
                is_self = bool(member_edipi and member_edipi == sponsor_edipi)
                if is_self:
                    buddy_name = "Self"
                    buddy_edipi = ""
                    buddy_last = ""
                    buddy_first = ""
                else:
                    buddy_name = sponsor_name
                    buddy_edipi = sponsor_edipi
                    buddy_last = sponsor_last
                    buddy_first = sponsor_first

                row = {
                    "Rank": member.get("Rank", ""),
                    "Name": member.get("Full_Name", ""),
                    "EDIPI": member_edipi,
                    "Last_Name": member.get("Last_Name", ""),
                    "First_Name": member.get("First_Name", ""),
                    "Buddy_Name": buddy_name,
                    "Buddy_EDIPI": buddy_edipi,
                    "Buddy_Last_Name": buddy_last,
                    "Buddy_First_Name": buddy_first,
                    "Destination": _csv_safe(destination),
                    "Time_out": now_str,
                    "Time_in": ""
                }
                writer.writerow(row)

    def show_zyn_easter_egg(self, barcode):
        pun = random.choice(ZYN_PUNS)
        msg = tk.Toplevel(self)
        msg.configure(bg=USMC_RED)
        tk.Label(msg, text="🚫 ZYN DETECTED", fg=USMC_GOLD, bg=USMC_RED, font=("Helvetica", 32, "bold")).pack(pady=30)
        tk.Label(msg, text=pun, fg="white", bg=USMC_RED, font=("Helvetica", 18)).pack(pady=10)
        tk.Label(msg, text="Please scan a valid Marine CAC only.", fg=USMC_GOLD, bg=USMC_RED, font=("Helvetica", 16)).pack(pady=20)
        tk.Button(msg, text="OK", bg=USMC_GOLD, fg=USMC_DARK, font=("Helvetica", 14), command=msg.destroy).pack(pady=20)
        msg.geometry("800x400")

    def show_admin_menu(self):
        if not self.verify_admin_password():
            return

        admin_win = tk.Toplevel(self)
        admin_win.title("ADMIN MENU")
        admin_win.configure(bg=BG_COLOR)
        admin_win.geometry("900x750")
        admin_win.grab_set()
        admin_win.lift()
        admin_win.focus_force()

        # ====================== SCROLLABLE ADMIN MENU ======================
        canvas = tk.Canvas(admin_win, bg=BG_COLOR, highlightthickness=0)
        scrollbar = tk.Scrollbar(admin_win, orient="vertical", command=canvas.yview)
        scroll_frame = tk.Frame(canvas, bg=BG_COLOR)

        scroll_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Mouse wheel support (consistent with other scrollable views)
        def on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        def on_linux_scroll(event):
            if event.num == 4:
                canvas.yview_scroll(-1, "units")
            elif event.num == 5:
                canvas.yview_scroll(1, "units")

        canvas.bind_all("<MouseWheel>", on_mousewheel)
        canvas.bind_all("<Button-4>", on_linux_scroll)
        canvas.bind_all("<Button-5>", on_linux_scroll)

        def cleanup_bindings():
            canvas.unbind_all("<MouseWheel>")
            canvas.unbind_all("<Button-4>")
            canvas.unbind_all("<Button-5>")

        admin_win.protocol("WM_DELETE_WINDOW", lambda: (cleanup_bindings(), admin_win.destroy()))

        # ====================== CONTENT ======================
        tk.Label(scroll_frame, text="🔐 ADMIN MENU", fg=USMC_GOLD, bg=BG_COLOR, font=("Helvetica", 28, "bold")).pack(pady=20)

        # Superuser-only buttons (only you see these)
        if getattr(self, 'is_superuser', False):
            tk.Button(scroll_frame, text="🔥 RESET ADMIN PASSWORD",
                      bg="#8B0000", fg="white",
                      font=("Helvetica", 16, "bold"), width=40, height=2,
                      command=lambda: (admin_win.destroy(), self.superuser_reset_admin_password())).pack(pady=8)
            tk.Button(scroll_frame, text="🔥 CHANGE SUPERUSER PASSWORD",
                      bg="#8B0000", fg="white",
                      font=("Helvetica", 16, "bold"), width=40, height=2,
                      command=lambda: (admin_win.destroy(), self.superuser_change_superuser_password())).pack(pady=8)
        elif not Path(SUPERUSER_HASH_FILE).exists():
            # Break-glass bootstrap: if no superuser password is set yet (e.g. the
            # exposed hash was removed and rotated), let an authenticated admin
            # establish one. The button disappears once the file exists.
            tk.Button(scroll_frame, text="⚙️ SET SUPERUSER PASSWORD (first-time setup)",
                      bg="#8B0000", fg="white",
                      font=("Helvetica", 16, "bold"), width=40, height=2,
                      command=lambda: (admin_win.destroy(), self.superuser_change_superuser_password())).pack(pady=8)

        # Regular admin options
        buttons = [
            ("1. Update Marine Profile", self.admin_update_profile),
            ("2. Reset Marine PIN", self.admin_reset_pin),
            ("3. Force Check-In Marine", self.force_check_in_from_admin),
            ("4. Change Admin Password", self.admin_change_password),
            ("5. Verify Backups (Integrity Check)", self.launch_backup_verifier),
            ("6. Export All Logs & Backups to USB", self.admin_export_to_usb),
            ("7. Exit Kiosk", self.admin_shutdown)
        ]
        for text, cmd in buttons:
            tk.Button(scroll_frame, text=text, bg=USMC_GOLD, fg=USMC_DARK,
                      font=("Helvetica", 16, "bold"), width=40, height=2,
                      command=lambda c=cmd: (admin_win.destroy(), c())).pack(pady=8)

        tk.Button(scroll_frame, text="Return to Kiosk", bg="#666666", fg="white",
                  font=("Helvetica", 14), command=admin_win.destroy).pack(pady=30)
    
    def superuser_reset_admin_password(self):
        new_pwd = self.themed_askstring("Reset Admin Password",
                                        "Enter NEW Admin Password:", show='*')
        if not new_pwd or len(new_pwd) < 4:
            self.themed_showerror("Error", "Password must be at least 4 characters.")
            return

        confirm = self.themed_askstring("Confirm", "Confirm NEW Admin Password:", show='*')
        if new_pwd != confirm:
            self.themed_showerror("Error", "Passwords do not match.")
            return

        new_hash = hash_secret(new_pwd)
        with open(ADMIN_HASH_FILE, "w", encoding="utf-8") as f:
            f.write(new_hash)

        self.log_admin_action("ADMIN_PW_RESET", actor="superuser")
        self.themed_showinfo("Success", "✅ Admin password has been reset.")

    def superuser_change_superuser_password(self):
        new_pwd = self.themed_askstring("Change Superuser Password",
                                        "Enter NEW Superuser Password:", show='*')
        if not new_pwd or len(new_pwd) < 8:
            self.themed_showerror("Error", "Superuser password must be at least 8 characters.")
            return

        confirm = self.themed_askstring("Confirm", "Confirm NEW Superuser Password:", show='*')
        if new_pwd != confirm:
            self.themed_showerror("Error", "Passwords do not match.")
            return

        new_hash = hash_secret(new_pwd)
        with open(SUPERUSER_HASH_FILE, "w", encoding="utf-8") as f:
            f.write(new_hash)

        self.log_admin_action("SUPERUSER_PW_CHANGE", actor="superuser")
        self.themed_showinfo("Success", "✅ Superuser password has been changed.\n\nOnly you know it now.")
    
    def launch_backup_verifier(self):
        try:
            subprocess.Popen([sys.executable, "backup_verifier.py"])
            self.themed_showinfo("Success", "✅ Backup Verifier opened in a new window.")
        except Exception as e:
            self.themed_showerror("Error", f"Could not launch verifier:\n{e}")

    def verify_admin_password(self):
        self.is_superuser = False
        for _ in range(3):
            pwd = self.themed_askstring("Admin Login", "Enter Admin Password:", show='*')
            if not pwd:
                return False

            # Check normal admin password
            try:
                admin_stored = ADMIN_HASH_FILE.read_text(encoding="utf-8")
            except FileNotFoundError:
                admin_stored = ""
            valid, needs_upgrade = verify_secret(pwd, admin_stored)
            if valid:
                if needs_upgrade:
                    try:
                        ADMIN_HASH_FILE.write_text(hash_secret(pwd), encoding="utf-8")
                    except Exception as e:
                        print(f"[ADMIN HASH UPGRADE ERROR] {e}")
                self.log_admin_action("LOGIN", actor="admin")
                return True

            # Check superuser password
            try:
                su_stored = Path(SUPERUSER_HASH_FILE).read_text(encoding="utf-8")
            except FileNotFoundError:
                su_stored = ""
            su_valid, su_upgrade = verify_secret(pwd, su_stored)
            if su_valid:
                self.is_superuser = True
                if su_upgrade:
                    try:
                        Path(SUPERUSER_HASH_FILE).write_text(hash_secret(pwd), encoding="utf-8")
                    except Exception as e:
                        print(f"[SUPERUSER HASH UPGRADE ERROR] {e}")
                self.log_admin_action("LOGIN", "superuser", actor="superuser")
                return True

            self.themed_showerror("Error", "Incorrect password")
        self.log_admin_action("LOGIN_FAILED", "3 incorrect attempts", actor="unknown")
        return False

    def admin_change_password(self):
        new_pwd = self.themed_askstring("Change Admin Password",
                                        "Enter NEW Admin Password (min 8 chars):", show='*')
        if not new_pwd or len(new_pwd) < 8:
            self.themed_showerror("Error", "Admin password must be at least 8 characters.")
            return
        confirm = self.themed_askstring("Confirm", "Confirm NEW Admin Password:", show='*')
        if new_pwd != confirm:
            self.themed_showerror("Error", "Passwords do not match.")
            return
        try:
            ADMIN_HASH_FILE.write_text(hash_secret(new_pwd), encoding="utf-8")
        except Exception as e:
            self.themed_showerror("Error", f"Could not save password:\n{e}")
            return
        self.log_admin_action("ADMIN_PW_CHANGE",
                              actor=("superuser" if getattr(self, 'is_superuser', False) else "admin"))
        self.themed_showinfo("Success", "✅ Admin password changed.")
        
    def force_check_in_from_admin(self):
        """Called from Admin Menu"""
        edipi = self.themed_askstring("Force Check-In", "Enter EDIPI of Marine to force check-in:")
        if edipi and edipi.strip():
            self.perform_force_checkin(edipi.strip())
    
    def force_check_in_with_password(self, edipi, parent_win=None):
        """Requires admin password BEFORE allowing force check-in (used by View Out buttons)"""
        if not self.verify_admin_password():
            return
        self.perform_force_checkin(edipi, parent_win)
    
    def perform_force_checkin(self, edipi, parent_win=None):
        """Core logic used by both Admin Menu and per-row buttons"""
        if not edipi:
            self.themed_showerror("Error", "EDIPI is required.")
            return

        reason = self.themed_askstring("Force Check-In Reason",
                                       "Enter reason for this force check-in\n(e.g. lost CAC, returned without scanning):")
        if not reason or not reason.strip():
            self.themed_showerror("Error", "A reason is required for force check-in.")
            return
        reason = reason.strip()

        confirm_msg = (f"Are you sure you want to FORCE CHECK-IN\n"
                       f"EDIPI {edipi} ?\n\n"
                       f"Reason: {reason}\n\n"
                       f"This action must also be recorded in the physical OOD logbook per unit policy.")
        if not self.themed_askyesno("CONFIRM FORCE CHECK-IN", confirm_msg):
            return

        # Search the same 7-day window the View-Out screen uses. A Marine who went
        # out last night and never scanned back in has their open entry in
        # YESTERDAY's log, so only checking today's file would miss the most
        # common force-check-in case.
        target_file = None
        fieldnames = None
        rows = []
        for i in range(7):
            d = datetime.date.today() - datetime.timedelta(days=i)
            log_file = DATA_DIR / "daily_logs" / f"liberty_log_{d.isoformat()}.csv"
            if not log_file.exists():
                continue
            with open(log_file, "r", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                fn = reader.fieldnames
                file_rows = list(reader)
            has_open = any(
                r.get("EDIPI") == edipi and (not r.get("Time_in") or str(r.get("Time_in")).strip() == "")
                for r in file_rows
            )
            if has_open:
                target_file, fieldnames, rows = log_file, fn, file_rows
                break

        if not target_file:
            self.themed_showerror("Error", f"No checked-out Marine found with EDIPI {edipi}.")
            return

        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for row in rows:
            if row.get("EDIPI") == edipi and (not row.get("Time_in") or str(row.get("Time_in")).strip() == ""):
                row["Time_in"] = now_str
                row["Destination"] = _csv_safe(f"{row.get('Destination', '')} [FORCE CHECK-IN: {reason}]".strip())

        with open(target_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        self.log_admin_action("FORCE_CHECKIN", f"EDIPI={edipi}; file={target_file.name}; reason={reason}",
                              actor=("superuser" if getattr(self, 'is_superuser', False) else "admin"))
        self.themed_showinfo("Success", f"✅ Marine {edipi} has been force checked-in.\nReason: {reason}")
        if parent_win:
            parent_win.destroy()
            self.admin_view_out()  # refresh the list

    def admin_export_to_usb(self):
        if not self.themed_askyesno("⚠️ PII/CUI WARNING",
            "This will export logs containing names, EDIPIs, and phone numbers.\n\n"
            "This data is PII/CUI. Only export to an approved, scanned USB.\n\n"
            "Continue?"):
            return

        start_date_str = simpledialog.askstring("Start Date", 
            "Enter START date for logs (YYYY-MM-DD)\nExample: 2026-05-20\n(Leave blank for ALL logs)", 
            parent=self)
        if start_date_str is None: return

        end_date_str = simpledialog.askstring("End Date", 
            "Enter END date for logs (YYYY-MM-DD)\nExample: 2026-05-24", 
            parent=self)
        if end_date_str is None: return

        export_all = not start_date_str.strip() and not end_date_str.strip()

        start_date = end_date = None
        if not export_all:
            try:
                start_date = datetime.datetime.strptime(start_date_str.strip(), "%Y-%m-%d").date()
                end_date = datetime.datetime.strptime(end_date_str.strip(), "%Y-%m-%d").date()
                if start_date > end_date:
                    self.themed_showerror("Invalid Range", "Start date cannot be after end date.")
                    return
            except ValueError:
                self.themed_showerror("Invalid Date", "Please use the format YYYY-MM-DD")
                return

        usb_path = filedialog.askdirectory(title="Select USB Flash Drive (root folder)", initialdir="/")
        if not usb_path: return

        usb_path = Path(usb_path)
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M")
        export_folder = usb_path / f"LibertyKiosk_Export_{timestamp}"
        export_folder.mkdir(parents=True, exist_ok=True)

        try:
            exported_logs = 0
            logs_src = DATA_DIR / "daily_logs"
            if logs_src.exists():
                logs_dest = export_folder / "daily_logs"
                logs_dest.mkdir(exist_ok=True)
                for log_file in logs_src.glob("liberty_log_*.csv"):
                    try:
                        date_str = log_file.stem.split("_")[-1]
                        file_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
                        if export_all or (start_date <= file_date <= end_date):
                            shutil.copy2(log_file, logs_dest / log_file.name)
                            exported_logs += 1
                    except ValueError:
                        shutil.copy2(log_file, logs_dest / log_file.name)
                        exported_logs += 1

            backups_src = DATA_DIR / "backups"
            if backups_src.exists():
                shutil.copytree(backups_src, export_folder / "backups", dirs_exist_ok=True)

            # Export visitor logs as part of the unified export
            visitor_src = VISITOR_LOGS_DIR
            if visitor_src.exists():
                visitor_dest = export_folder / "visitor_logs"
                visitor_dest.mkdir(exist_ok=True)
                for vlog in visitor_src.glob("visitor_log_*.csv"):
                    shutil.copy2(vlog, visitor_dest / vlog.name)

            for file in [PROFILES_FILE, ADMIN_HASH_FILE]:
                if file.exists():
                    shutil.copy2(file, export_folder / file.name)

            range_text = "ALL logs" if export_all else f"{start_date} to {end_date}"
            self.themed_showinfo("✅ Export Successful",
                f"Export completed!\n\n"
                f"Liberty logs exported: {exported_logs} files ({range_text})\n"
                f"Visitor logs included\n"
                f"Folder created: {export_folder}\n\n"
                "You may now safely remove the USB drive.")

            self.log_admin_action(
                "EXPORT", f"{exported_logs} liberty logs + visitor logs ({range_text}) -> {export_folder}",
                actor=("superuser" if getattr(self, 'is_superuser', False) else "admin"))
        except Exception as e:
            self.themed_showerror("Export Error", f"Could not export files:\n{str(e)}")

    def admin_shutdown(self):
        if self.themed_askyesno("Shutdown", "Close the kiosk completely?"):
            self.destroy()
            sys.exit(0)

    def start_daily_backup_scheduler(self):
        def scheduler_loop():
            while True:
                now = datetime.datetime.now()
                if now.hour >= 2:
                    next_run = now + datetime.timedelta(days=1)
                else:
                    next_run = now
                next_run = next_run.replace(hour=2, minute=0, second=0, microsecond=0)
                wait_seconds = (next_run - now).total_seconds()
                print(f"[BACKUP] Next backup scheduled in {wait_seconds/3600:.2f} hours")
                time.sleep(wait_seconds)
                try:
                    self.perform_log_backup()
                except Exception as e:
                    print(f"[BACKUP ERROR] {e}")
        thread = threading.Thread(target=scheduler_loop, daemon=True)
        thread.start()
        print("✅ Daily backup scheduler started")

    def perform_log_backup(self):
        yesterday = datetime.date.today() - datetime.timedelta(days=1)
        log_file = DATA_DIR / "daily_logs" / f"liberty_log_{yesterday.isoformat()}.csv"
        if not log_file.exists():
            return
        backup_dir = DATA_DIR / "backups"
        backup_file = backup_dir / f"liberty_log_{yesterday.isoformat()}.csv.bak"
        hash_file = backup_dir / f"liberty_log_{yesterday.isoformat()}.sha256"
        shutil.copy2(log_file, backup_file)
        with open(log_file, "rb") as f:
            file_hash = hashlib.sha256(f.read()).hexdigest()
        with open(hash_file, "w", encoding="utf-8") as f:
            f.write(file_hash)
        print(f"✅ BACKUP SUCCESS: {yesterday}")

    def launch_visitor_signin(self):
        """Launch the standalone Visitor Sign-In tool (like backup_verifier).
        The confirmation dialog will automatically close when the visitor tool is closed."""
        try:
            proc = subprocess.Popen([sys.executable, "visitor_signin.py"])

            # Create a custom dialog we can track and auto-close later
            dlg = self._create_themed_toplevel("Visitor Sign-In")
            tk.Label(dlg, text="✅ Visitor Sign-In tool opened in a new window.",
                     fg=USMC_GOLD, bg=BG_COLOR, font=("Helvetica", 16, "bold"),
                     wraplength=620).pack(pady=40)
            tk.Button(dlg, text="OK", bg=USMC_GOLD, fg=USMC_DARK,
                      font=("Helvetica", 14, "bold"), width=15, height=2,
                      command=dlg.destroy).pack(pady=20)

            # Store references so the poller can close the dialog
            self._visitor_launch_dialog = dlg
            self._visitor_process = proc

            # Start polling to auto-close the dialog when the visitor tool exits
            self.after(900, self._poll_visitor_process)

        except Exception as e:
            self.themed_showerror("Error", f"Could not launch visitor sign-in tool:\n{e}")

    def _poll_visitor_process(self):
        """Check if the launched visitor_signin.py process has exited.
        If so, automatically close the 'launched in new window' dialog."""
        if not hasattr(self, '_visitor_process') or self._visitor_process is None:
            return

        # poll() returns None if still running, exit code otherwise
        if self._visitor_process.poll() is not None:
            # Process has ended
            if hasattr(self, '_visitor_launch_dialog') and self._visitor_launch_dialog is not None:
                try:
                    self._visitor_launch_dialog.destroy()
                except Exception:
                    pass  # Dialog may have already been closed by user

            self._visitor_process = None
            self._visitor_launch_dialog = None
        else:
            # Still running — check again shortly
            self.after(900, self._poll_visitor_process)

    def view_visitor_list(self):
        """Show today's visitor sign-ins in a style matching 'View Marines Out'.
        Highlights visitors who have not yet checked out."""
        win = tk.Toplevel(self)
        win.title("Visitors Today")
        win.configure(bg=BG_COLOR)
        win.geometry("1050x680")

        tk.Label(win, text="VISITORS TODAY", fg=USMC_GOLD, bg=BG_COLOR, font=("Helvetica", 22, "bold")).pack(pady=10)

        # Scrollable container (same pattern as admin_view_out)
        canvas = tk.Canvas(win, bg=BG_COLOR, highlightthickness=0)
        scrollbar = tk.Scrollbar(win, orient="vertical", command=canvas.yview)
        scroll_frame = tk.Frame(canvas, bg=BG_COLOR)

        scroll_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True, padx=20, pady=10)
        scrollbar.pack(side="right", fill="y")

        # Mouse wheel support
        def on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        def on_linux_scroll(event):
            if event.num == 4:
                canvas.yview_scroll(-1, "units")
            elif event.num == 5:
                canvas.yview_scroll(1, "units")

        canvas.bind_all("<MouseWheel>", on_mousewheel)
        canvas.bind_all("<Button-4>", on_linux_scroll)
        canvas.bind_all("<Button-5>", on_linux_scroll)

        # Load only today's visitor log
        today = datetime.date.today().isoformat()
        log_file = DATA_DIR / "visitor logs" / f"visitor_log_{today}.csv"

        visitor_count = 0
        open_count = 0

        if not log_file.exists():
            tk.Label(scroll_frame, text="No visitors have signed in today.", fg=USMC_GOLD, bg=BG_COLOR,
                     font=("Helvetica", 16)).pack(pady=60)
        else:
            try:
                with open(log_file, "r", newline="", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    rows = list(reader)

                for row in rows:
                    visitor_count += 1
                    is_open = not str(row.get("Time_Out", "")).strip()

                    if is_open:
                        open_count += 1
                        bg_color = "#003300"          # Dark green for still signed in
                        status_color = "#00FF00"
                        status_text = "STILL SIGNED IN"
                    else:
                        bg_color = "#001F3F"          # Normal dark blue
                        status_color = "#AAAAAA"
                        status_text = f"Checked Out: {row.get('Time_Out', '')[:16]}"

                    row_frame = tk.Frame(scroll_frame, bg=bg_color, relief="ridge", bd=2)
                    row_frame.pack(fill="x", pady=6, padx=10)

                    info = tk.Frame(row_frame, bg=bg_color)
                    info.pack(side="left", fill="both", expand=True, padx=12, pady=8)

                    # Header
                    header_text = f"VISITOR #{visitor_count}"
                    if is_open:
                        header_text += "   ● " + status_text
                    tk.Label(info, text=header_text, fg=status_color if is_open else USMC_GOLD, bg=bg_color,
                             font=("Helvetica", 11, "bold")).pack(anchor="w")

                    # Main line: Host → Visitor
                    main_line = f"{row.get('Host_Rank','')} {row.get('Host_Name','')}  →  {row.get('Visitor_Name','')}"
                    tk.Label(info, text=main_line, fg="white", bg=bg_color,
                             font=("Helvetica", 14, "bold")).pack(anchor="w")

                    # Details
                    tk.Label(info, text=f"Location: {row.get('Building','')} - {row.get('Room','')}",
                             fg="#CCCCCC", bg=bg_color, font=("Helvetica", 11)).pack(anchor="w")

                    tk.Label(info, text=f"Signed In: {row.get('Timestamp','')[:19]}",
                             fg="#AAAAAA", bg=bg_color, font=("Helvetica", 11)).pack(anchor="w")

                    if not is_open:
                        tk.Label(info, text=status_text, fg="#AAAAAA", bg=bg_color,
                                 font=("Helvetica", 11)).pack(anchor="w")
                    else:
                        tk.Label(info, text=status_text, fg="#00FF00", bg=bg_color,
                                 font=("Helvetica", 12, "bold")).pack(anchor="w")

            except Exception as e:
                tk.Label(scroll_frame, text=f"Error reading visitor log: {e}", fg=USMC_RED, bg=BG_COLOR,
                         font=("Helvetica", 14)).pack(pady=40)

        # Summary at bottom
        if visitor_count > 0:
            summary = f"Total today: {visitor_count}   |   Still signed in: {open_count}"
            tk.Label(scroll_frame, text=summary, fg=USMC_GOLD, bg=BG_COLOR,
                     font=("Helvetica", 13, "bold")).pack(pady=15)

        tk.Button(win, text="Close", bg=USMC_GOLD, fg=USMC_DARK,
                  font=("Helvetica", 14, "bold"), width=14, height=1,
                  command=win.destroy).pack(pady=15)

if __name__ == "__main__":
    def ignore(sig, frame): pass
    signal.signal(signal.SIGINT, ignore)
    app = LibertyKiosk()
    app.mainloop()
