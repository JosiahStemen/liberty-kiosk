# MARDET-MONTEREY Liberty Kiosk

**Official self-service liberty check-in/out system for MARDET-Monterey.**

This GUI application allows Marines to quickly check in and out for liberty using their CAC cards at a dedicated kiosk station.

> **Important Note for Legal / Audit Review**  
> This system is designed to operate in an **air-gapped environment under constant duty watch**. It is intended to operate **in parallel with** the unit’s existing physical OOD logbook. The digital records are designed to be human-readable while also incorporating cryptographic controls for integrity. See the sections below on Cryptographic Integrity Controls and Legal Considerations.

## ✨ Features

- **CAC Barcode Scanning**: Scans the *front* of the Common Access Card (CAC) via USB barcode reader (emulates keyboard input)
- **Automatic Profile Management**: First-time users are automatically detected and guided through registration
- **PIN Authentication**: Secure 5-9 digit PIN for check-in/out
- **Buddy System**: Check out with multiple Marines under one sponsor
- **Destination Logging**: Required field for accountability
- **View Marines Out on Main Screen**: Large button on the right side of the main screen.
- **Visitor System**: "CHECK IN/OUT VISITOR" and "VIEW VISITOR LIST" buttons on the left side of the main screen. Host must not be checked out on liberty to sign in a visitor.
- **Full Admin Panel**:
  - Force Check-In Marine (OOD override with reason + logbook warning)
  - Update Marine profiles (rank, name, phone, etc.)
  - Reset forgotten PINs
  - Verify backup integrity
  - Export All Logs & Backups to USB (includes liberty logs + visitor logs)
  - Safe kiosk shutdown
- **Scrollable Admin Menu**
- **Superuser Break-Glass Account** (J-Dizz only): Private password that works even if shared admin password changes
- **Daily Logging & Automated Backups**: Logs all activity with daily CSV files + SHA-256 hashed backups
- **USMC-Themed UI**: Red, gold, and dark blue color scheme

## Deployment & Quick Start

### Minimal Deployment on the Kiosk Machine
1. Copy the following to the kiosk computer:
   - `liberty_kiosk_gui.py`
   - The entire `lib/` folder
   - The `dependencies/` folder
   - (The `liberty_data/` folder will be created automatically)

2. Install dependencies:
   ```bash
   pip install -r dependencies/requirements.txt
   ```

3. (Recommended) Use the provided launcher:
   Double-click `run_kiosk.bat`

4. On first run, go to the Admin Menu and immediately change the default admin password.

### Launcher
A simple `run_kiosk.bat` is included in the root for easy startup on the kiosk machine.

📋 First-Time Marine Registration
When a new CAC is scanned:

System auto-parses name and rank.
Prompts for:
10-digit EDIPI
Phone number
5-9 digit PIN (chosen by Marine)

Profile is saved to liberty_data/profiles.csv

🔐 Admin Menu
Access: Click ADMIN MENU button → Enter shared admin password.
The Admin Menu is scrollable and includes:

Update Marine Profile
Reset Marine PIN
Force Check-In Marine ← OOD Override (searches the last 7 days)
Change Admin Password
Verify Backups (Integrity Check)
Export All Logs & Backups to USB (includes liberty logs + visitor logs)
Exit Kiosk

Force Check-In (OOD Override)

Available from Admin Menu OR by clicking the small red FORCE CHECK-IN button next to any Marine on the View Marines Out screen.
You must enter a reason (e.g. “lost CAC”, “returned without scanning”).
Double confirmation dialog reminds you: “This action must also be recorded in the physical OOD logbook per unit policy.”
The daily log clearly marks it as a force check-in.

🔥 Superuser (Break-Glass) Account – J-Dizz Only
Your private superuser password works anywhere the normal admin password is asked.
When you log in with the superuser password, two extra red buttons appear at the top of the Admin Menu:

🔥 RESET ADMIN PASSWORD – Instantly set a new shared admin password
🔥 CHANGE SUPERUSER PASSWORD – Change your own private password

Never share your superuser password or the superuser_hash.txt file.

## Project Structure (Clean Deployment Layout)

```
liberty-kiosk/
├── liberty_kiosk_gui.py          # ← Main application to run on the kiosk
├── liberty_data/                 # ← All operational data (gitignored)
│   ├── daily_logs/
│   ├── visitor logs/
│   ├── backups/
│   └── integrity_ledger.csv
├── dependencies/
│   └── requirements.txt
├── lib/                          # Internal shared code modules
│   ├── liberty_common.py
│   ├── kiosk_config.py
│   ├── kiosk_ui.py
│   └── ...
├── tools/                        # Administrative and testing tools
│   ├── visitor_signin.py
│   ├── backup_verifier.py
│   └── create_test_data.py
├── run_kiosk.bat                 # Simple launcher for the main application
├── README.md
└── .gitignore
```

### Minimal Files Needed on the Kiosk Machine
- `liberty_kiosk_gui.py`
- The entire `lib/` folder
- The `dependencies/` folder (install packages listed in `requirements.txt`)
- The `liberty_data/` folder (created automatically on first run)
├── tools/                        # Utility / admin scripts
│   ├── visitor_signin.py
│   ├── backup_verifier.py
│   └── create_test_data.py
├── README.md
└── .gitignore

