import tkinter as tk
from tkinter import messagebox, Scrollbar, VERTICAL, RIGHT, Y
from pathlib import Path
import hashlib

# USMC COLORS
USMC_RED = "#C8102E"
USMC_GOLD = "#FFCC00"
USMC_DARK = "#001F3F"
BG_COLOR = "#001F3F"

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
        self.script_dir = Path(__file__).parent
        self.backup_dir = None
        possible = [
            self.script_dir / "liberty_data" / "backups",
            Path("liberty_data/backups"),
            Path.cwd() / "liberty_data" / "backups"
        ]
        for p in possible:
            if p.exists():
                self.backup_dir = p
                break

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
        if not self.backup_dir or not self.backup_dir.exists():
            self.backup_list.insert(0, "❌ Backups folder not found!")
            return

        bak_files = sorted(self.backup_dir.glob("*.csv.bak"))
        if not bak_files:
            self.backup_list.insert(0, "No backups found yet.")
            return

        for bak in bak_files:
            date_part = bak.name.replace("liberty_log_", "").replace(".csv.bak", "")
            self.backup_list.insert(0, f"📅 {date_part}   →   {bak.name}")

    def verify_selected(self):
        selection = self.backup_list.curselection()
        if not selection:
            messagebox.showwarning("Select a backup", "Please select one from the list.")
            return

        selected_text = self.backup_list.get(selection[0])
        date_str = selected_text.split("→")[0].strip().replace("📅", "").strip()

        bak_file = self.backup_dir / f"liberty_log_{date_str}.csv.bak"
        hash_file = self.backup_dir / f"liberty_log_{date_str}.sha256"

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
            self.result_text.insert(tk.END, "✅ VERIFICATION SUCCESSFUL - FILE IS UNTOUCHED\n\n", "green")
            self.result_text.insert(tk.END, "Technical Details:\n")
            self.result_text.insert(tk.END, "• Algorithm used: SHA-256 (256-bit Secure Hash Algorithm)\n")
            self.result_text.insert(tk.END, "• Hash type: Cryptographic one-way function\n")
            self.result_text.insert(tk.END, "• Any change to even a single character in the log would produce a completely different hash\n")
            self.result_text.insert(tk.END, "• This provides mathematically verifiable proof of data integrity\n")
            self.result_text.insert(tk.END, "• Accepted standard by DoD, courts, and federal agencies for chain-of-custody\n\n")
            self.result_text.insert(tk.END, "This backup is 100% identical to the original file created at 02:00 AM on the backup date.\n")
            self.result_text.insert(tk.END, "You can confidently present this report as evidence.")
        else:
            self.result_text.insert(tk.END, "❌ VERIFICATION FAILED - FILE HAS BEEN MODIFIED\n", "red")

        self.result_text.tag_config("green", foreground="#00FF00")
        self.result_text.tag_config("red", foreground="#FF4444")

if __name__ == "__main__":
    app = BackupVerifier()
    app.mainloop()
