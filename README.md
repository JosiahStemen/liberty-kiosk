# MARDET-MONTEREY Liberty Kiosk

## Overview

This is the official Liberty Kiosk system for MARDET Monterey. It allows Marines to check in/out for liberty using their CAC cards at a self-service kiosk.

## Features

- CAC barcode scanning (front of card only)
- Automatic Marine profile creation and management
- PIN-protected check-in / check-out
- Buddy system (multiple Marines checking out together)
- Required destination logging
- ZYN product detection with humorous warnings
- Full admin panel with profile management
- Daily logging system

## Admin Guide

### Accessing Admin Menu
1. On the main screen, click **ADMIN MENU** (bottom right)
2. Enter the admin password (default: `LibertyKiosk2026!`)

### Available Admin Functions

1. **View Marines Currently on Liberty** - Shows all Marines who have checked out but not yet checked back in.
2. **Update Marine Profile** - Edit rank, name, EDIPI, phone number.
3. **Reset Marine PIN** - Reset a Marine's PIN if forgotten.
4. **Change Admin Password** - Update the kiosk admin password.
5. **Exit Kiosk** - Completely close the application.

## First Time Setup

1. Place the `liberty_kiosk_gui.py` file on the kiosk computer.
2. Install Python 3 if not already installed.
3. Run the script: `python liberty_kiosk_gui.py`
4. **Immediately change the admin password** using the Admin Menu.
5. Test with your own CAC card.

## File Structure

```
liberty-kiosk/
├── liberty_kiosk_gui.py          ← Main application
├── liberty_data/                 ← Created automatically
│   ├── profiles.csv              ← All registered Marines
│   ├── admin.hash                ← Admin password hash
│   └── daily_logs/               ← Daily check-in/out logs
```

**Important**: Never delete the `liberty_data` folder while the kiosk is running.

## Security Notes

- All PINs are stored as SHA-256 hashes
- Admin password is also hashed
- CAC data is only parsed for name/rank (no sensitive data stored)

## Troubleshooting

- Scanner not working? Make sure you're scanning the **front** of the CAC.
- "Parse error"? Try scanning again slowly and steadily.
- For admin access issues, the default password is `LibertyKiosk2026!`

## Support

Contact the developer or your S-6 shop for assistance.

**Semper Fi**
