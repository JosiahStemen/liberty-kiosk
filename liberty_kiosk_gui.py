import csv
import datetime
import hashlib
import json
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

# Add the lib folder to path so we can import our modules cleanly
sys.path.insert(0, str(Path(__file__).parent / "lib"))

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
    get_last_row_hash,
    _compute_row_hash,
    record_hash_entry,
)

from kiosk_config import (
    ensure_data_directories,
    get_daily_log_path,
    get_visitor_log_path,
    DAILY_LOGS_DIR,
    VISITOR_LOGS_DIR,
    BACKUPS_DIR,
    INTEGRITY_LEDGER_FILE,
    SUPERUSER_HASH_FILE,
    AUDIT_FILE,
    DEFAULT_ADMIN_PASSWORD,
)

from kiosk_ui import ThemedDialogs

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


class LibertyKiosk(tk.Tk, ThemedDialogs):
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
        log_file = DATA_DIR / "daily_logs" / f"liberty_log_{today.isoformat()}.csv"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        return log_file

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

    # Themed dialog methods (_create_themed_toplevel, themed_showinfo, etc.)
    # are now provided by the ThemedDialogs mixin from kiosk_ui.py.
    # This removes ~100 lines of duplicated code while keeping identical behavior.

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
                # Refresh current_user *from the saved profile* (which now has the user-corrected
                # Last/First/Middle names instead of the original parsed UNKNOWNs). This ensures
                # that handle_check_in_out -> group = [self.current_user.copy()] -> log_check_out
                # writes the proper name into the daily log CSV (so "View Marines Out" shows it).
                if parsed["Raw_ID"] in self.profiles:
                    self.current_user = self.profiles[parsed["Raw_ID"]].copy()
                else:
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
        open_entry, log_file = self.find_open_entry(edipi)

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
            log_file.parent.mkdir(parents=True, exist_ok=True)
            with open(log_file, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)

    def log_check_out(self, group_members, sponsor_profile, destination):
        """Write checkout entries to today's liberty log (clean columns only).
        Hash chain is recorded separately in the integrity ledger.
        """
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_file = self.get_log_file()

        # Ensure the daily_logs directory exists (critical after fresh start or deletion)
        log_file.parent.mkdir(parents=True, exist_ok=True)

        file_exists = log_file.exists()

        # Clean fieldnames (no hash columns in the human-readable CSV)
        fieldnames = [
            "Rank", "Name", "EDIPI", "Last_Name", "First_Name",
            "Buddy_Name", "Buddy_EDIPI", "Buddy_Last_Name", "Buddy_First_Name",
            "Destination", "Time_out", "Time_in"
        ]

        previous_hash = get_last_row_hash("liberty", datetime.date.today().isoformat()) if log_file.exists() else ""

        try:
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

                    row_hash = _compute_row_hash(row, previous_hash)

                    # Record in separate ledger only
                    record_hash_entry(
                        log_type="liberty",
                        log_date=datetime.date.today().isoformat(),
                        original_row_key=f"{now_str}|{member_edipi}",
                        previous_hash=previous_hash,
                        row_hash=row_hash
                    )

                    writer.writerow(row)
                    previous_hash = row_hash

            return True
        except Exception as e:
            print(f"[LOG_CHECK_OUT ERROR] Failed to write log: {e}")
            self.themed_showerror("Logging Error", f"Failed to save checkout log:\n{e}")
            return False

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
            verifier_path = str(Path(__file__).parent / "tools" / "backup_verifier.py")
            subprocess.Popen([sys.executable, verifier_path])
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
        """Export logs for a date range as a court-ready, cryptographically hardened package.

        Structure:
            LibertyKiosk_Export_YYYY-MM-DD_to_YYYY-MM-DD/
                ├── Reports/
                │   └── Daily/                   (Liberty PDF per day only)
                │   └── Visitor_Logs_Report.pdf  (combined visitor report)
                └── Full_Integrity_Package/
                    ├── SourceData/              (raw daily_logs and visitor logs CSVs)
                    ├── Backups/                 (.bak + .sha256)
                    ├── Evidence/                (ChainOfCustody + MANIFEST + README)
                    └── Metadata/                (integrity_ledger + export info)
        """
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

        # === NEW ARCHIVE-FRIENDLY NAMING (always date range for easy searching on archive drives) ===
        if export_all:
            # For "ALL", discover the actual date range from the logs that will be exported
            min_date = None
            max_date = None
            logs_src = DATA_DIR / "daily_logs"
            if logs_src.exists():
                for f in logs_src.glob("liberty_log_*.csv"):
                    try:
                        d = datetime.datetime.strptime(f.stem.split("_")[-1], "%Y-%m-%d").date()
                        if min_date is None or d < min_date: min_date = d
                        if max_date is None or d > max_date: max_date = d
                    except:
                        continue
            if min_date and max_date:
                range_part = f"{min_date.isoformat()}_to_{max_date.isoformat()}"
            else:
                range_part = "All_Available"
        else:
            range_part = f"{start_date.isoformat()}_to_{end_date.isoformat()}"
        export_name = f"LibertyKiosk_Export_{range_part}"
        export_folder = usb_path / export_name
        export_folder.mkdir(parents=True, exist_ok=True)

        # === EXPORT STRUCTURE ===
        # - Reports/
        #     - Daily/ (Liberty PDFs per day only)
        #     - Visitor_Logs_Report.pdf (combined visitor report)
        # - Full_Integrity_Package/
        #     - SourceData/ (raw logs)
        #     - Backups/ (.bak + .sha256)
        #     - Evidence/ (manifest + CoC + README)
        #     - Metadata/ (ledger + export info)
        reports_dir = export_folder / "Reports"
        reports_daily_dir = reports_dir / "Daily"
        integrity_dir = export_folder / "Full_Integrity_Package"

        evidence_dir    = integrity_dir / "Evidence"
        source_data_dir = integrity_dir / "SourceData"
        backups_dir     = integrity_dir / "Backups"
        metadata_dir    = integrity_dir / "Metadata"

        reports_dir.mkdir(parents=True, exist_ok=True)
        reports_daily_dir.mkdir(parents=True, exist_ok=True)
        integrity_dir.mkdir(parents=True, exist_ok=True)
        evidence_dir.mkdir(parents=True, exist_ok=True)
        source_data_dir.mkdir(parents=True, exist_ok=True)
        backups_dir.mkdir(parents=True, exist_ok=True)
        metadata_dir.mkdir(parents=True, exist_ok=True)

        try:
            exported_backup_count = 0

            # 1. Copy filtered daily BACKUP .bak + .sha256 files (robust date extraction for .csv.bak)
            backups_src = DATA_DIR / "backups"
            if backups_src.exists():
                for bak_file in backups_src.glob("liberty_log_*.csv.bak"):
                    try:
                        # Robust handling of double extension .csv.bak
                        base = bak_file.name.replace("liberty_log_", "").split(".")[0]
                        file_date = datetime.datetime.strptime(base, "%Y-%m-%d").date()
                        if export_all or (start_date <= file_date <= end_date):
                            shutil.copy2(bak_file, backups_dir / bak_file.name)
                            hash_file = backups_src / (bak_file.stem + ".sha256")
                            if hash_file.exists():
                                shutil.copy2(hash_file, backups_dir / hash_file.name)
                            exported_backup_count += 1
                    except Exception:
                        continue

                for bak_file in backups_src.glob("visitor_log_*.csv.bak"):
                    try:
                        base = bak_file.name.replace("visitor_log_", "").split(".")[0]
                        file_date = datetime.datetime.strptime(base, "%Y-%m-%d").date()
                        if export_all or (start_date <= file_date <= end_date):
                            shutil.copy2(bak_file, backups_dir / bak_file.name)
                            hash_file = backups_src / (bak_file.stem + ".sha256")
                            if hash_file.exists():
                                shutil.copy2(hash_file, backups_dir / hash_file.name)
                    except Exception:
                        continue

            # 2. Copy the raw source logs (daily_logs + visitor logs) for the selected date range
            #    These are the actual human-readable records at the time of export.
            source_files_copied = 0
            daily_src = DATA_DIR / "daily_logs"
            visitor_src = VISITOR_LOGS_DIR

            target_daily = source_data_dir / "daily_logs"
            target_visitor = source_data_dir / "visitor_logs"
            target_daily.mkdir(parents=True, exist_ok=True)
            target_visitor.mkdir(parents=True, exist_ok=True)

            if daily_src.exists():
                for log_file in sorted(daily_src.glob("liberty_log_*.csv")):
                    try:
                        date_str = log_file.stem.split("_")[-1]
                        file_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
                        if export_all or (start_date <= file_date <= end_date):
                            shutil.copy2(log_file, target_daily / log_file.name)
                            source_files_copied += 1
                    except Exception:
                        continue

            if visitor_src.exists():
                for log_file in sorted(visitor_src.glob("visitor_log_*.csv")):
                    try:
                        date_str = log_file.stem.split("_")[-1]
                        file_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
                        if export_all or (start_date <= file_date <= end_date):
                            shutil.copy2(log_file, target_visitor / log_file.name)
                            source_files_copied += 1
                    except Exception:
                        continue

            # 4. Generate reports from the copied raw source data
            #    Daily reports for Liberty only (user prefers combined visitor report only)
            self._generate_daily_split_reports(source_data_dir, reports_daily_dir, start_date, end_date, export_all,
                                               generate_visitor_daily=False)

            # Generate combined Visitor report (no combined Liberty report is created)
            self._generate_visitor_logs_report(reports_dir, start_date, end_date, export_all, source_base_dir=source_data_dir)

            # 3. Copy supporting files into the integrity package
            if INTEGRITY_LEDGER_FILE.exists():
                shutil.copy2(INTEGRITY_LEDGER_FILE, metadata_dir / "integrity_ledger.csv")

            if PROFILES_FILE.exists():
                shutil.copy2(PROFILES_FILE, metadata_dir / "profiles.csv")
            if ADMIN_HASH_FILE.exists():
                shutil.copy2(ADMIN_HASH_FILE, metadata_dir / "admin.hash")

            # Create metadata file inside the integrity package
            export_meta = {
                "export_name": export_name,
                "created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "log_range": range_part,
                "source_files_copied": source_files_copied,
                "backups_copied": exported_backup_count,
                "kiosk_export_version": "2.3-with-raw-source"
            }
            with open(metadata_dir / "export_metadata.json", "w", encoding="utf-8") as f:
                json.dump(export_meta, f, indent=2)

            range_text = "ALL logs" if export_all else f"{start_date} to {end_date}"

            # 5. Write Chain of Custody + detailed README directly into Evidence/
            # (no root writes + no renames = no more WinError 183)
            dummy_manifest = "pending"
            self._generate_export_pdf(evidence_dir, range_text, exported_backup_count, manifest_hash=dummy_manifest)
            self._write_evidence_readme(evidence_dir, range_text, dummy_manifest)

            # 6. Build the cryptographic manifest on the final structure
            manifest_hash = self._create_export_manifest(export_folder)

            # Rebuild the Evidence files with the real manifest hash (with safety deletes)
            for fname in ["ChainOfCustody.pdf", "ChainOfCustody.txt", "README_Evidence.txt"]:
                p = evidence_dir / fname
                if p.exists():
                    p.unlink()

            self._generate_export_pdf(evidence_dir, range_text, exported_backup_count, manifest_hash=manifest_hash)
            self._write_evidence_readme(evidence_dir, range_text, manifest_hash)

            # Final feedback
            self.themed_showinfo("✅ Export Complete",
                f"Export finished successfully.\n\n"
                f"Folder: {export_name}\n"
                f"Log Range: {range_text}\n\n"
                f"MANIFEST.sha256: {manifest_hash[:16]}...\n\n"
                f"Layout:\n"
                f"• Reports/Daily/          ← Daily Liberty PDFs only\n"
                f"• Reports/Visitor_Logs_Report.pdf (combined visitor report)\n"
                f"• Full_Integrity_Package/ ← SourceData (raw logs) + Backups + Evidence + Metadata\n\n"
                f"Copy the whole folder to your archive drive.")

            self.log_admin_action(
                "EXPORT_HARDENED",
                f"Package {export_name} -> manifest {manifest_hash}",
                actor=("superuser" if getattr(self, 'is_superuser', False) else "admin"))

        except Exception as e:
            self.themed_showerror("Export Error", f"Could not complete hardened export:\n{str(e)}")
            import traceback
            traceback.print_exc()

    def _generate_export_pdf(self, export_folder: Path, range_text: str, exported_logs: int, manifest_hash: str = ""):
        """
        Generate a strong Chain of Custody PDF that is cryptographically bound to the manifest.
        This version is designed for court / forensic defensibility.
        """
        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
            from reportlab.lib import colors
            from reportlab.lib.units import inch

            pdf_path = export_folder / "ChainOfCustody.pdf"
            doc = SimpleDocTemplate(str(pdf_path), pagesize=letter)
            styles = getSampleStyleSheet()

            story = []

            # Title
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=styles['Heading1'],
                fontSize=18,
                textColor=colors.HexColor('#C8102E'),
                spaceAfter=12
            )
            story.append(Paragraph("MARDET-MONTEREY LIBERTY KIOSK", title_style))
            story.append(Paragraph("DIGITAL EVIDENCE EXPORT — CHAIN OF CUSTODY", styles['Heading2']))
            story.append(Spacer(1, 16))

            # Export metadata
            story.append(Paragraph(f"<b>Export Created:</b> {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles['Normal']))
            story.append(Paragraph(f"<b>Log Date Range:</b> {range_text}", styles['Normal']))
            story.append(Paragraph(f"<b>Liberty Log Files in Package:</b> {exported_logs}", styles['Normal']))
            story.append(Paragraph(f"<b>Full Export Folder:</b> {export_folder.name}", styles['Normal']))
            story.append(Spacer(1, 12))

            # Cryptographic Binding Section (the key improvement)
            story.append(Paragraph("<b>CRYPTOGRAPHIC PACKAGE INTEGRITY</b>", styles['Heading3']))
            if manifest_hash:
                story.append(Paragraph(
                    f"<b>Evidence Manifest Hash (MANIFEST.sha256):</b><br/>{manifest_hash}",
                    styles['Normal']
                ))
            else:
                story.append(Paragraph("<i>Manifest hash not available at generation time.</i>", styles['Normal']))
            story.append(Spacer(1, 8))
            story.append(Paragraph(
                "The SHA-256 hash above is the cryptographic fingerprint of MANIFEST.json, which contains "
                "the SHA-256 hash of every file in this export package (raw logs, backups, reports, ledger, etc.). "
                "Any alteration to any file after export will cause the manifest verification to fail.",
                styles['Normal']
            ))
            story.append(Spacer(1, 16))

            # Chain of Custody certification
            story.append(Paragraph("<b>CHAIN OF CUSTODY CERTIFICATION</b>", styles['Heading3']))
            story.append(Paragraph(
                "I certify under penalty of perjury that:<br/>"
                "• The files in this export package are true and accurate copies of the records that existed "
                "on the MARDET-Monterey Liberty Kiosk system at the time of export.<br/>"
                "• I did not alter, delete, add, or modify any data during the export process.<br/>"
                "• The cryptographic manifest hash recorded above was computed at the time this package was created.",
                styles['Normal']
            ))
            story.append(Spacer(1, 20))

            # Signature block
            story.append(Paragraph("<b>EXPORTER</b>", styles['Normal']))
            story.append(Paragraph("Name (Print): ________________________________________________", styles['Normal']))
            story.append(Spacer(1, 8))
            story.append(Paragraph("Rank / EDIPI: ________________________________________________", styles['Normal']))
            story.append(Spacer(1, 8))
            story.append(Paragraph("Signature: ____________________________________________________", styles['Normal']))
            story.append(Spacer(1, 8))
            story.append(Paragraph("Date / Time: __________________________________________________", styles['Normal']))
            story.append(Spacer(1, 16))

            story.append(Paragraph("<b>WITNESS (Recommended)</b>", styles['Normal']))
            story.append(Paragraph("Name / Rank: __________________________________________________", styles['Normal']))
            story.append(Spacer(1, 8))
            story.append(Paragraph("Signature: ____________________________________________________", styles['Normal']))
            story.append(Spacer(1, 8))
            story.append(Paragraph("Date / Time: __________________________________________________", styles['Normal']))

            story.append(Spacer(1, 24))
            story.append(Paragraph(
                "<i>This package contains raw source logs, daily backup files with their SHA-256 hashes, "
                "the integrity ledger, human-readable reports, and a complete cryptographic manifest. "
                "It is intended as a self-contained evidence production from the Liberty Kiosk system.</i>",
                styles['Normal']
            ))

            doc.build(story)
            self.log_admin_action("EXPORT_COC_PDF", f"ChainOfCustody.pdf created at {pdf_path}")

        except ImportError:
            # reportlab not installed — create a strong text version instead
            txt_path = export_folder / "ChainOfCustody.txt"
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write("MARDET-MONTEREY LIBERTY KIOSK\n")
                f.write("DIGITAL EVIDENCE EXPORT — CHAIN OF CUSTODY\n\n")
                f.write(f"Export Created: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Log Date Range: {range_text}\n")
                f.write(f"Liberty Log Files: {exported_logs}\n\n")
                if manifest_hash:
                    f.write(f"MANIFEST.sha256: {manifest_hash}\n\n")
                f.write("I certify that the files in this export are true copies of the kiosk records at time of export.\n")
                f.write("I did not alter any data during export.\n\n")
                f.write("EXPORTER Name: ________________________  EDIPI/Rank: ________________________\n")
                f.write("Signature: ________________________  Date/Time: ________________________\n\n")
                f.write("WITNESS Name: ________________________  Signature: ________________________\n")
                f.write(f"Export Folder: {target_dir.parent.name if target_dir.parent else target_dir.name}\n\n")
                f.write("CHAIN OF CUSTODY\n")
                f.write("I certify that the digital files contained in this export folder are true and accurate copies "
                        "of the original records from the Liberty Kiosk system at the time of export.\n\n")
                f.write("Exporter Name (Print): ________________________________\n\n")
                f.write("EDIPI / Rank: ________________________________\n\n")
                f.write("Signature: ________________________________\n\n")
                f.write("Date / Time: ________________________________\n\n")
                f.write("Witness (if required): ________________________________\n\n")
                f.write("Witness Signature: ________________________________\n")
            self.log_admin_action("EXPORT_TEXT_REPORT", f"Text report created at {txt_path} (reportlab not installed)")
        except Exception as e:
            self.log_admin_action("EXPORT_PDF_ERROR", str(e))

    def _generate_liberty_logs_report(self, export_folder: Path, start_date, end_date, export_all: bool, source_base_dir: Path = None) -> bool:
        """Generate a human-readable report (PDF if possible, otherwise .txt) for liberty logs.
        If source_base_dir is provided, read raw logs from there instead of live DATA_DIR.
        """
        # Always generate the text version first (reliable)
        text_ok = self._generate_liberty_logs_text_report(export_folder, start_date, end_date, export_all, source_base_dir)

        # Try PDF as bonus
        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib import colors
            from reportlab.lib.units import inch

            pdf_path = export_folder / "Liberty_Logs_Report.pdf"
            doc = SimpleDocTemplate(str(pdf_path), pagesize=letter)
            styles = getSampleStyleSheet()
            story = []

            story.append(Paragraph("MARDET-MONTEREY - Liberty Logs Report", styles['Heading1']))
            story.append(Paragraph(f"Date Range: {'ALL' if export_all else f'{start_date} to {end_date}'}", styles['Normal']))
            story.append(Spacer(1, 15))

            if source_base_dir:
                logs_src = source_base_dir / "daily_logs"
            else:
                logs_src = DATA_DIR / "daily_logs"
            found_any = False

            if logs_src.exists():
                for log_file in sorted(logs_src.glob("liberty_log_*.csv")):
                    try:
                        date_str = log_file.stem.split("_")[-1]
                        file_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
                        if not export_all and not (start_date <= file_date <= end_date):
                            continue

                        found_any = True
                        story.append(Paragraph(f"<b>Liberty Log - {date_str}</b>", styles['Heading2']))

                        with open(log_file, "r", newline="", encoding="utf-8") as f:
                            reader = csv.DictReader(f)
                            rows = list(reader)

                        if not rows:
                            story.append(Paragraph("No entries for this day.", styles['Normal']))
                            continue

                        table_data = [["Time Out", "Name", "EDIPI", "Destination", "Time In"]]
                        for row in rows[:60]:
                            table_data.append([
                                str(row.get("Time_out", ""))[:16],
                                str(row.get("Name", ""))[:22],
                                str(row.get("EDIPI", "")),
                                str(row.get("Destination", ""))[:22],
                                str(row.get("Time_in", ""))[:16] if row.get("Time_in") else "Still Out"
                            ])

                        t = Table(table_data, colWidths=[1.2*inch, 1.7*inch, 1.0*inch, 1.8*inch, 1.0*inch])
                        t.setStyle(TableStyle([
                            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#C8102E')),
                            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                            ('FONTSIZE', (0, 0), (-1, -1), 7),
                            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                        ]))
                        story.append(t)
                        story.append(Spacer(1, 12))

                    except Exception as e:
                        story.append(Paragraph(f"Error reading log for {date_str}: {e}", styles['Normal']))

            if not found_any:
                story.append(Paragraph("No liberty logs found for the selected date range.", styles['Normal']))

            doc.build(story)
            return True

        except Exception as e:
            print(f"[Liberty PDF Report Warning] Could not create PDF (using text instead): {e}")
            return text_ok  # Return whether the text report succeeded

    def _generate_visitor_logs_report(self, export_folder: Path, start_date, end_date, export_all: bool, source_base_dir: Path = None) -> bool:
        """Generate a human-readable report (PDF if possible, otherwise .txt) for visitor logs.
        If source_base_dir is provided, read raw logs from there instead of live data.
        """
        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib import colors
            from reportlab.lib.units import inch

            pdf_path = export_folder / "Visitor_Logs_Report.pdf"
            doc = SimpleDocTemplate(str(pdf_path), pagesize=letter)
            styles = getSampleStyleSheet()
            story = []

            story.append(Paragraph("MARDET-MONTEREY - Visitor Logs Report", styles['Heading1']))
            story.append(Paragraph(f"Date Range: {'ALL' if export_all else f'{start_date} to {end_date}'}", styles['Normal']))
            story.append(Spacer(1, 15))

            if source_base_dir:
                visitor_src = source_base_dir / "visitor_logs"
            else:
                visitor_src = VISITOR_LOGS_DIR
            found_any = False

            if visitor_src.exists():
                for log_file in sorted(visitor_src.glob("visitor_log_*.csv")):
                    try:
                        date_str = log_file.stem.split("_")[-1]
                        file_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
                        if not export_all and not (start_date <= file_date <= end_date):
                            continue

                        found_any = True
                        story.append(Paragraph(f"<b>Visitor Log - {date_str}</b>", styles['Heading2']))

                        with open(log_file, "r", newline="", encoding="utf-8") as f:
                            reader = csv.DictReader(f)
                            rows = list(reader)

                        if not rows:
                            story.append(Paragraph("No entries for this day.", styles['Normal']))
                            continue

                        table_data = [["Signed In", "Host", "Visitor", "Location", "Checked Out"]]
                        for row in rows[:50]:
                            table_data.append([
                                str(row.get("Timestamp", ""))[:16],
                                f"{row.get('Host_Rank','')} {row.get('Host_Name','')}"[:20],
                                str(row.get("Visitor_Name", ""))[:18],
                                f"{row.get('Building','')}-{row.get('Room','')}",
                                str(row.get("Time_Out", ""))[:16] if row.get("Time_Out") else "Still Signed In"
                            ])

                        t = Table(table_data, colWidths=[1.15*inch, 1.6*inch, 1.5*inch, 0.9*inch, 1.3*inch])
                        t.setStyle(TableStyle([
                            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#C8102E')),
                            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                            ('FONTSIZE', (0, 0), (-1, -1), 7),
                            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                        ]))
                        story.append(t)
                        story.append(Spacer(1, 12))

                    except Exception:
                        continue

            if not found_any:
                story.append(Paragraph("No visitor logs found for the selected date range.", styles['Normal']))

            doc.build(story)
            return True

        except ImportError:
            return self._generate_visitor_logs_text_report(export_folder, start_date, end_date, export_all)
        except Exception as e:
            print(f"[Visitor Report Error] {e}")
            import traceback
            traceback.print_exc()
            return False

    # --- Text fallback reports (always work) ---

    def _generate_liberty_logs_text_report(self, export_folder: Path, start_date, end_date, export_all: bool, source_base_dir: Path = None) -> bool:
        txt_path = export_folder / "Liberty_Logs_Report.txt"
        try:
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write("MARDET-MONTEREY - Liberty Logs Report\n")
                f.write(f"Date Range: {'ALL' if export_all else f'{start_date} to {end_date}'}\n\n")

                if source_base_dir:
                    logs_src = source_base_dir / "daily_logs"
                else:
                    logs_src = DATA_DIR / "daily_logs"
                if not logs_src.exists():
                    f.write("No liberty logs found.\n")
                    return True

                for log_file in sorted(logs_src.glob("liberty_log_*.csv")):
                    try:
                        date_str = log_file.stem.split("_")[-1]
                        file_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
                        if not export_all and not (start_date <= file_date <= end_date):
                            continue

                        f.write(f"=== Liberty Log - {date_str} ===\n")
                        with open(log_file, "r", newline="", encoding="utf-8") as lf:
                            reader = csv.DictReader(lf)
                            for row in reader:
                                f.write(f"Out: {row.get('Time_out','')[:16]} | {row.get('Name',''):<22} | EDIPI: {row.get('EDIPI',''):<12} | Dest: {row.get('Destination',''):<20} | In: {row.get('Time_in','') or 'Open'}\n")
                        f.write("\n")
                    except Exception:
                        continue
            return True
        except Exception:
            return False

    def _generate_visitor_logs_text_report(self, export_folder: Path, start_date, end_date, export_all: bool, source_base_dir: Path = None) -> bool:
        txt_path = export_folder / "Visitor_Logs_Report.txt"
        try:
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write("MARDET-MONTEREY - Visitor Logs Report\n")
                f.write(f"Date Range: {'ALL' if export_all else f'{start_date} to {end_date}'}\n\n")

                if source_base_dir:
                    visitor_src = source_base_dir / "visitor_logs"
                else:
                    visitor_src = VISITOR_LOGS_DIR
                if not visitor_src.exists():
                    f.write("No visitor logs found.\n")
                    return True

                for log_file in sorted(visitor_src.glob("visitor_log_*.csv")):
                    try:
                        date_str = log_file.stem.split("_")[-1]
                        file_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
                        if not export_all and not (start_date <= file_date <= end_date):
                            continue

                        f.write(f"=== Visitor Log - {date_str} ===\n")
                        with open(log_file, "r", newline="", encoding="utf-8") as lf:
                            reader = csv.DictReader(lf)
                            for row in reader:
                                checked_out = row.get("Time_Out", "") or "Still Signed In"
                                f.write(f"In: {row.get('Timestamp','')[:16]} | Host: {row.get('Host_Rank','')} {row.get('Host_Name',''):<18} | Visitor: {row.get('Visitor_Name',''):<18} | Loc: {row.get('Building','')}-{row.get('Room','')} | Out: {checked_out}\n")
                        f.write("\n")
                    except Exception:
                        continue
            return True
        except Exception:
            return False

    # ====================== NEW HARDENED EXPORT HELPERS ======================

    def _create_export_manifest(self, export_folder: Path) -> str:
        """
        Create a cryptographic manifest for the export package.

        - MANIFEST.json lists every file in the package (except itself and MANIFEST.sha256)
          along with its size and SHA-256 hash.
        - MANIFEST.sha256 contains the SHA-256 of the final MANIFEST.json.

        This allows a simple top-level integrity check:
            sha256(MANIFEST.json) == contents of MANIFEST.sha256

        Returns the SHA-256 of the final MANIFEST.json.
        """
        manifest_path = export_folder / "MANIFEST.json"
        manifest_hash_path = export_folder / "MANIFEST.sha256"

        files_list = []

        for file_path in sorted(export_folder.rglob("*")):
            if not file_path.is_file():
                continue

            # Exclude the two manifest files themselves from the list
            if file_path.name in ("MANIFEST.json", "MANIFEST.sha256"):
                continue

            try:
                rel_path = str(file_path.relative_to(export_folder)).replace("\\", "/")
                file_size = file_path.stat().st_size
                with open(file_path, "rb") as f:
                    file_hash = hashlib.sha256(f.read()).hexdigest()

                files_list.append({
                    "path": rel_path,
                    "size_bytes": file_size,
                    "sha256": file_hash
                })
            except Exception as e:
                files_list.append({
                    "path": str(file_path.relative_to(export_folder)),
                    "error": str(e)
                })

        manifest_data = {
            "export_folder": export_folder.name,
            "created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "file_count": len(files_list),
            "files": files_list
        }

        # Write the final manifest
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest_data, f, indent=2)

        # Compute hash of the manifest we just wrote (this is the authoritative value)
        with open(manifest_path, "rb") as f:
            manifest_hash = hashlib.sha256(f.read()).hexdigest()

        # Write the hash to the sidecar file
        with open(manifest_hash_path, "w", encoding="utf-8") as f:
            f.write(manifest_hash)

        return manifest_hash

    def _generate_daily_split_reports(self, source_data_dir: Path, reports_daily_dir: Path,
                                      start_date, end_date, export_all: bool,
                                      generate_visitor_daily: bool = True):
        """
        Generate separate PDF reports for each individual day.
        This is the primary format used for 6105s, NJPs, and routine admin actions.

        By default generates daily reports for both Liberty and Visitors.
        Set generate_visitor_daily=False to only generate daily Liberty reports
        (useful when only the combined visitor report is desired).
        """
        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.lib import colors
            from reportlab.lib.units import inch
        except ImportError:
            # If no reportlab, we skip daily PDFs (text versions are less critical here)
            return

        styles = getSampleStyleSheet()

        # Determine which dates to process
        dates_to_process = []
        if export_all:
            # Scan live daily_logs (or SourceData if provided)
            scan_dir = (source_data_dir / "daily_logs") if source_data_dir else (DATA_DIR / "daily_logs")
            for f in scan_dir.glob("liberty_log_*.csv"):
                try:
                    d = datetime.datetime.strptime(f.stem.split("_")[-1], "%Y-%m-%d").date()
                    dates_to_process.append(d)
                except:
                    continue
        else:
            current = start_date
            while current <= end_date:
                dates_to_process.append(current)
                current += datetime.timedelta(days=1)

        for day in sorted(dates_to_process):
            day_str = day.isoformat()

            # --- Liberty for this day ---
            base_dir = source_data_dir if source_data_dir else DATA_DIR
            lib_src = base_dir / "daily_logs" / f"liberty_log_{day_str}.csv"
            if lib_src.exists():
                try:
                    with open(lib_src, "r", newline="", encoding="utf-8") as f:
                        rows = list(csv.DictReader(f))

                    pdf_path = reports_daily_dir / f"{day_str}_Liberty_Report.pdf"
                    doc = SimpleDocTemplate(str(pdf_path), pagesize=letter)
                    story = []

                    story.append(Paragraph(f"MARDET-MONTEREY - Liberty Log - {day_str}", styles['Heading2']))
                    story.append(Spacer(1, 10))

                    if rows:
                        table_data = [["Time Out", "Name", "EDIPI", "Destination", "Time In"]]
                        for row in rows:
                            table_data.append([
                                str(row.get("Time_out", ""))[:16],
                                str(row.get("Name", ""))[:22],
                                str(row.get("EDIPI", "")),
                                str(row.get("Destination", ""))[:22],
                                str(row.get("Time_in", ""))[:16] if row.get("Time_in") else "Still Out"
                            ])
                        t = Table(table_data, colWidths=[1.2*inch, 1.7*inch, 1.0*inch, 1.8*inch, 1.0*inch])
                        t.setStyle(TableStyle([
                            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#C8102E')),
                            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                            ('FONTSIZE', (0, 0), (-1, -1), 7),
                            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                        ]))
                        story.append(t)
                    else:
                        story.append(Paragraph("No liberty entries for this date.", styles['Normal']))

                    doc.build(story)
                except Exception:
                    pass

            # --- Visitor for this day ---
            if generate_visitor_daily:
                vis_src = base_dir / "visitor_logs" / f"visitor_log_{day_str}.csv"
                if vis_src.exists():
                    try:
                        with open(vis_src, "r", newline="", encoding="utf-8") as f:
                            rows = list(csv.DictReader(f))

                        pdf_path = reports_daily_dir / f"{day_str}_Visitor_Report.pdf"
                        doc = SimpleDocTemplate(str(pdf_path), pagesize=letter)
                        story = []

                        story.append(Paragraph(f"MARDET-MONTEREY - Visitor Log - {day_str}", styles['Heading2']))
                        story.append(Spacer(1, 10))

                        if rows:
                            table_data = [["In Time", "Host", "Visitor", "Location", "Out Time"]]
                            for row in rows:
                                checked_out = row.get("Time_Out", "") or "Still Signed In"
                                table_data.append([
                                    str(row.get("Timestamp", ""))[:16],
                                    f"{row.get('Host_Rank','')} {row.get('Host_Name','')}"[:22],
                                    str(row.get("Visitor_Name", ""))[:22],
                                    f"{row.get('Building','')}-{row.get('Room','')}",
                                    checked_out[:16]
                                ])
                            t = Table(table_data, colWidths=[1.1*inch, 1.6*inch, 1.6*inch, 1.0*inch, 1.3*inch])
                            t.setStyle(TableStyle([
                                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#C8102E')),
                                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                                ('FONTSIZE', (0, 0), (-1, -1), 7),
                                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                            ]))
                            story.append(t)
                        else:
                            story.append(Paragraph("No visitor entries for this date.", styles['Normal']))

                        doc.build(story)
                    except Exception:
                        pass

    def _write_evidence_readme(self, target_dir: Path, range_text: str, manifest_hash: str):
        """Write clear instructions so anyone (lawyer, forensic examiner, court) knows how to use the package."""
        readme_path = target_dir / "README_Evidence.txt"

        content = f"""MARDET-MONTEREY LIBERTY KIOSK — DIGITAL EVIDENCE PACKAGE
================================================================

Export Folder: {target_dir.parent.name if target_dir.parent else target_dir.name}
Log Date Range: {range_text}
Manifest Hash (MANIFEST.sha256): {manifest_hash}
Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

FOLDER LAYOUT
-------------
Reports/
    - Daily/ folder
        One PDF per day for Liberty logs only
        (e.g. 2026-05-18_Liberty_Report.pdf).

    - Visitor_Logs_Report.pdf (combined visitor report for the selected date range)

Full_Integrity_Package/
    - SourceData/
        Raw daily_logs and visitor logs CSV files for the selected date range.

    - Backups/
        .bak files and corresponding .sha256 hash files for the selected date range.

    - Evidence/
        ChainOfCustody.pdf, MANIFEST.json, MANIFEST.sha256, and this README.

    - Metadata/
        integrity_ledger.csv (full ledger at time of export) and export_metadata.json.

The top-level folder name is based on the log date range being exported.

CONTENTS OF THIS PACKAGE
------------------------
- MANIFEST.json + MANIFEST.sha256
    Complete cryptographic inventory. Every file in this folder has a recorded SHA-256.
    To verify the entire package has not been altered since export:
        1. Compute SHA-256 of MANIFEST.json
        2. Compare it to the value in MANIFEST.sha256
        3. (Advanced) Recompute hashes of individual files and compare to MANIFEST.json

- SourceData/
    Raw CSV files of the daily liberty logs and visitor logs for the selected date range.

- Backups/
    Daily .bak snapshot files and their .sha256 hash sidecars for the selected date range.

- Reports/
    - ChainOfCustody.pdf
    - Daily/ folder containing one Liberty PDF per day in the range
    - Visitor_Logs_Report.pdf (combined visitor report for the range)

- Metadata/
    - integrity_ledger.csv (full ledger at time of export)
    - export_metadata.json

- profiles.csv and admin.hash (at time of export)

HOW TO VERIFY THIS PACKAGE (FORENSIC / COURT USE)
-------------------------------------------------
1. Verify the outer manifest:
   - SHA-256(MANIFEST.json) must exactly match the contents of MANIFEST.sha256

2. Verify the row-level hash chain (recommended):
   - Use the Backup Verifier tool (backup_verifier.py) against the Backups/ folder,
     pointing it at the Metadata/integrity_ledger.csv

3. Cross-check (using the generated reports):
   - The Reports/Daily/ PDFs are the human-readable version of what was exported.
   - You can verify the .bak files against the ledger using the verifier tool.

4. Chain of Custody:
   - The signed ChainOfCustody.pdf should be completed by the person who
     performed the export and (ideally) a witness.
   - The MANIFEST.sha256 value printed in the CoC document must match the actual file.

IMPORTANT NOTES FOR LEGAL USE
-----------------------------
This export package contains:
- The raw log files for the selected date range
- Daily backup files (.bak) and their SHA-256 hashes
- The integrity ledger at the time of export
- A cryptographic manifest of all files in the package
- A signed Chain of Custody document

The .bak files are daily snapshots created by the kiosk the morning after the logs were written.

QUESTIONS?
----------
Contact the unit S-1 or the administrator who performed this export.
"""

        with open(readme_path, "w", encoding="utf-8") as f:
            f.write(content)

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
            visitor_path = str(Path(__file__).parent / "tools" / "visitor_signin.py")
            proc = subprocess.Popen([sys.executable, visitor_path])

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
