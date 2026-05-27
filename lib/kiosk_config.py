"""
kiosk_config.py

Central configuration for the Liberty Kiosk system.
This makes it easier to customize paths, security settings, and branding
without digging through multiple files.
"""

from pathlib import Path

# ====================== BASE PATHS ======================
BASE_DATA_DIR = Path("liberty_data")

# Subdirectory names (easy to change if needed)
DAILY_LOGS_DIR_NAME = "daily_logs"
VISITOR_LOGS_DIR_NAME = "visitor logs"
BACKUPS_DIR_NAME = "backups"

# Full resolved paths
DATA_DIR = BASE_DATA_DIR
DAILY_LOGS_DIR = DATA_DIR / DAILY_LOGS_DIR_NAME
VISITOR_LOGS_DIR = DATA_DIR / VISITOR_LOGS_DIR_NAME
BACKUPS_DIR = DATA_DIR / BACKUPS_DIR_NAME

# ====================== FILES ======================
PROFILES_FILE = DATA_DIR / "profiles.csv"
ADMIN_HASH_FILE = DATA_DIR / "admin.hash"
AUDIT_FILE = DATA_DIR / "admin_audit.csv"
SUPERUSER_HASH_FILE = Path("superuser_hash.txt")   # Kept in root for break-glass access
INTEGRITY_LEDGER_FILE = DATA_DIR / "integrity_ledger.csv"

# ====================== SECURITY ======================
DEFAULT_ADMIN_PASSWORD = "LibertyKiosk2026!"
PBKDF2_ITERATIONS = 200_000

# ====================== BRANDING / UNIT INFO ======================
KIOSK_TITLE = "MARDET-MONTEREY LIBERTY KIOSK"
UNIT_NAME = "MARDET-MONTEREY"

# USMC Official Colors (central source of truth for theming)
USMC_RED = "#C8102E"
USMC_GOLD = "#FFCC00"
USMC_DARK = "#001F3F"
BG_COLOR = "#001F3F"   # Same as USMC_DARK for dark backgrounds

# ====================== BACKUP SCHEDULER ======================
BACKUP_HOUR = 2          # Run daily backup at 02:00
BACKUP_LOOKBACK_DAYS = 7 # How far back to look for logs to back up

# ====================== HELPER FUNCTIONS ======================
def ensure_data_directories():
    """Create all required data directories if they don't exist."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DAILY_LOGS_DIR.mkdir(parents=True, exist_ok=True)
    VISITOR_LOGS_DIR.mkdir(parents=True, exist_ok=True)
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)

def get_daily_log_path(date) -> Path:
    """Return the path to the liberty log file for a given date."""
    return DAILY_LOGS_DIR / f"liberty_log_{date.isoformat()}.csv"

def get_visitor_log_path(date) -> Path:
    """Return the path to the visitor log file for a given date."""
    return VISITOR_LOGS_DIR / f"visitor_log_{date.isoformat()}.csv"