When deploying to the kiosk machine, the main things you need are:
- liberty_kiosk_gui.py
- The dependencies/ folder (install from requirements.txt)
- The liberty_data/ folder (created automatically on first run)
- The lib/ folder (required by the main app)

## Legal & Evidentiary Considerations

This system operates under the following controls that are relevant to evidentiary use:

- **Air-gapped environment** — No network connectivity.
- **Constant physical supervision** — The kiosk is under continuous duty watch.
- **Parallel physical record** — A traditional paper OOD logbook is maintained alongside the digital system.
- **Cryptographic integrity controls** — See "Cryptographic Integrity Controls" section below.
- **Human-readable logs** — Liberty and visitor logs are deliberately kept in CSV format (with a separate integrity ledger) so that duty personnel and leadership can directly review them without specialized software.

**Important Limitation**: This system is **not** designed to be the sole record of liberty accountability. It is intended as a **supplement** to the unit’s physical logbook. Any digital record should be corroborated with the contemporaneous paper log and witness testimony.

## Cryptographic Integrity Controls

The system uses a layered approach to detect tampering while preserving human readability:

### 1. Separate Integrity Ledger (`integrity_ledger.csv`)
- All cryptographic hash chaining occurs in a dedicated ledger file, **not** inside the operational liberty or visitor logs.
- Each entry in the ledger contains:
  - `PreviousHash` — cryptographic hash of the prior entry in the chain.
  - `RowHash` — hash of the current log row’s data + the `PreviousHash`.
- This creates a verifiable chain: altering any historical row will cause all subsequent `RowHash` values to become invalid.
- Because the hashes live in a separate file, the main operational logs remain clean and easy for humans to read and print.

### 2. Daily File-Level Hashing
- At the end of each day, the previous day’s liberty log is backed up.
- A SHA-256 hash of the backup file is created and stored alongside it.
- These file hashes allow verification that a backup has not been altered since it was created.

### 3. Export Process & Chain of Custody
- When logs are exported via the Admin Menu, the system generates:
  - Raw log files (daily_logs and visitor logs) for the selected date range.
  - Filtered backup files (.bak) and their SHA-256 hash files.
  - Human-readable PDF reports (daily reports + combined visitor report) for the selected date range.
  - A cryptographic manifest of all files in the export.
  - A dedicated **Chain of Custody PDF** containing:
    - Export metadata and date range.
    - A formal certification statement.
    - Signature blocks for the exporter (name, rank, EDIPI, signature, date/time) and an optional witness.
- The full integrity ledger at the time of export is included for independent verification of the hash chain.

### 4. Hash Algorithm
- SHA-256 is used for all hashing (both file-level backups and the row-level chain in the integrity ledger).
- This is a widely accepted, collision-resistant cryptographic hash function.

**What these controls can detect**:
- Retroactive alteration of historical log entries after they were written.
- Corruption or truncation of backup files.

**What these controls cannot prevent**:
- False data entered at the time of creation (mitigated by duty watch + physical logbook).
- Tampering by someone with physical access during their watch who also controls the ledger at the moment of entry.

These controls, when combined with constant duty supervision and the parallel physical OOD logbook, are intended to provide a reasonable level of assurance regarding the integrity of the records for internal unit purposes and potential evidentiary use.

## Preparing Evidence for Court or Subpoena (Single Day)

If a specific day’s records are subpoenaed, the following package should be prepared:

1. **The raw log files** for that date (included in the export) or the daily backup + verified hash.
2. **The corresponding entries** from `integrity_ledger.csv` for that date.
3. **Proof of hash chain integrity** for the requested day (run the Backup Verifier and export/save the verification report).
4. **The daily backup** (.bak) and its `.sha256` hash file.
5. **The Chain of Custody PDF** generated during any export of that data.
6. **A copy of the physical OOD logbook** entry for the same date.
7. **Testimony** from the duty personnel who were on watch during the relevant period.
8. **Export metadata** (who performed the export, when, and under what authority).

The combination of cryptographic controls (hash chain + file hashes), constant duty supervision, and the contemporaneous physical logbook is intended to support the reliability of the digital record.

## Tools & Utilities

The `tools/` folder contains administrative and testing utilities:

- `visitor_signin.py` — Standalone Visitor Check-In/Out tool (launched from the main kiosk).
- `backup_verifier.py` — Verifies both file-level SHA-256 hashes and the row-level hash chain stored in the integrity ledger.
- `create_test_data.py` — Generates realistic multi-day test data, including properly chained entries in the separate integrity ledger (useful for training and validation).

🔧 Troubleshooting

Scanner not reading: Ensure scanning front of CAC only. Reader must be set to keyboard emulation.
Parse error: Scan slowly and steadily. Try again.
Admin Menu buttons blank: Restart the program.
Dialogs don't auto-focus: Fixed in latest version — you can now type immediately.
Forgotten Admin Password: Use your superuser password to reset it instantly.

📋 Recent Changes

- Admin Menu is now fully scrollable
- Export includes raw logs, daily backups with hashes, PDF reports, cryptographic manifest, and Chain of Custody documentation.
- Added dedicated Visitor Check-In/Out system with its own tool
- Added `kiosk_config.py` and `kiosk_ui.py` for better architecture
- Removed live status dashboard from main screen
- Visitor buttons moved to left side and styled gold for consistency
- Improved Zyn easter egg UPC accuracy

Liberty Kiosk - MARDET Monterey
Semper Fidelis 🪖
