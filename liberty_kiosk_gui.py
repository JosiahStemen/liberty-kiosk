import csv
import datetime
import hashlib
import random
import re
import signal
import sys
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, simpledialog

# USMC COLORS
USMC_RED = "#C8102E"
USMC_GOLD = "#FFCC00"
USMC_DARK = "#001F3F"
BG_COLOR = "#001F3F"

ZYN_PUNS = [
    "Monica Lewzynsky is NOT authorized liberty!",
    "Thomas Jefferzyn is NOT authorized liberty!",
    "Lynyrd Zynyrd is NOT authorized liberty!",
    "Zynjamin Franklin is NOT authorized liberty!",
    "Zyn Diesel is NOT authorized liberty!",
    "Zyndaya is NOT authorized liberty!",
    "Frank Zynatra is NOT authorized liberty!",

]

ZYN_UPC_CODES = {
    "609249900036", "609249900425", "609249900418", "609249901415",
    "609249902412", "609249902429", "609249903013", "609249903419",
    "609249903426", "609249904416", "609249904423", "609249906410",
    "609249906427", "609249907417", "609249907424", "609249914415",
    "609249914422",
}

DATA_DIR = Path("liberty_data")
PROFILES_FILE = DATA_DIR / "profiles.csv"
ADMIN_HASH_FILE = DATA_DIR / "admin.hash"
DEFAULT_ADMIN_PASSWORD = "LibertyKiosk2026!"

