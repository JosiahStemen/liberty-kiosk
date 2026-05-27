"""
liberty_common.py

Shared constants, functions, and helpers used by:
- liberty_kiosk_gui.py (main kiosk)
- visitor_signin.py (standalone visitor tool)
- backup_verifier.py (and future tools)

This module reduces duplication and makes it easy to build additional
admin/reporting utilities in the future.
"""

import csv
import datetime
import hashlib
import hmac
import os
import re
from pathlib import Path
from kiosk_config import (
    DATA_DIR,
    PROFILES_FILE,
    VISITOR_LOGS_DIR,
    DAILY_LOGS_DIR,
    BACKUPS_DIR,
    ensure_data_directories,
    get_daily_log_path,
    get_visitor_log_path,
)

# ====================== USMC COLORS (shared theme) ======================
USMC_RED = "#C8102E"
USMC_GOLD = "#FFCC00"
USMC_DARK = "#001F3F"
BG_COLOR = "#001F3F"

# ====================== PASSWORD / PIN HASHING ======================
PBKDF2_ITERATIONS = 200_000


def hash_secret(secret: str) -> str:
    """Hash a secret (PIN or password) using PBKDF2-HMAC-SHA256."""
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", secret.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${dk.hex()}"


def verify_secret(secret: str, stored: str):
    """
    Verify a secret against a stored hash.
    Returns (is_valid, needs_upgrade).
    Supports modern PBKDF2 format and legacy SHA-256 hashes.
    """
    stored = (stored or "").strip()
    if not stored:
        return False, False

    if stored.startswith("pbkdf2_sha256$"):
        try:
            _, iters, salt_hex, hash_hex = stored.split("$")
            dk = hashlib.pbkdf2_hmac(
                "sha256", secret.encode("utf-8"), bytes.fromhex(salt_hex), int(iters)
            )
            return hmac.compare_digest(dk.hex(), hash_hex), False
        except Exception:
            return False, False

    # Legacy SHA-256 support (auto-upgrade on successful login)
    if len(stored) == 64 and all(c in "0123456789abcdefABCDEF" for c in stored):
        legacy = hashlib.sha256(secret.encode("utf-8")).hexdigest()
        return hmac.compare_digest(legacy, stored.lower()), True

    return False, False


def _csv_safe(value):
    """Prevent CSV formula injection."""
    s = "" if value is None else str(value)
    if s[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + s
    return s


# ====================== CAC BARCODE PARSING ======================
def parse_cac_barcode(barcode: str) -> dict:
    """
    Parse a CAC barcode (front scan, keyboard wedge emulation).
    Returns a dict with Rank, Name fields, EDIPI, etc.
    This is intentionally lenient — the main kiosk and visitor tool
    both rely on it.
    """
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
        "EDIPI": barcode,           # The 99-char string acts as the unique ID
        "Rank": rank,
        "Last_Name": last,
        "First_Name": first,
        "Middle_Initial": mi,
        "Full_Name": full_name
    }


