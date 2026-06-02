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
    INTEGRITY_LEDGER_FILE,
    ensure_data_directories,
    get_daily_log_path,
    get_visitor_log_path,
    # Colors centralized in kiosk_config for theming consistency
    USMC_RED,
    USMC_GOLD,
    USMC_DARK,
    BG_COLOR,
)

# ====================== SEPARATE HASH LEDGER FOR LOG INTEGRITY ======================
# Hashes are stored in a dedicated ledger file so the main logs remain clean
# and easy for humans (duty personnel, OOD, etc.) to read and print.

INTEGRITY_LEDGER_HEADERS = [
    "LedgerTimestamp", "LogType", "LogDate", "OriginalRowKey",
    "PreviousHash", "RowHash"
]


def _compute_row_hash(row_data: dict, previous_hash: str) -> str:
    """
    Compute a deterministic hash for a log row.
    """
    # Exclude any hash fields if present
    data_to_hash = {k: v for k, v in row_data.items() 
                    if k not in ("PreviousHash", "RowHash")}
    data_to_hash["PreviousHash"] = previous_hash or ""

    serialized = "|".join(f"{k}={data_to_hash[k]}" for k in sorted(data_to_hash.keys()))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def get_last_row_hash(log_type: str, log_date: str) -> str:
    """
    Return the most recent RowHash for a given log type and date from the ledger.
    log_type: "liberty" or "visitor"
    log_date: "YYYY-MM-DD"
    """
    if not INTEGRITY_LEDGER_FILE.exists():
        return ""

    with open(INTEGRITY_LEDGER_FILE, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        last_hash = ""
        for row in reader:
            if row.get("LogType") == log_type and row.get("LogDate") == log_date:
                last_hash = row.get("RowHash", "") or ""
        return last_hash


def record_hash_entry(log_type: str, log_date: str, original_row_key: str, 
                      previous_hash: str, row_hash: str):
    """Append a hash entry to the integrity ledger."""
    ensure_data_directories()
    ledger_exists = INTEGRITY_LEDGER_FILE.exists()

    with open(INTEGRITY_LEDGER_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=INTEGRITY_LEDGER_HEADERS)
        if not ledger_exists:
            writer.writeheader()

        writer.writerow({
            "LedgerTimestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "LogType": log_type,
            "LogDate": log_date,
            "OriginalRowKey": original_row_key,
            "PreviousHash": previous_hash,
            "RowHash": row_hash
        })

# Colors are now imported from kiosk_config (single source of truth for branding)

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

    Solid multi-strategy parser:
    - Rank via case-insensitive substring on known list.
    - Name: tries original pattern, no-MI pattern, comma/dot separated LAST,FIRST[.MI],
      and word fallback. Handles missing middle initial, ALL CAPS, Title Case, etc.
    - Never crashes; falls back to UNKNOWN fields (user corrects in registration UI).
    The 99-char Raw_ID is always the reliable per-card key; the parsed name is best-effort
    convenience for first-time registration.
    """
    rank = "UNKNOWN"
    first = "UNKNOWN"
    last = "UNKNOWN"
    mi = ""

    # Rank: robust case-insensitive
    rank_words = ["SGT", "CPL", "LCPL", "PFC", "PVT", "SSGT", "GYSGT", "MSGT", "MGYSGT", "SGTMAJ"]
    upper_bar = barcode.upper()
    for word in rank_words:
        if word in upper_bar:
            rank = word
            break

    # Name strategies (first successful non-UNKNOWN wins)
    # 1. Original Title-Case with MI (may have glued or spaced)
    m = re.search(r'([A-Z][a-z]+)\s+([A-Z])([A-Z][a-z]+)', barcode)
    if m:
        first = m.group(1)
        mi = m.group(2)
        last = m.group(3)
    else:
        # 2. Title Case without MI
        m = re.search(r'([A-Z][a-z]+)\s+([A-Z][a-z]+)', barcode)
        if m:
            first = m.group(1)
            last = m.group(2)
            mi = ""
        else:
            # 3. Comma / dot / space separated (LAST, FIRST or LAST.FIRST.MI etc.)
            m = re.search(r'([A-Za-z]+)[,\.\s]+([A-Za-z]+)(?:[,\.\s]+([A-Za-z]))?', barcode)
            if m:
                last = m.group(1).strip().title()
                first = m.group(2).strip().title()
                mi = (m.group(3) or "").strip().upper()[:1]
            else:
                # 4. Last resort: collect capitalized words and assign heuristically
                words = re.findall(r'([A-Z][A-Za-z]+)', barcode)
                if len(words) >= 2:
                    # Heuristic for many barcode formats: first word-ish is last name
                    last = words[0].title()
                    first = words[1].title()
                    mi = ""
                    if len(last) < 2 and len(words) > 2:
                        last = words[-1].title()
                        first = words[-2].title()

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
    "Visitor_Name", "Building", "Room", "Time_Out",
    "PreviousHash", "RowHash"
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
    """Append a visitor sign-in record. Hashes are recorded in a separate integrity ledger."""
    init_visitor_log()
    log_file = get_today_visitor_log_filename()

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_date = datetime.date.today().isoformat()

    previous_hash = get_last_row_hash("visitor", log_date)

    row_data = {
        "Timestamp": timestamp,
        "Host_Rank": host_rank,
        "Host_Name": host_name,
        "Host_EDIPI": host_edipi,
        "Visitor_Name": visitor_name,
        "Building": building,
        "Room": room,
        "Time_Out": ""
    }

    row_hash = _compute_row_hash(row_data, previous_hash)

    # Record in separate ledger instead of the main log
    record_hash_entry(
        log_type="visitor",
        log_date=log_date,
        original_row_key=f"{timestamp}|{visitor_name}",
        previous_hash=previous_hash,
        row_hash=row_hash
    )

    # Write clean row to the main visitor log (no hash columns)
    with open(log_file, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=VISITOR_LOG_HEADERS)
        writer.writerow(row_data)


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