class LibertyKiosk(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MARDET-MONTEREY LIBERTY KIOSK")
        self.attributes("-fullscreen", True)
        self.configure(bg=BG_COLOR)
        self.protocol("WM_DELETE_WINDOW", self.ignore_close)
        self.bind("<Escape>", lambda e: self.show_admin_menu())

        self.init_files()
        self.profiles = self.load_profiles()
        self.current_user = None

        self.build_main_screen()

    def ignore_close(self): pass

    def init_files(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        (DATA_DIR / "daily_logs").mkdir(parents=True, exist_ok=True)

        if not PROFILES_FILE.exists():
            with open(PROFILES_FILE, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Raw_ID", "EDIPI", "Rank", "Last_Name", "First_Name", "Middle_Initial", "Phone", "PIN_hash"])

        if not ADMIN_HASH_FILE.exists():
            default_hash = hashlib.sha256(DEFAULT_ADMIN_PASSWORD.encode()).hexdigest()
            with open(ADMIN_HASH_FILE, "w", encoding="utf-8") as f:
                f.write(default_hash)

    def get_log_file(self):
        today = datetime.date.today()
        return DATA_DIR / "daily_logs" / f"liberty_log_{today.isoformat()}.csv"

    def load_profiles(self):
        profiles = {}
        if PROFILES_FILE.exists():
            with open(PROFILES_FILE, "r", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    mi = row.get("Middle_Initial", "").strip()
                    full = f"{row['Last_Name']}, {row['First_Name']}"
                    if mi: full += f" {mi}"
                    row["Full_Name"] = full
                    profiles[row["Raw_ID"]] = row
        return profiles

    def save_profile(self, raw_id, edipi, rank, last, first, mi, phone, pin_hash):
        print(f"DEBUG: Saving profile - Raw_ID={raw_id[:30]}... EDIPI={edipi}")
        mi = str(mi or "").strip()
        full_name = f"{last}, {first}"
        if mi:
            full_name += f" {mi}"

        self.profiles[raw_id] = {
            "Raw_ID": raw_id,
            "EDIPI": edipi,
            "Rank": rank,
            "Last_Name": last,
            "First_Name": first,
            "Middle_Initial": mi,
            "Phone": phone,
            "PIN_hash": pin_hash,
            "Full_Name": full_name
        }
        with open(PROFILES_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["Raw_ID","EDIPI","Rank","Last_Name","First_Name","Middle_Initial","Phone","PIN_hash"])
            writer.writeheader()
            for p in self.profiles.values():
                row = {k: p[k] for k in ["Raw_ID","EDIPI","Rank","Last_Name","First_Name","Middle_Initial","Phone","PIN_hash"]}
                writer.writerow(row)
        print("DEBUG: Profile saved to disk successfully (with Full_Name)")

    def is_zyn_code(self, barcode):
        """Return True ONLY if the scanned barcode exactly matches a real ZYN product UPC"""
        return barcode in ZYN_UPC_CODES

    # ==================== THEMED DIALOGS ====================
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

    def themed_askstring(self, title, prompt, show=None):
        dlg = self._create_themed_toplevel(title, BG_COLOR)
        result = [None]

        tk.Label(dlg, text=prompt, fg=USMC_GOLD, bg=BG_COLOR,
                 font=("Helvetica", 18, "bold"), wraplength=650).pack(pady=30)

        entry = tk.Entry(dlg, font=("Helvetica", 18), width=40, show=show, justify="center")
        entry.pack(pady=10)
        entry.focus_set()

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

        dlg.bind("<Return>", lambda e: submit())
        dlg.bind("<Escape>", lambda e: cancel())
        dlg.wait_window(dlg)
        return result[0]

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

    # =====================================================================

    def build_main_screen(self):
        for widget in self.winfo_children(): widget.destroy()

        header = tk.Frame(self, bg=USMC_RED, height=140)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="UNITED STATES MARINE CORPS", fg=USMC_GOLD, bg=USMC_RED, font=("Helvetica", 28, "bold")).pack(pady=8)
        tk.Label(header, text="MARDET-MONTEREY LIBERTY KIOSK", fg="white", bg=USMC_RED, font=("Helvetica", 36, "bold")).pack()

        main = tk.Frame(self, bg=BG_COLOR)
        main.pack(fill="both", expand=True, padx=40, pady=40)

        tk.Label(main, text="SCAN THE FRONT OF YOUR CAC", fg=USMC_GOLD, bg=BG_COLOR, font=("Helvetica", 48, "bold")).pack(pady=60)
        tk.Label(main, text="Hold the FRONT of your CAC in front of the scanner", fg="white", bg=BG_COLOR, font=("Helvetica", 24)).pack()

        self.scan_entry = tk.Entry(main, font=("Helvetica", 12), width=80, justify="center")
        self.scan_entry.pack(pady=30)
        self.scan_entry.bind("<Return>", self.process_scan)

        self.status_label = tk.Label(main, text="", fg=USMC_GOLD, bg=BG_COLOR, font=("Helvetica", 18, "bold"), wraplength=1100)
        self.status_label.pack(pady=40)

        footer = tk.Frame(self, bg=BG_COLOR)
        footer.pack(side="bottom", fill="x", pady=20, padx=30)
        tk.Label(footer, text="Scanner ready - FRONT of CAC only", fg="#666666", bg=BG_COLOR, font=("Helvetica", 12)).pack(side="left")

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

        print(f"\n=== SCAN RECEIVED ===\nLength: {len(barcode)}\nRaw: {repr(barcode)}\n")

        if not barcode: return
        if barcode.upper() == "ADMIN":
            self.show_admin_menu()
            return

        if len(barcode) == 99:
            try:
                parsed = self.parse_cac_barcode(barcode)
            except Exception:
                self.show_message("❌ Parse error. Try scanning the front again.", USMC_RED)
                return

            print(f"DEBUG: Parsed name = {parsed['Full_Name']}")

            if barcode in self.profiles:
                self.current_user = self.profiles[barcode].copy()
                print("DEBUG: Existing profile found → going to handle_check_in_out")
                self.handle_check_in_out()
            else:
                print("DEBUG: No profile found → showing registration screen")
                self.current_user = {"Raw_ID": barcode, "EDIPI": None, "Rank": parsed["Rank"], "Full_Name": parsed["Full_Name"], **parsed}
                self.show_registration_screen(parsed)

        elif self.is_zyn_code(barcode):
            self.show_zyn_easter_egg(barcode)
            return

        else:
            self.show_message("❌ Please scan the FRONT of your CAC only", USMC_RED)
            return

    def parse_cac_barcode(self, barcode):
        rank = "UNKNOWN"
        first = "UNKNOWN"
        last = "UNKNOWN"
        mi = ""

        rank_words = ["SGT", "CPL", "LCPL", "PFC", "PVT", "SSGT", "GYSGT", "MSGT", "MGYSGT", "SGTMAJ"]
        for word in rank_words:
            if word in barcode:
                rank = word
                break

        name_match = re.search(r'([A-Z][a-z]+)\s+([A-Z])([A-Z][a-z]+)', barcode)
        if name_match:
            first = name_match.group(1)
            mi = name_match.group(2)
            last = name_match.group(3)

        full_name = f"{last}, {first}"
        if mi:
            full_name += f" {mi}"

        return {
            "Raw_ID": barcode,
            "EDIPI": barcode,
            "Rank": rank,
            "Last_Name": last,
            "First_Name": first,
            "Middle_Initial": mi,
            "Full_Name": full_name
        }

    def show_registration_screen(self, parsed):
        reg_win = tk.Toplevel(self)
        reg_win.title("Register New Marine")
        reg_win.configure(bg=BG_COLOR)
        reg_win.geometry("900x700")
        reg_win.grab_set()
        reg_win.lift()
        reg_win.focus_force()

        tk.Label(reg_win, text="🆕 FIRST-TIME REGISTRATION", fg=USMC_GOLD, bg=BG_COLOR,
                 font=("Helvetica", 24, "bold")).pack(pady=20)

        tk.Label(reg_win, text=f"Detected: {parsed['Rank']} {parsed['Full_Name']}", 
                 fg="white", bg=BG_COLOR, font=("Helvetica", 18)).pack(pady=10)

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

                pin_hash = hashlib.sha256(pin.encode()).hexdigest()
                self.save_profile(parsed["Raw_ID"], edipi, parsed["Rank"], last_var.get().strip(),
                                  first_var.get().strip(), mi_var.get().strip(),
                                  phone_var.get().strip(), pin_hash)

                self.profiles = self.load_profiles()
                self.current_user["EDIPI"] = edipi
                self.current_user["Raw_ID"] = parsed["Raw_ID"]

                reg_win.destroy()
                self.show_message(f"✅ {first_var.get()} {last_var.get()} registered! Oorah!", USMC_GOLD, 6)
                self.after(1500, self.handle_check_in_out)

            except Exception as e:
                self.themed_showerror("Error", f"Failed to save profile:\n{e}")

        tk.Button(reg_win, text="REGISTER MARINE", bg=USMC_GOLD, fg=USMC_DARK,
                  font=("Helvetica", 18, "bold"), command=finish_registration).pack(pady=40)

    def handle_check_in_out(self):
        raw_id = self.current_user.get("Raw_ID")
        print(f"DEBUG: handle_check_in_out - Raw_ID = {raw_id[:50]}...")

        profile = self.profiles.get(raw_id)
        if not profile:
            print("DEBUG: Profile not found in memory!")
            self.show_message("❌ Profile not found. Please register again.", USMC_RED)
            self.after(2000, self.build_main_screen)
            return

        edipi = profile["EDIPI"]
        print(f"DEBUG: Looking for open entry using EDIPI = {edipi}")
        open_entry, log_file = self.find_open_entry(edipi)

        full_name = profile.get("Full_Name") or f"{profile.get('Last_Name', '')}, {profile.get('First_Name', '')}"

        if open_entry:
            print("DEBUG: Open entry FOUND → prompting for CHECK IN")
            pin = self.themed_askstring("CHECK IN", f"Enter PIN to CHECK IN\n{full_name}", show='*')
            if pin and self.verify_pin(profile, pin):
                self.update_check_in(edipi, log_file)
                self.show_message(f"✅ {full_name} CHECKED IN", USMC_GOLD, 6)
            else:
                self.themed_showerror("Invalid PIN", "❌ Invalid PIN")
        else:
            print("DEBUG: No open entry found → prompting for CHECK OUT")
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
                    self.themed_showerror("Invalid Scan", "❌ Please scan the FRONT of a valid CAC only.\n\nRandom text or other barcodes are not accepted.")
                    continue

                try:
                    b_parsed = self.parse_cac_barcode(buddy)
                    b_raw_id = b_parsed["Raw_ID"]

                    if b_raw_id == raw_id:
                        self.themed_showerror("Duplicate", "You cannot add yourself as a buddy.")
                        continue

                    if b_raw_id not in self.profiles:
                        print("DEBUG: New buddy detected → creating profile")
                        self.save_profile(b_raw_id, b_parsed["EDIPI"], b_parsed["Rank"], b_parsed["Last_Name"],
                                          b_parsed["First_Name"], b_parsed["Middle_Initial"],
                                          "UNKNOWN", hashlib.sha256("00000".encode()).hexdigest())
                        self.profiles = self.load_profiles()

                    group.append(b_parsed)
                    self.show_message(f"✅ {b_parsed['Full_Name']} added to group", USMC_GOLD, 2)

                except Exception:
                    self.themed_showerror("Parse Error", "❌ Could not read CAC barcode.\nPlease scan the FRONT of the card again.")
                    continue

            # ==================== REQUIRED DESTINATION ====================
            while True:
                destination = self.themed_askstring("DESTINATION", "Where are you going?")
                if destination and destination.strip():
                    break
                self.themed_showerror("Required Field", "Destination / Location cannot be blank.\nPlease enter where you are going.")
            # =================================================================

            self.log_check_out(group, full_name, destination)
            self.show_message(f"✅ Group of {len(group)} checked OUT", USMC_GOLD, 6)

        self.current_user = None
        self.after(3000, self.build_main_screen)

    def verify_pin(self, profile, pin):
        print("DEBUG: verify_pin called")
        return profile["PIN_hash"] == hashlib.sha256(pin.encode()).hexdigest()

    def find_open_entry(self, edipi):
        print(f"DEBUG: find_open_entry - Searching for open entry for EDIPI {edipi}")
        for i in range(7):
            d = datetime.date.today() - datetime.timedelta(days=i)
            log_file = DATA_DIR / "daily_logs" / f"liberty_log_{d.isoformat()}.csv"
            if not log_file.exists():
                print(f"  No log file for {d}")
                continue
            print(f"  Checking file: {log_file.name}")
            with open(log_file, "r", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                print(f"    Found {len(rows)} rows in file")
                for idx, row in enumerate(reversed(rows)):
                    row_edipi = row.get("EDIPI")
                    time_in = row.get("Time_in", "")
                    print(f"      Row {idx} - EDIPI={row_edipi} | Time_in='{time_in}'")
                    if row_edipi == edipi and (time_in == "" or time_in is None or str(time_in).strip() == ""):
                        print("      *** OPEN ENTRY FOUND ***")
                        return row, log_file
        print("DEBUG: No open entry found for this EDIPI")
        return None, None

    def update_check_in(self, edipi, log_file):
        print(f"DEBUG: Updating check-in for EDIPI {edipi} in {log_file.name}")
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
                    print("DEBUG: Check-in updated in row")
        if updated:
            with open(log_file, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
            print("DEBUG: Log file updated with check-in")
        else:
            print("DEBUG: No row updated with check-in")

    def log_check_out(self, group_members, sponsor_name, destination):
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_file = self.get_log_file()
        file_exists = log_file.exists()
        print(f"DEBUG: Logging check-out to {log_file.name} - {len(group_members)} members")
        with open(log_file, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["Rank", "Name", "EDIPI", "Buddy_Name", "Destination", "Time_out", "Time_in"])
                print("DEBUG: Created new log file with header")
            for member in group_members:
                buddy_name = "Self" if member.get("Full_Name") == sponsor_name else sponsor_name
                writer.writerow([
                    member["Rank"], member.get("Full_Name", ""), member["EDIPI"],
                    buddy_name, destination, now_str, ""
                ])
                print(f"DEBUG: Wrote check-out row for EDIPI {member['EDIPI']}")
        print("DEBUG: Check-out logged successfully")

    def show_zyn_easter_egg(self, barcode):
        pun = random.choice(ZYN_PUNS)
        msg = tk.Toplevel(self)
        msg.configure(bg=USMC_RED)
        msg.lift()
        msg.focus_force()
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
        admin_win.geometry("900x700")
        admin_win.grab_set()
        admin_win.lift()
        admin_win.focus_force()

        tk.Label(admin_win, text="🔐 ADMIN MENU", fg=USMC_GOLD, bg=BG_COLOR, font=("Helvetica", 28, "bold")).pack(pady=20)

        buttons = [
            ("1. View Marines Currently on Liberty", self.admin_view_out),
            ("2. Update Marine Profile", self.admin_update_profile),
            ("3. Reset Marine PIN", self.admin_reset_pin),
            ("4. Change Admin Password", self.admin_change_password),
            ("5. Exit Kiosk", self.admin_shutdown)
        ]
        for text, cmd in buttons:
            tk.Button(admin_win, text=text, bg=USMC_GOLD, fg=USMC_DARK,
                      font=("Helvetica", 16, "bold"), width=40, height=2,
                      command=lambda c=cmd: (admin_win.destroy(), c())).pack(pady=8)

        tk.Button(admin_win, text="Return to Kiosk", bg="#666666", fg="white",
                  font=("Helvetica", 14), command=admin_win.destroy).pack(pady=30)

    def verify_admin_password(self):
        for _ in range(3):
            pwd = self.themed_askstring("Admin Login", "Enter Admin Password:", show='*')
            if not pwd:
                return False
            with open(ADMIN_HASH_FILE, "r", encoding="utf-8") as f:
                stored = f.read().strip()
            if hashlib.sha256(pwd.encode()).hexdigest() == stored:
                return True
            self.themed_showerror("Error", "Incorrect password")
        return False

    def admin_view_out(self):
        out_text = "MARINES CURRENTLY ON LIBERTY\n" + "="*85 + "\n"
        out_text += f"{'RANK & NAME':<35} {'CHECKED OUT':<22} {'PHONE':<18} DESTINATION\n"
        out_text += "-"*85 + "\n"
        found = False

        for i in range(7):
            d = datetime.date.today() - datetime.timedelta(days=i)
            log_file = DATA_DIR / "daily_logs" / f"liberty_log_{d.isoformat()}.csv"
            if not log_file.exists():
                continue

            with open(log_file, "r", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if not row.get("Time_in"):
                        edipi = row.get("EDIPI")
                        _, profile = self.find_profile_by_search(edipi)
                        phone = profile.get("Phone", "Unknown") if profile else "Unknown"
                        time_out = row.get("Time_out", "Unknown")
                        rank = row.get("Rank", "")
                        name = row.get("Name", "Unknown")
                        destination = row.get("Destination", "Not Specified")

                        out_text += f"{rank} {name:<30} {time_out:<22} {phone:<18} {destination}\n"
                        found = True

        if not found:
            out_text += "No Marines currently on liberty."

        self.themed_showinfo("Currently on Liberty", out_text)

    def admin_update_profile(self):
        search = self.themed_askstring("Update Profile", "Enter EDIPI or Name:")
        if not search:
            return

        raw_id, profile = self.find_profile_by_search(search)
        if not profile:
            self.themed_showerror("Not Found", "Marine not found")
            return

        update_win = tk.Toplevel(self)
        update_win.title("Update Marine Profile")
        update_win.configure(bg=BG_COLOR)
        update_win.geometry("900x700")
        update_win.grab_set()
        update_win.lift()
        update_win.focus_force()

        tk.Label(update_win, text="✏️ UPDATE MARINE PROFILE", fg=USMC_GOLD, bg=BG_COLOR,
                 font=("Helvetica", 24, "bold")).pack(pady=20)

        tk.Label(update_win, text=f"Current: {profile.get('Full_Name', profile.get('Last_Name', ''))}", 
                 fg="white", bg=BG_COLOR, font=("Helvetica", 18)).pack(pady=10)

        rank_var = tk.StringVar(value=profile.get("Rank", ""))
        last_var = tk.StringVar(value=profile.get("Last_Name", ""))
        first_var = tk.StringVar(value=profile.get("First_Name", ""))
        mi_var = tk.StringVar(value=profile.get("Middle_Initial", ""))
        edipi_var = tk.StringVar(value=profile.get("EDIPI", ""))
        phone_var = tk.StringVar(value=profile.get("Phone", ""))

        tk.Label(update_win, text="Rank:", fg=USMC_GOLD, bg=BG_COLOR, font=("Helvetica", 14)).pack(anchor="w", padx=50)
        tk.Entry(update_win, textvariable=rank_var, font=("Helvetica", 16), width=40).pack(pady=5)

        tk.Label(update_win, text="Last Name:", fg=USMC_GOLD, bg=BG_COLOR, font=("Helvetica", 14)).pack(anchor="w", padx=50)
        tk.Entry(update_win, textvariable=last_var, font=("Helvetica", 16), width=40).pack(pady=5)

        tk.Label(update_win, text="First Name:", fg=USMC_GOLD, bg=BG_COLOR, font=("Helvetica", 14)).pack(anchor="w", padx=50)
        tk.Entry(update_win, textvariable=first_var, font=("Helvetica", 16), width=40).pack(pady=5)

        tk.Label(update_win, text="Middle Initial:", fg=USMC_GOLD, bg=BG_COLOR, font=("Helvetica", 14)).pack(anchor="w", padx=50)
        tk.Entry(update_win, textvariable=mi_var, font=("Helvetica", 16), width=40).pack(pady=5)

        tk.Label(update_win, text="10-digit EDIPI:", fg=USMC_GOLD, bg=BG_COLOR, font=("Helvetica", 14)).pack(anchor="w", padx=50, pady=(20,5))
        tk.Entry(update_win, textvariable=edipi_var, font=("Helvetica", 16), width=40).pack(pady=5)

        tk.Label(update_win, text="Phone Number:", fg=USMC_GOLD, bg=BG_COLOR, font=("Helvetica", 14)).pack(anchor="w", padx=50, pady=(20,5))
        tk.Entry(update_win, textvariable=phone_var, font=("Helvetica", 16), width=40).pack(pady=5)

        def finish_update():
            try:
                new_edipi = edipi_var.get().strip()
                if not new_edipi.isdigit() or len(new_edipi) != 10:
                    self.themed_showerror("Error", "EDIPI must be exactly 10 digits", parent=update_win)
                    return
                if not phone_var.get().strip():
                    self.themed_showerror("Error", "Phone number is required", parent=update_win)
                    return

                pin_hash = profile.get("PIN_hash", hashlib.sha256("00000".encode()).hexdigest())

                self.save_profile(raw_id, new_edipi, rank_var.get().strip(),
                                  last_var.get().strip(), first_var.get().strip(),
                                  mi_var.get().strip(), phone_var.get().strip(), pin_hash)

                self.profiles = self.load_profiles()
                update_win.destroy()
                self.themed_showinfo("Success", f"✅ Profile for {first_var.get()} {last_var.get()} updated!")
            except Exception as e:
                self.themed_showerror("Error", f"Failed to update profile:\n{e}")

        tk.Button(update_win, text="UPDATE PROFILE", bg=USMC_GOLD, fg=USMC_DARK,
                  font=("Helvetica", 18, "bold"), command=finish_update).pack(pady=40)

    def admin_reset_pin(self):
        search = self.themed_askstring("Reset PIN", "Enter EDIPI or Name:")
        if not search:
            return

        raw_id, profile = self.find_profile_by_search(search)
        if not profile:
            self.themed_showerror("Not Found", "Marine not found")
            return

        new_pin = self.themed_askstring("New PIN", f"Enter new 5-9 digit PIN for\n{profile.get('Full_Name', profile.get('Last_Name',''))}:", show='*')
        if new_pin and new_pin.isdigit() and 5 <= len(new_pin) <= 9:
            pin_hash = hashlib.sha256(new_pin.encode()).hexdigest()
            self.save_profile(raw_id, profile["EDIPI"], profile["Rank"], profile["Last_Name"],
                              profile["First_Name"], profile.get("Middle_Initial",""),
                              profile["Phone"], pin_hash)
            self.profiles = self.load_profiles()
            self.themed_showinfo("Success", f"PIN reset successfully for {profile.get('Full_Name') or profile.get('Last_Name') or 'Marine'}!")
        else:
            self.themed_showerror("Error", "Invalid PIN (must be 5-9 digits)")

    def admin_change_password(self):
        new_pwd = self.themed_askstring("New Password", "Enter NEW Admin Password:", show='*')
        if not new_pwd:
            return
        confirm = self.themed_askstring("Confirm", "Confirm NEW Admin Password:", show='*')
        if new_pwd == confirm and len(new_pwd) >= 6:
            new_hash = hashlib.sha256(new_pwd.encode()).hexdigest()
            with open(ADMIN_HASH_FILE, "w", encoding="utf-8") as f:
                f.write(new_hash)
            self.themed_showinfo("Success", "Admin password changed!")
        else:
            self.themed_showerror("Error", "Passwords do not match or too short")

    def admin_shutdown(self):
        if self.themed_askyesno("Shutdown", "Close the kiosk completely?"):
            self.destroy()
            sys.exit(0)

    def find_profile_by_search(self, search):
        if not search:
            return None, None
        search = search.strip()
        search_lower = search.lower()
        for raw_id, p in self.profiles.items():
            if raw_id == search or p.get("EDIPI") == search or search_lower in p.get("Full_Name", "").lower():
                return raw_id, p
        return None, None

if __name__ == "__main__":
    def ignore(sig, frame): pass
    signal.signal(signal.SIGINT, ignore)
    app = LibertyKiosk()
    app.mainloop()
