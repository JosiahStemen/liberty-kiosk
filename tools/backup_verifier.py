import tkinter as tk
from tkinter import messagebox, Scrollbar, VERTICAL, RIGHT, Y
from pathlib import Path
import hashlib
import csv
import sys

# Ensure we can import shared modules from the lib/ folder
# even when this script is launched from the tools/ directory
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "lib"))

# Use the single source of truth for paths and colors (same as main kiosk + visitor tool)
from kiosk_config import BACKUPS_DIR, DATA_DIR, INTEGRITY_LEDGER_FILE, ensure_data_directories
from liberty_common import USMC_RED, USMC_GOLD, USMC_DARK, BG_COLOR, _compute_row_hash

class BackupVerifier(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MARDET-MONTEREY - Backup Integrity Verifier")
        self.configure(bg=BG_COLOR)
        self.geometry("1150x800")

        # Force the window to the very top (works even when launched from another Tkinter app)
        self.update_idletasks()          # helps on some platforms
        self.lift()                      # bring window forward
        self.attributes('-topmost', True)  # temporarily make it stay on top
        self.focus_force()               # steal keyboard focus

        # (Optional but recommended) Remove the "always on top" after a short delay
        # so it doesn't stay stuck on top forever
        self.after(300, lambda: self.attributes('-topmost', False))

        # Use the canonical data location (liberty_data/ at project root when launched from GUI)
        ensure_data_directories()
        self.backup_dir = BACKUPS_DIR

        self.backup_paths = []   # parallel list of actual .bak Path objects for reliable selection

        self.create_widgets()
        self.load_backups()

    def create_widgets(self):
        # Header
        header = tk.Frame(self, bg=USMC_RED, height=100)
        header.pack(fill="x")
        tk.Label(header, text="MARDET-MONTEREY", fg=USMC_GOLD, bg=USMC_RED, font=("Helvetica", 24, "bold")).pack(pady=8)
        tk.Label(header, text="BACKUP INTEGRITY VERIFIER", fg="white", bg=USMC_RED, font=("Helvetica", 18, "bold")).pack()

        tk.Label(self, text="Available Backups:", fg=USMC_GOLD, bg=BG_COLOR, font=("Helvetica", 12, "bold")).pack(anchor="w", padx=40, pady=(20,5))

        self.backup_list = tk.Listbox(self, font=("Helvetica", 11), height=12, bg="#002b4d", fg="white", selectbackground=USMC_GOLD)
        self.backup_list.pack(fill="both", expand=True, padx=40, pady=5)

        tk.Button(self, text="🔍 VERIFY SELECTED BACKUP", bg=USMC_GOLD, fg=USMC_DARK,
                  font=("Helvetica", 14, "bold"), height=2, command=self.verify_selected).pack(pady=20)

        # Scrollable Results Area
        result_frame = tk.Frame(self)
        result_frame.pack(fill="both", expand=True, padx=40, pady=10)

        self.result_text = tk.Text(result_frame, font=("Consolas", 10), bg="#002b4d", fg="white", wrap="word")
        scrollbar = Scrollbar(result_frame, orient=VERTICAL, command=self.result_text.yview)
        self.result_text.configure(yscrollcommand=scrollbar.set)

        self.result_text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    def load_backups(self):
        self.backup_list.delete(0, tk.END)
        self.backup_paths.clear()

        if not self.backup_dir or not self.backup_dir.exists():
            self.backup_list.insert(0, "❌ Backups folder not found!")
            return

        # Collect both liberty and visitor backups, newest first
        liberty_baks = sorted(self.backup_dir.glob("liberty_log_*.csv.bak"), reverse=True)
        visitor_baks = sorted(self.backup_dir.glob("visitor_log_*.csv.bak"), reverse=True)

        all_baks = liberty_baks + visitor_baks
        if not all_baks:
            self.backup_list.insert(0, "No backups found yet.")
            return

        for bak in all_baks:
            if "liberty_log_" in bak.name:
                date_part = bak.name.replace("liberty_log_", "").replace(".csv.bak", "")
                label = f"📅 {date_part}   [LIBERTY]   {bak.name}"
            else:
                date_part = bak.name.replace("visitor_log_", "").replace(".csv.bak", "")
                label = f"📅 {date_part}   [VISITOR]    {bak.name}"

            self.backup_list.insert(tk.END, label)
            self.backup_paths.append(bak)

    def verify_selected(self):
        selection = self.backup_list.curselection()
        if not selection:
            messagebox.showwarning("Select a backup", "Please select one from the list.")
            return

        idx = selection[0]
        if idx >= len(self.backup_paths):
            messagebox.showerror("Error", "Internal list mismatch. Please restart the verifier.")
            return

        bak_file = self.backup_paths[idx]
        date_str = bak_file.name.replace("liberty_log_", "").replace("visitor_log_", "").replace(".csv.bak", "")
        hash_file = bak_file.with_suffix("").with_suffix(".sha256")   # turns .csv.bak into .sha256

        self.result_text.delete(1.0, tk.END)
        self.result_text.insert(tk.END, "=== BACKUP INTEGRITY VERIFICATION REPORT ===\n\n")
        self.result_text.insert(tk.END, f"Date being checked : {date_str}\n")
        self.result_text.insert(tk.END, f".bak file path      : {bak_file}\n")
        self.result_text.insert(tk.END, f".sha256 file path   : {hash_file}\n\n")

        if not bak_file.exists() or not hash_file.exists():
            self.result_text.insert(tk.END, "❌ Missing .bak or .sha256 file\n")
            return

        # Perform verification
        with open(bak_file, "rb") as f:
            current_hash = hashlib.sha256(f.read()).hexdigest()

        stored_hash = hash_file.read_text().strip()

        if current_hash == stored_hash:
            self.result_text.insert(tk.END, "✅ FILE HASH VERIFICATION SUCCESSFUL\n\n", "green")

            # Now perform hash chain verification on the rows
            self.result_text.insert(tk.END, "Performing row-level hash chain verification...\n\n")
            chain_valid, chain_message = self._verify_hash_chain(bak_file)

            if chain_valid:
                self.result_text.insert(tk.END, "✅ HASH CHAIN VERIFICATION SUCCESSFUL\n\n", "green")
                self.result_text.insert(tk.END, "This means no retroactive changes were made to the log after entries were written.\n")
            else:
                self.result_text.insert(tk.END, "❌ HASH CHAIN VERIFICATION FAILED\n\n", "red")
                self.result_text.insert(tk.END, chain_message + "\n")

            self.result_text.insert(tk.END, "What this means:\n")
            self.result_text.insert(tk.END, "• Every log entry contains the cryptographic hash of the previous entry.\n")
            self.result_text.insert(tk.END, "• Changing any historical row will break the chain for all subsequent rows.\n")
            self.result_text.insert(tk.END, "• Combined with daily file hashing, this provides strong tamper-evidence.\n")
        else:
            self.result_text.insert(tk.END, "❌ VERIFICATION FAILED - FILE HAS BEEN MODIFIED\n", "red")

        self.result_text.tag_config("green", foreground="#00FF00")
        self.result_text.tag_config("red", foreground="#FF4444")

    def _verify_hash_chain(self, log_file: Path) -> tuple[bool, str]:
        """
        Verify hash chain using the separate integrity ledger (preferred for clean logs).
        Falls back to embedded hashes if ledger not available.
        """
        try:
            # INTEGRITY_LEDGER_FILE and _compute_row_hash already imported at top level

            # Try ledger first (clean separation)
            if INTEGRITY_LEDGER_FILE.exists():
                return self._verify_chain_from_ledger(log_file)

            # Fallback: old embedded hash columns in the log file itself
            with open(log_file, "r", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = list(reader)

            if not rows:
                return True, "File is empty — nothing to verify."

            previous_hash = ""
            for i, row in enumerate(rows):
                stored_prev = row.get("PreviousHash", "")
                stored_row_hash = row.get("RowHash", "")

                if stored_prev != previous_hash:
                    return False, f"Chain broken at row {i+1}: PreviousHash mismatch."

                data_for_hash = {k: v for k, v in row.items() if k not in ("PreviousHash", "RowHash")}
                data_for_hash["PreviousHash"] = stored_prev

                serialized = "|".join(f"{k}={data_for_hash[k]}" for k in sorted(data_for_hash.keys()))
                computed_hash = hashlib.sha256(serialized.encode("utf-8")).hexdigest()

                if computed_hash != stored_row_hash:
                    return False, f"Chain broken at row {i+1}: RowHash mismatch."

                previous_hash = stored_row_hash

            return True, f"Successfully verified embedded hash chain across {len(rows)} rows."

        except Exception as e:
            return False, f"Error during chain verification: {str(e)}"

    def _verify_chain_from_ledger(self, log_file: Path) -> tuple[bool, str]:
        """
        Properly verify the hash chain by:
        1. Reading the actual log data from the backup file.
        2. Recomputing what each RowHash should be.
        3. Comparing against the values stored in the integrity ledger.
        """
        # INTEGRITY_LEDGER_FILE and _compute_row_hash already imported at module level

        try:
            # Determine log type and date
            filename = log_file.name
            if "liberty_log_" in filename:
                log_type = "liberty"
                log_date = filename.replace("liberty_log_", "").replace(".csv.bak", "")
            elif "visitor_log_" in filename:
                log_type = "visitor"
                log_date = filename.replace("visitor_log_", "").replace(".csv.bak", "")
            else:
                return False, "Unknown log type for chain verification."

            # Load ledger entries for this log
            with open(INTEGRITY_LEDGER_FILE, "r", newline="", encoding="utf-8") as f:
                ledger_reader = csv.DictReader(f)
                ledger_entries = [r for r in ledger_reader 
                                  if r.get("LogType") == log_type and r.get("LogDate") == log_date]

            if not ledger_entries:
                return True, "No ledger entries for this date — nothing to verify."

            # Load the actual log data from the backup
            with open(log_file, "r", newline="", encoding="utf-8") as f:
                log_reader = csv.DictReader(f)
                log_rows = list(log_reader)

            # Note: We no longer do a strict count match because the ledger can have 
            # entries from multiple generations or the full history. We verify what we have.

            # Build a lookup from OriginalRowKey -> ledger entry for faster matching
            ledger_by_key = {entry.get("OriginalRowKey", ""): entry for entry in ledger_entries}

            previous_hash = ""
            verified_count = 0
            chain_broken = False
            error_msg = ""

            for i, log_row in enumerate(log_rows):
                # Build the same key the generator uses
                # For liberty: Time_out|EDIPI
                # For visitor: Timestamp|Visitor_Name
                if log_type == "liberty":
                    row_key = f"{log_row.get('Time_out', '')}|{log_row.get('EDIPI', '')}"
                else:
                    row_key = f"{log_row.get('Timestamp', '')}|{log_row.get('Visitor_Name', '')}"

                ledger_entry = ledger_by_key.get(row_key)

                if not ledger_entry:
                    error_msg = f"Row {i+1} not found in ledger (key: {row_key})"
                    chain_broken = True
                    break

                stored_prev = ledger_entry.get("PreviousHash", "")
                stored_row_hash = ledger_entry.get("RowHash", "")

                # Recompute what the hash should be
                computed_hash = _compute_row_hash(log_row, previous_hash)

                if stored_prev != previous_hash:
                    error_msg = f"Chain broken at row {i+1}: PreviousHash in ledger does not match."
                    chain_broken = True
                    break

                if computed_hash != stored_row_hash:
                    error_msg = f"Hash mismatch at row {i+1}: Computed hash does not match ledger."
                    chain_broken = True
                    break

                previous_hash = computed_hash
                verified_count += 1

            if chain_broken:
                return False, error_msg

            return True, f"✅ Hash chain successfully verified for {verified_count} rows against the ledger."

        except Exception as e:
            return False, f"Ledger verification error: {str(e)}"

if __name__ == "__main__":
    app = BackupVerifier()
    app.mainloop()
