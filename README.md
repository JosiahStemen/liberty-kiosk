# MARDET-MONTEREY Liberty Kiosk

**Official self-service liberty check-in/out system for MARDET Monterey.**

This GUI application allows Marines to quickly check in and out for liberty using their CAC cards at a dedicated kiosk station.

## ✨ Features

- **CAC Barcode Scanning**: Scans the *front* of the Common Access Card (CAC) via USB barcode reader (emulates keyboard input)
- **Automatic Profile Management**: First-time users are automatically detected and guided through registration
- **PIN Authentication**: Secure 5-9 digit PIN for check-in/out
- **Buddy System**: Check out with multiple Marines under one sponsor
- **Destination Logging**: Required field for accountability
- **ZYN Detection**: Humorous warnings if ZYN product barcodes are scanned
- **Full Admin Panel**:
  - View Marines currently on liberty
  - Update Marine profiles (rank, name, phone, etc.)
  - Reset forgotten PINs
  - Change admin password
  - Verify backup integrity
  - Export logs to USB (with PII warnings)
  - Safe kiosk shutdown
- **Daily Logging & Automated Backups**: Logs all activity with daily CSV files + SHA-256 hashed backups
- **USMC-Themed UI**: Red, gold, and dark blue color scheme

## 🚀 Quick Start

1. Ensure Python 3 is installed on the kiosk computer.
2. Place all project files in a directory.
3. Run the main application:
   ```bash
   python liberty_kiosk_gui.py
   ```
4. The application launches in **fullscreen mode**.
5. **Immediately** go to **ADMIN MENU** → Change Admin Password (default: `LibertyKiosk2026!`)

## 📋 First-Time Marine Registration

When a new CAC is scanned:
1. System auto-parses name and rank.
2. Prompts for:
   - 10-digit EDIPI
   - Phone number
   - 5-9 digit PIN (chosen by Marine)
3. Profile is saved to `liberty_data/profiles.csv`

## 🔐 Admin Menu

**Access**: Click **ADMIN MENU** button (bottom right) → Enter admin password.

Available functions:

1. **View Marines Currently on Liberty** - Real-time list of checked-out personnel (last 7 days)
2. **Update Marine Profile** - Edit rank/name/phone
3. **Reset Marine PIN** - For forgotten PINs
4. **Change Admin Password** - Security best practice
5. **Verify Backups (Integrity Check)** - Launches `backup_verifier.py`
6. **Export Logs & Backups to USB** - Secure data export with date range selection
7. **Exit Kiosk** - Close application

## 📁 Project Structure

```
liberty-kiosk/
├── liberty_kiosk_gui.py          # Main kiosk application
├── backup_verifier.py            # Backup integrity checker
├── create_test_data.py           # Generate realistic test logs
├── README.md
└── liberty_data/                 # Auto-created at runtime
    ├── profiles.csv              # All Marine profiles
    ├── admin.hash                # Hashed admin password
    ├── daily_logs/               # Daily liberty logs (CSV)
    └── backups/                  # Daily backups + SHA256 hashes
```

**⚠️ Important**: Do not manually delete or modify files in `liberty_data/` while the kiosk is running.

## 🛡️ Security

- All PINs and admin password stored as **SHA-256 hashes**
- No full CAC data stored — only parsed name/rank/EDIPI
- Daily automated backups with cryptographic integrity verification
- Export function includes strong PII/CUI warnings
- Escape key opens admin menu (for quick access)

## 🛠️ Additional Tools

### backup_verifier.py
Launches a separate GUI to verify that backup files match their SHA-256 hashes. Useful for audits and chain-of-custody.

### create_test_data.py
Generates realistic test data (logs + backups) for testing the system. Configurable number of days/entries.

## 🔧 Troubleshooting

- **Scanner not reading**: Ensure scanning **front** of CAC only. Reader must be set to keyboard emulation.
- **Parse error**: Scan slowly and steadily. Try again.
- **Forgotten Admin Password**: Manually delete `liberty_data/admin.hash` to reset to default (`LibertyKiosk2026!`)
- **Application not fullscreen**: Check display settings or modify code.
- **ZYN warnings**: Intentional easter egg for tobacco products.

## 📋 Deployment Notes

- Designed for Windows kiosk computers with attached barcode scanner
- Recommended to run as a startup application
- Consider using a dedicated user account with auto-login
- Test thoroughly with real CAC cards before live deployment
- Maintain physical security of the kiosk station

## Support

Contact your S-6 shop or the developer for assistance.

**Semper Fidelis** 🪖

---

*Liberty Kiosk v1.0 - MARDET Monterey*