# MARDET-MONTEREY Liberty Kiosk

**Official self-service liberty check-in/out system for MARDET-Monterey.**

This GUI application allows Marines to quickly check in and out for liberty using their CAC cards at a dedicated kiosk station.

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

## 🚀 Quick Start

1. Ensure Python 3 is installed on the kiosk computer.
2. Place all project files in a directory.
3. Run the main application:
   python liberty_kiosk_gui.py
4. The application launches in fullscreen mode.
5. Immediately go to ADMIN MENU → Change Admin Password (default: LibertyKiosk2026!)

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

📁 Project Structure
liberty-kiosk/
├── liberty_kiosk_gui.py          # Main kiosk application
├── kiosk_config.py               # Centralized configuration (paths, security settings, etc.)
├── kiosk_ui.py                   # Shared themed UI components and dialogs
├── liberty_common.py             # Shared utilities (hashing, CAC parsing, profile loading, etc.)
├── visitor_signin.py             # Standalone Visitor Check-In/Out tool (launched from main GUI)
├── backup_verifier.py            # Backup integrity checker
├── create_test_data.py           # Generate realistic test logs
├── README.md
├── .gitignore                    # Keeps PII/CUI + credential hashes out of git
├── superuser_hash.txt            # Private superuser hash (gitignored — never commit)
└── liberty_data/                 # Auto-created at runtime (gitignored)
    ├── profiles.csv              # All Marine profiles
    ├── admin.hash                # Shared admin password hash (salted PBKDF2)
    ├── admin_audit.csv           # Admin action audit trail (logins, exports, etc.)
    ├── daily_logs/               # Daily liberty logs (CSV)
    ├── visitor logs/             # Visitor sign-in/check-out logs (separate folder)
    └── backups/                  # Daily backups + SHA256 hashes
⚠️ Important: Do not manually delete or modify files in liberty_data/.

🛡️ Security

All PINs and admin/superuser passwords stored as salted PBKDF2-HMAC-SHA256 hashes (legacy SHA-256 hashes auto-upgrade on next successful login)
Credential hashes and all PII/CUI are excluded from git via .gitignore — never commit liberty_data/ or the hash files
Admin actions (logins, password changes, force check-ins, exports) are recorded in liberty_data/admin_audit.csv
No full CAC data stored — only parsed name/rank/EDIPI
Daily automated backups with cryptographic integrity verification
Export function includes strong PII/CUI warnings
Escape key opens admin menu (for quick access)

🛠️ Additional Tools

liberty_common.py
Shared code used by the main kiosk and standalone tools (PIN hashing, CAC parsing, profile loading, "is on liberty?" checks, visitor logging, etc.). This is the foundation for the modular design.

kiosk_config.py
Centralized configuration for paths, security settings, and helper functions.

kiosk_ui.py
Reusable themed UI components and dialogs for consistent red/gold styling across tools.

visitor_signin.py
Standalone Visitor Check-In/Out application. Launched by clicking "CHECK IN/OUT VISITOR" on the main kiosk (left side). The host Marine must **not** be currently checked out on liberty to sign in a visitor (this is enforced). Supports both signing visitors in and checking them out.

backup_verifier.py
Launches a separate GUI to verify that backup files match their SHA-256 hashes.

create_test_data.py
Generates realistic test data (logs + backups) for testing the system.

🔧 Troubleshooting

Scanner not reading: Ensure scanning front of CAC only. Reader must be set to keyboard emulation.
Parse error: Scan slowly and steadily. Try again.
Admin Menu buttons blank: Restart the program.
Dialogs don't auto-focus: Fixed in latest version — you can now type immediately.
Forgotten Admin Password: Use your superuser password to reset it instantly.

📋 Recent Changes

- Admin Menu is now fully scrollable
- Combined export options into one unified "Export All Logs & Backups to USB"
- Added dedicated Visitor Check-In/Out system with its own tool
- Added `kiosk_config.py` and `kiosk_ui.py` for better architecture
- Removed live status dashboard from main screen
- Visitor buttons moved to left side and styled gold for consistency
- Improved Zyn easter egg UPC accuracy

Liberty Kiosk - MARDET Monterey
Semper Fidelis 🪖