# ====================== PROFILES ======================
def load_profiles() -> dict:
    """Load all Marine profiles from the CSV. Returns dict keyed by Raw_ID."""
    profiles = {}
    if PROFILES_FILE.exists():
        with open(PROFILES_FILE, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                mi = row.get("Middle_Initial", "").strip()
                full = f"{row['Last_Name']}, {row['First_Name']}"
                if mi:
                    full += f" {mi}"
                row["Full_Name"] = full
                profiles[row["Raw_ID"]] = row
    return profiles


def find_profile_by_edipi(edipi: str, profiles: dict = None) -> dict:
    """
    Find a profile by its 10-digit EDIPI.
    The main profiles dict is keyed by Raw_ID (full CAC barcode), so we need this lookup.
    """
    if profiles is None:
        profiles = load_profiles()
    if not edipi:
        return None
    edipi = str(edipi).strip()
    for p in profiles.values():
        if str(p.get("EDIPI", "")).strip() == edipi:
            return p
    return None


# ====================== LIBERTY STATUS CHECK ======================
def find_open_entry(edipi: str):
    """
    Check if this EDIPI has an open liberty entry (has checked out but not yet checked back in)
    in the last 7 days of logs.

    Returns (row_dict, log_file_path) if found, otherwise (None, None).
    """
    for i in range(7):
        d = datetime.date.today() - datetime.timedelta(days=i)
        log_file = get_daily_log_path(d)
        if not log_file.exists():
            continue

        with open(log_file, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

            for row in reversed(rows):
                if row.get("EDIPI") == edipi:
                    time_in = row.get("Time_in")
                    if time_in is None or str(time_in).strip() == "":
                        return row, log_file
    return None, None


# ====================== VISITOR LOGGING ======================
VISITOR_LOG_HEADERS = [
    "Timestamp", "Host_Rank", "Host_Name", "Host_EDIPI",
    "Visitor_Name", "Building", "Room", "Time_Out"
]


def get_today_visitor_log_filename():
    """Return the path to today's visitor log CSV."""
    ensure_data_directories()
    return get_visitor_log_path(datetime.date.today())


def init_visitor_log():
    """Ensure today's visitor log exists with the correct header (adds Time_Out column if missing)."""
    log_file = get_today_visitor_log_filename()
    if not log_file.exists():
        with open(log_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(VISITOR_LOG_HEADERS)
    else:
        # Ensure the file has the Time_Out column (for older logs)
        with open(log_file, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            existing_fieldnames = reader.fieldnames or []
            rows = list(reader)

        if "Time_Out" not in existing_fieldnames:
            new_fieldnames = existing_fieldnames + ["Time_Out"]
            for r in rows:
                r.setdefault("Time_Out", "")
            with open(log_file, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=new_fieldnames)
                writer.writeheader()
                writer.writerows(rows)


def log_visitor_signin(host_rank, host_name, host_edipi, visitor_name, building, room):
    """Append a visitor sign-in record (Time_Out left blank until checked out)."""
    init_visitor_log()
    log_file = get_today_visitor_log_filename()
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_file, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=VISITOR_LOG_HEADERS)
        writer.writerow({
            "Timestamp": timestamp,
            "Host_Rank": host_rank,
            "Host_Name": host_name,
            "Host_EDIPI": host_edipi,
            "Visitor_Name": visitor_name,
            "Building": building,
            "Room": room,
            "Time_Out": ""
        })


def checkout_visitor(timestamp: str, host_edipi: str, visitor_name: str) -> bool:
    """
    Mark a previously signed-in visitor as checked out by filling in Time_Out.
    Returns True if a matching open record was found and updated.
    """
    log_file = get_today_visitor_log_filename()
    if not log_file.exists():
        return False

    with open(log_file, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or VISITOR_LOG_HEADERS
        rows = list(reader)

    updated = False
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for row in rows:
        if (row.get("Timestamp") == timestamp and
            str(row.get("Host_EDIPI", "")).strip() == str(host_edipi).strip() and
            row.get("Visitor_Name", "").strip().lower() == visitor_name.strip().lower() and
            not row.get("Time_Out")):
            row["Time_Out"] = now_str
            updated = True
            break

    if updated:
        with open(log_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        return True
    return False


def get_open_visitors_for_today():
    """Return list of visitors who have signed in today but have not yet checked out."""
    log_file = get_today_visitor_log_filename()
    if not log_file.exists():
        return []

    with open(log_file, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [row for row in reader if not row.get("Time_Out", "").strip()]


# ====================== PHONE NUMBER FORMATTING ======================
def format_phone(phone: str) -> str:
    """
    Format a phone number into (555)123-4567 style.
    
    Accepts:
        - 5551234567
        - 555-123-4567
        - (555) 123-4567
        - 1-555-123-4567
        - etc.
    
    Returns the nicely formatted version when possible.
    Falls back to the original (stripped) input if it can't parse it.
    """
    if not phone:
        return ""

    # Keep only digits
    digits = "".join(c for c in phone if c.isdigit())

    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]  # drop leading country code

    if len(digits) == 10:
        area = digits[0:3]
        prefix = digits[3:6]
        line = digits[6:10]
        return f"({area}){prefix}-{line}"

    # Could not normalize nicely — return cleaned version
    return digits if digits else phone.strip()
