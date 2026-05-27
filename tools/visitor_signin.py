"""
visitor_signin.py

Standalone Visitor Sign-In tool for MARDET-Monterey Liberty Kiosk.

Launched from the main kiosk GUI (or run directly with: python visitor_signin.py).

Requirements:
- The host Marine must **NOT** be currently checked out on liberty.
- Uses the exact same profile, hashing, CAC parsing, and logging logic as the main kiosk
  via liberty_common.py.

This is the "better route" architecture — shared code, separate tool.
"""

import csv
import tkinter as tk
from tkinter import messagebox, simpledialog
from pathlib import Path
import sys

# Add lib folder to path (so we can run this script from tools/ or root)
sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

# ====================== SHARED LOGIC ======================
from liberty_common import (
    USMC_RED,
    USMC_GOLD,
    USMC_DARK,
    BG_COLOR,
    DATA_DIR,
    PROFILES_FILE,
    parse_cac_barcode,
    load_profiles,
    find_open_entry,
    verify_secret,
    hash_secret,
    log_visitor_signin,
    find_profile_by_edipi,
    get_open_visitors_for_today,
    checkout_visitor,
)

# ====================== TOP-LEVEL FOCUS BEHAVIOR ======================
# Same trick used by backup_verifier.py so the tool comes to the front
# even when launched from the main fullscreen kiosk.


class VisitorSignInApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MARDET-MONTEREY - Visitor Sign-In")
        self.configure(bg=BG_COLOR)
        self.geometry("720x620")

        # Force to front (works even when launched from another Tkinter app)
        self.update_idletasks()
        self.lift()
        self.attributes("-topmost", True)
        self.focus_force()
        # Drop always-on-top after a short delay so it doesn't stay stuck
        self.after(300, lambda: self.attributes("-topmost", False))

        self.profiles = load_profiles()
        self.current_host = None          # dict with host info after successful PIN

        self.create_widgets()
        self.show_scan_step()

    def create_widgets(self):
        # Header
        header = tk.Frame(self, bg=USMC_RED, height=90)
        header.pack(fill="x")
        tk.Label(header, text="MARDET-MONTEREY", fg=USMC_GOLD, bg=USMC_RED,
                 font=("Helvetica", 22, "bold")).pack(pady=(8, 0))
        tk.Label(header, text="VISITOR SIGN-IN", fg="white", bg=USMC_RED,
                 font=("Helvetica", 16, "bold")).pack()

        # Main content area
        self.content = tk.Frame(self, bg=BG_COLOR)
        self.content.pack(fill="both", expand=True, padx=30, pady=15)

        # Status / instructions label (changes per step)
        self.status_label = tk.Label(self.content, text="", fg=USMC_GOLD, bg=BG_COLOR,
                                     font=("Helvetica", 14, "bold"), wraplength=650)
        self.status_label.pack(pady=(5, 10))

        # Host info display (populated after successful scan + PIN)
        self.host_frame = tk.Frame(self.content, bg="#002b4d", bd=2, relief="ridge")
        self.host_info_label = tk.Label(self.host_frame, text="", fg="white", bg="#002b4d",
                                        font=("Helvetica", 13), justify="left")
        self.host_info_label.pack(padx=15, pady=10)
        self.host_frame.pack(fill="x", pady=5)
        self.host_frame.pack_forget()   # hidden until we have a valid host

        # CAC scan entry (we keep it so the keyboard wedge works naturally)
        self.scan_frame = tk.Frame(self.content, bg=BG_COLOR)
        tk.Label(self.scan_frame, text="Scan Host Marine CAC (front of card):",
                 fg=USMC_GOLD, bg=BG_COLOR, font=("Helvetica", 12)).pack(anchor="w")
        self.scan_entry = tk.Entry(self.scan_frame, font=("Consolas", 16), width=50,
                                   bg="#003355", fg="white", insertbackground=USMC_GOLD)
        self.scan_entry.pack(pady=8)
        self.scan_entry.bind("<Return>", self.on_scan)
        self.scan_frame.pack(fill="x", pady=10)

        # PIN entry (shown after host is identified)
        self.pin_frame = tk.Frame(self.content, bg=BG_COLOR)
        tk.Label(self.pin_frame, text="Enter Host Marine's PIN (5-9 digits):",
                 fg=USMC_GOLD, bg=BG_COLOR, font=("Helvetica", 12)).pack(anchor="w")
        self.pin_entry = tk.Entry(self.pin_frame, font=("Consolas", 18), width=20, show="•",
                                  bg="#003355", fg="white", insertbackground=USMC_GOLD)
        self.pin_entry.pack(pady=8)
        self.pin_entry.bind("<Return>", self.on_pin_submit)
        tk.Button(self.pin_frame, text="VERIFY PIN & CONTINUE", bg=USMC_GOLD, fg=USMC_DARK,
                  font=("Helvetica", 13, "bold"), command=self.on_pin_submit).pack(pady=5)
        self.pin_frame.pack(fill="x", pady=5)
        self.pin_frame.pack_forget()

        # Visitor details form (final step)
        self.visitor_frame = tk.Frame(self.content, bg=BG_COLOR)

        tk.Label(self.visitor_frame, text="Visitor Full Name:", fg=USMC_GOLD, bg=BG_COLOR,
                 font=("Helvetica", 12)).pack(anchor="w", pady=(8, 2))
        self.visitor_name_var = tk.StringVar()
        tk.Entry(self.visitor_frame, textvariable=self.visitor_name_var, font=("Helvetica", 14),
                 width=45, bg="#003355", fg="white").pack()

        tk.Label(self.visitor_frame, text="Building Number:", fg=USMC_GOLD, bg=BG_COLOR,
                 font=("Helvetica", 12)).pack(anchor="w", pady=(12, 2))
        self.building_var = tk.StringVar()
        tk.Entry(self.visitor_frame, textvariable=self.building_var, font=("Helvetica", 14),
                 width=45, bg="#003355", fg="white").pack()

        tk.Label(self.visitor_frame, text="Room Number:", fg=USMC_GOLD, bg=BG_COLOR,
                 font=("Helvetica", 12)).pack(anchor="w", pady=(12, 2))
        self.room_var = tk.StringVar()
        tk.Entry(self.visitor_frame, textvariable=self.room_var, font=("Helvetica", 14),
                 width=45, bg="#003355", fg="white").pack()

        tk.Button(self.visitor_frame, text="✅ CONFIRM VISITOR SIGN-IN",
                  bg="#28a745", fg="white", font=("Helvetica", 15, "bold"), height=2,
                  command=self.confirm_visitor).pack(pady=20, fill="x")

        self.visitor_frame.pack(fill="x", pady=10)
        self.visitor_frame.pack_forget()

        # ====================== CHECKOUT VISITOR UI ======================
        self.checkout_frame = tk.Frame(self.content, bg=BG_COLOR)

        tk.Label(self.checkout_frame, text="Visitors currently signed in (no checkout time yet):",
                 fg=USMC_GOLD, bg=BG_COLOR, font=("Helvetica", 13, "bold")).pack(anchor="w", pady=5)

        self.visitor_listbox = tk.Listbox(self.checkout_frame, font=("Consolas", 12), height=8,
                                          bg="#002b4d", fg="white", selectbackground=USMC_GOLD)
        self.visitor_listbox.pack(fill="both", expand=True, pady=5)

        tk.Button(self.checkout_frame, text="CHECK OUT SELECTED VISITOR",
                  bg="#dc3545", fg="white", font=("Helvetica", 14, "bold"), height=2,
                  command=self.perform_visitor_checkout).pack(fill="x", pady=8)

        self.checkout_frame.pack(fill="both", expand=True, pady=5)
        self.checkout_frame.pack_forget()

        # ====================== THEMED DIALOG HELPERS ======================
        # These make popups match the red/gold USMC theme (Point 4)

        # Bottom buttons
        btn_bar = tk.Frame(self, bg=BG_COLOR)
        btn_bar.pack(fill="x", padx=30, pady=15)
        tk.Button(btn_bar, text="CHECK IN/OUT VISITOR", bg="#17a2b8", fg="white",
                  font=("Helvetica", 12, "bold"), width=22, command=self.show_checkin_out_choice).pack(side="left", padx=5)
        tk.Button(btn_bar, text="CLOSE", bg=USMC_RED, fg="white",
                  font=("Helvetica", 12), command=self.destroy).pack(side="right")

    # ====================== FLOW CONTROL ======================

    def show_scan_step(self):
        """Reset to the initial CAC scan step."""
        self.current_host = None

        self.host_frame.pack_forget()
        self.pin_frame.pack_forget()
        self.checkout_frame.pack_forget()
        self.visitor_frame.pack_forget()
        self.scan_frame.pack(fill="x", pady=10)

        self.status_label.config(
            text="Scan the HOST MARINE's CAC card now.",
            fg=USMC_GOLD
        )
        self.scan_entry.delete(0, tk.END)
        self.scan_entry.focus_set()

    def on_scan(self, event=None):
        raw = self.scan_entry.get().strip()
        if not raw:
            return

        try:
            parsed = parse_cac_barcode(raw)
            edipi = parsed.get("EDIPI") or raw

            # Look up the full profile (for PIN hash etc.)
            profile = self.profiles.get(raw) or self.profiles.get(edipi)
            if not profile:
                self.themed_showerror("Not Found", "This CAC is not registered in the system.\n"
                                                   "The Marine must register at the main kiosk first.")
                self.show_scan_step()
                return

            # Use the 10-digit EDIPI stored in the profile (what the logs actually contain)
            real_edipi = profile.get("EDIPI") or edipi

            # THE KEY REQUIREMENT:
            # Host Marine must NOT be checked out on liberty.
            open_entry, log_file = find_open_entry(real_edipi)
            if open_entry:
                name = profile.get("Full_Name", "This Marine")
                messagebox.showerror(
                    "Currently on Liberty",
                    f"{name} is currently checked OUT on liberty.\n\n"
                    "They must check back IN at the main kiosk before they can sign in a visitor."
                )
                self.show_scan_step()
                return

            # Valid host who is present (not on liberty) — proceed
            self.current_host = {
                "raw_id": raw,
                "edipi": real_edipi,   # the 10-digit one used in logs
                "rank": profile.get("Rank", parsed["Rank"]),
                "name": profile.get("Full_Name", parsed["Full_Name"]),
                "profile": profile
            }

            self.scan_frame.pack_forget()

            # === POINT 2: Smart check after scanning host ===
            open_visitors = [v for v in get_open_visitors_for_today()
                             if str(v.get("Host_EDIPI", "")).strip() == str(real_edipi).strip()]

            if open_visitors:
                # Themed choice dialog
                choice = self.themed_askyesno(
                    "Existing Visitors Found",
                    f"{self.current_host['rank']} {self.current_host['name']} currently has {len(open_visitors)} visitor(s) signed in.\n\n"
                    "Would you like to CHECK OUT a visitor?"
                )
                if choice:
                    self.show_checkout_step()
                    return
                # else fall through to sign in flow

            self.show_host_and_pin_step()

        except Exception as e:
            messagebox.showerror("Scan Error", f"Could not read CAC.\n\n{e}")
            self.show_scan_step()

    def show_host_and_pin_step(self):
        host = self.current_host
        self.host_info_label.config(
            text=f"HOST: {host['rank']} {host['name']}\nEDIPI: {host['edipi']}"
        )
        self.host_frame.pack(fill="x", pady=8)

        self.status_label.config(
            text="Verify the host information above, then enter their PIN.",
            fg=USMC_GOLD
        )

        self.pin_frame.pack(fill="x", pady=8)
        self.pin_entry.delete(0, tk.END)
        self.pin_entry.focus_set()

    def on_pin_submit(self, event=None):
        pin = self.pin_entry.get().strip()
        if not pin:
            return

        host = self.current_host
        profile = host["profile"]

        valid, needs_upgrade = verify_secret(pin, profile.get("PIN_hash", ""))
        if not valid:
            self.themed_showerror("Invalid PIN", "Incorrect PIN. Please try again.")
            self.pin_entry.delete(0, tk.END)
            self.pin_entry.focus_set()
            return

        if needs_upgrade:
            try:
                new_hash = hash_secret(pin)
                profile["PIN_hash"] = new_hash
                self._save_profile_upgrade(host["raw_id"], profile)
            except Exception as e:
                print(f"[PIN UPGRADE] {e}")

        # PIN good — move to visitor details
        self.pin_frame.pack_forget()
        self.status_label.config(
            text=f"Host verified: {host['rank']} {host['name']}\n"
                 "Now enter the visitor's details.",
            fg="#90EE90"
        )
        self.visitor_frame.pack(fill="x", pady=5)
        self.visitor_name_var.set("")
        self.building_var.set("")
        self.room_var.set("")

    def _save_profile_upgrade(self, raw_id, profile):
        """Minimal upgrade writer for the standalone tool."""
        # Re-read and rewrite only the changed row (keeps it simple)
        all_profiles = load_profiles()
        all_profiles[raw_id] = profile
        with open(PROFILES_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["Raw_ID", "EDIPI", "Rank", "Last_Name",
                                                   "First_Name", "Middle_Initial", "Phone", "PIN_hash"])
            writer.writeheader()
            for p in all_profiles.values():
                row = {k: p.get(k, "") for k in ["Raw_ID", "EDIPI", "Rank", "Last_Name",
                                                 "First_Name", "Middle_Initial", "Phone", "PIN_hash"]}
                writer.writerow(row)

    def confirm_visitor(self):
        visitor_name = self.visitor_name_var.get().strip()
        building = self.building_var.get().strip()
        room = self.room_var.get().strip()

        if not all([visitor_name, building, room]):
            self.themed_showerror("Missing Info", "All three fields are required.")
            return

        host = self.current_host
        log_visitor_signin(
            host["rank"],
            host["name"],
            host["edipi"],
            visitor_name,
            building,
            room
        )

        msg = (f"Visitor {visitor_name} signed in to {building}-{room}\n\n"
               f"by {host['rank']} {host['name']}")
        messagebox.showinfo("Success", msg)

        # Offer to do another or close
        if messagebox.askyesno("Another Visitor?", "Sign in another visitor for this host?"):
            self.show_scan_step()
        else:
            self.destroy()

    # ====================== THEMED DIALOGS (for consistent red/gold theme) ======================

    def _create_themed_dialog(self, title, bg_color=BG_COLOR):
        dlg = tk.Toplevel(self)
        dlg.title(title)
        dlg.configure(bg=bg_color)
        dlg.geometry("520x260")
        dlg.grab_set()
        dlg.lift()
        dlg.focus_force()
        dlg.transient(self)
        return dlg

    def themed_showinfo(self, title, message):
        dlg = self._create_themed_dialog(title)
        tk.Label(dlg, text=message, fg=USMC_GOLD, bg=BG_COLOR, font=("Helvetica", 14, "bold"),
                 wraplength=480, justify="center").pack(pady=30)
        tk.Button(dlg, text="OK", bg=USMC_GOLD, fg=USMC_DARK, font=("Helvetica", 13, "bold"),
                  width=14, height=1, command=dlg.destroy).pack(pady=10)
        dlg.bind("<Return>", lambda e: dlg.destroy())
        dlg.wait_window(dlg)

    def themed_showerror(self, title, message):
        dlg = self._create_themed_dialog(title, USMC_RED)
        tk.Label(dlg, text=message, fg="white", bg=USMC_RED, font=("Helvetica", 14, "bold"),
                 wraplength=480, justify="center").pack(pady=30)
        tk.Button(dlg, text="OK", bg=USMC_GOLD, fg=USMC_DARK, font=("Helvetica", 13, "bold"),
                  width=14, height=1, command=dlg.destroy).pack(pady=10)
        dlg.bind("<Return>", lambda e: dlg.destroy())
        dlg.wait_window(dlg)

    def themed_askyesno(self, title, message):
        """Returns True for Yes, False for No"""
        dlg = self._create_themed_dialog(title)
        result = [False]

        tk.Label(dlg, text=message, fg=USMC_GOLD, bg=BG_COLOR, font=("Helvetica", 14, "bold"),
                 wraplength=480, justify="center").pack(pady=25)

        def yes():
            result[0] = True
            dlg.destroy()

        def no():
            result[0] = False
            dlg.destroy()

        btn_frame = tk.Frame(dlg, bg=BG_COLOR)
        btn_frame.pack(pady=15)
        tk.Button(btn_frame, text="YES", bg=USMC_GOLD, fg=USMC_DARK, font=("Helvetica", 13, "bold"),
                  width=12, command=yes).pack(side="left", padx=15)
        tk.Button(btn_frame, text="NO", bg="#6c757d", fg="white", font=("Helvetica", 13, "bold"),
                  width=12, command=no).pack(side="left", padx=15)

        dlg.bind("<Return>", lambda e: yes())
        dlg.wait_window(dlg)
        return result[0]

    # ====================== CHECKOUT VISITOR FLOW ======================

    def show_checkin_out_choice(self):
        """Entry point for the single 'CHECK IN/OUT VISITOR' button."""
        self.show_scan_step()  # This will guide the user through host scan, then smart choice

    def show_checkout_step(self):
        """Switch UI to show current open visitors for checkout."""
        self.host_frame.pack_forget()
        self.pin_frame.pack_forget()
        self.visitor_frame.pack_forget()
        self.scan_frame.pack_forget()

        self.checkout_frame.pack(fill="both", expand=True, pady=5)

        self.status_label.config(
            text="Select a visitor below to check them out.",
            fg=USMC_GOLD
        )

        self.refresh_visitor_list()

    def refresh_visitor_list(self):
        """Reload the list of visitors who are still signed in."""
        self.visitor_listbox.delete(0, tk.END)
        visitors = get_open_visitors_for_today()

        if not visitors:
            self.visitor_listbox.insert(0, "No open visitors right now.")
            return

        for v in visitors:
            ts = str(v.get("Timestamp", ""))[:16]
            display = (f"{ts} | "
                       f"{v.get('Host_Rank', '')} {v.get('Host_Name', '')} → "
                       f"{v.get('Visitor_Name', '')} "
                       f"({v.get('Building', '')}-{v.get('Room', '')})")
            # Store the full row data in the listbox for later checkout
            self.visitor_listbox.insert(tk.END, display)
            self.visitor_listbox.itemconfig(tk.END, {"bg": "#003355"})

        self._current_open_visitors = visitors   # keep reference for checkout

    def perform_visitor_checkout(self):
        """Check out the selected visitor."""
        selection = self.visitor_listbox.curselection()
        if not selection:
            self.themed_showerror("Select Visitor", "Please select a visitor from the list.")
            return

        index = selection[0]
        if not hasattr(self, "_current_open_visitors") or index >= len(self._current_open_visitors):
            messagebox.showerror("Error", "Could not find visitor data.")
            return

        visitor = self._current_open_visitors[index]
        ts = visitor.get("Timestamp", "")
        host_edipi = visitor.get("Host_EDIPI", "")
        visitor_name = visitor.get("Visitor_Name", "")

        if not ts or not visitor_name:
            self.themed_showerror("Error", "Invalid visitor record.")
            return

        if self.themed_askyesno("Confirm Checkout",
                                f"Check out {visitor_name} (hosted by {visitor.get('Host_Rank')} {visitor.get('Host_Name')})?"):
            success = checkout_visitor(ts, host_edipi, visitor_name)
            if success:
                self.themed_showinfo("Checked Out", f"{visitor_name} has been checked out.")
                self.refresh_visitor_list()
            else:
                self.themed_showerror("Failed", "Could not update the record. Please try again.")


if __name__ == "__main__":
    # Make sure data directory exists (harmless if it already does)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    app = VisitorSignInApp()
    app.mainloop()
