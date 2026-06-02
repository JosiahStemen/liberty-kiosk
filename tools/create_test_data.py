from pathlib import Path
import csv
import datetime
import hashlib
import random
import shutil
import sys

# ==================== DETERMINE PROJECT ROOT ====================
# Always write test data to the project root (where the main GUI, verifier, and export expect it)
# This works no matter how you launch the script (from root, from inside tools/, or with different CWD)
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent.resolve()
DATA_DIR = PROJECT_ROOT / "liberty_data"

print(f"Test data will be written to project root:\n  {DATA_DIR}\n")

# ==================== CONFIG ====================
NUM_DAYS = 10
ENTRIES_PER_DAY = 15
VISITOR_ENTRIES_PER_DAY = 8          # Fewer visitors than liberty checkouts
LOGS_DIR = DATA_DIR / "daily_logs"
VISITOR_LOGS_DIR = DATA_DIR / "visitor logs"
BACKUPS_DIR = DATA_DIR / "backups"
INTEGRITY_LEDGER = DATA_DIR / "integrity_ledger.csv"

# Realistic test data
RANKS = ["SGT", "CPL", "LCPL", "PFC", "SSGT", "GYSGT", "MSGT", "1STLT", "CAPT"]
FIRST_NAMES = ["John", "Michael", "David", "James", "Robert", "Thomas", "Daniel", "Christopher", "Matthew", "Joseph"]
LAST_NAMES = ["SMITH", "JOHNSON", "WILLIAMS", "BROWN", "JONES", "GARCIA", "MILLER", "DAVIS", "RODRIGUEZ", "MARTINEZ"]
DESTINATIONS = ["Monterey Downtown", "Cannery Row", "Fisherman's Wharf", "Santa Cruz Beach", "Big Sur", "Carmel Beach", "17-Mile Drive", "San Francisco", "Napa Valley", "Home"]


# Add lib folder to path so we can use the real hash function etc.
sys.path.insert(0, str(PROJECT_ROOT / "lib"))

# Use the exact same hash function as the main application
try:
    from liberty_common import _compute_row_hash as _compute_test_row_hash
except ImportError:
    def _compute_test_row_hash(row_data: dict, previous_hash: str) -> str:
        data_to_hash = {k: v for k, v in row_data.items() if k not in ("PreviousHash", "RowHash")}
        data_to_hash["PreviousHash"] = previous_hash or ""
        serialized = "|".join(f"{k}={data_to_hash[k]}" for k in sorted(data_to_hash.keys()))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

# ==================== SETUP FOLDERS ====================
LOGS_DIR.mkdir(parents=True, exist_ok=True)
VISITOR_LOGS_DIR.mkdir(parents=True, exist_ok=True)
BACKUPS_DIR.mkdir(parents=True, exist_ok=True)

print(f"Folders ready: {LOGS_DIR}, {VISITOR_LOGS_DIR}, and {BACKUPS_DIR}\n")

# Prepare integrity ledger (create header if new)
if not INTEGRITY_LEDGER.exists():
    with open(INTEGRITY_LEDGER, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "LedgerTimestamp", "LogType", "LogDate", "OriginalRowKey",
            "PreviousHash", "RowHash"
        ])

ledger_rows = []

today = datetime.date.today()

for i in range(NUM_DAYS):
    log_date = today - datetime.timedelta(days=i)
    liberty_log_file = LOGS_DIR / f"liberty_log_{log_date.isoformat()}.csv"
    visitor_log_file = VISITOR_LOGS_DIR / f"visitor_log_{log_date.isoformat()}.csv"
    
    print(f"Creating logs for {log_date}...")

    # === LIBERTY LOGS ===
    liberty_rows = []
    previous_liberty_hash = ""
    open_count_for_current = 0

    for _ in range(ENTRIES_PER_DAY):
        rank = random.choice(RANKS)
        first = random.choice(FIRST_NAMES)
        last = random.choice(LAST_NAMES)
        name = f"{last}, {first}"
        edipi = f"{random.randint(1000000000, 9999999999)}"
        last_name = last
        first_name = first

        # 25% chance of buddy (cleaner fields now)
        if random.random() < 0.25:
            buddy_first = random.choice(FIRST_NAMES)
            buddy_last = random.choice(LAST_NAMES)
            buddy_name = f"{buddy_last}, {buddy_first}"
            buddy_edipi = f"{random.randint(1000000000, 9999999999)}"
        else:
            buddy_name = "Self"
            buddy_edipi = ""

        destination = random.choice(DESTINATIONS)
        
        hour_out = random.randint(16, 23)
        minute_out = random.randint(0, 59)
        time_out = f"{log_date} {hour_out:02d}:{minute_out:02d}:00"
        
        is_current_day = (i == 0)
        if is_current_day:
            # For the current day: only leave TWO people not signed back in.
            # Everyone else must be signed in.
            if open_count_for_current < 2:
                time_in = ""
                open_count_for_current += 1
            else:
                hour_in = random.randint(1, 6)
                minute_in = random.randint(0, 59)
                time_in = f"{log_date + datetime.timedelta(days=1 if hour_in < 8 else 0)} {hour_in:02d}:{minute_in:02d}:00"
        else:
            # Previous days: everyone is signed back in
            hour_in = random.randint(1, 6)
            minute_in = random.randint(0, 59)
            time_in = f"{log_date + datetime.timedelta(days=1 if hour_in < 8 else 0)} {hour_in:02d}:{minute_in:02d}:00"

        row = {
            "Rank": rank,
            "Name": name,
            "EDIPI": edipi,
            "Last_Name": last_name,
            "First_Name": first_name,
            "Buddy_Name": buddy_name,
            "Buddy_EDIPI": buddy_edipi,
            "Destination": destination,
            "Time_out": time_out,
            "Time_in": time_in
        }

        row_hash = _compute_test_row_hash(row, previous_liberty_hash)
        ledger_rows.append({
            "LedgerTimestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "LogType": "liberty",
            "LogDate": log_date.isoformat(),
            "OriginalRowKey": f"{time_out}|{edipi}",
            "PreviousHash": previous_liberty_hash,
            "RowHash": row_hash
        })

        # Clean row for the actual log (no hash columns)
        liberty_rows.append([
            rank, name, edipi, last_name, first_name,
            buddy_name, buddy_edipi,
            destination, time_out, time_in
        ])

        previous_liberty_hash = row_hash

    # Write clean liberty log
    with open(liberty_log_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Rank", "Name", "EDIPI", "Last_Name", "First_Name",
            "Buddy_Name", "Buddy_EDIPI",
            "Destination", "Time_out", "Time_in"
        ])
        writer.writerows(liberty_rows)

    # === VISITOR LOGS ===
    visitor_rows = []
    previous_visitor_hash = ""

    for _ in range(VISITOR_ENTRIES_PER_DAY):
        host_rank = random.choice(RANKS)
        host_first = random.choice(FIRST_NAMES)
        host_last = random.choice(LAST_NAMES)
        host_name = f"{host_last}, {host_first}"
        host_edipi = f"{random.randint(1000000000, 9999999999)}"

        visitor_first = random.choice(FIRST_NAMES)
        visitor_last = random.choice(LAST_NAMES)
        visitor_name = f"{visitor_last}, {visitor_first}"

        building = str(random.randint(1, 30))
        room = str(random.randint(100, 399))

        hour = random.randint(17, 23)
        minute = random.randint(0, 59)
        timestamp = f"{log_date} {hour:02d}:{minute:02d}:00"

        # Decide if this visitor has already checked out (realistic mix)
        if random.random() < 0.55:   # ~45% still signed in (open visitors)
            time_out = ""
        else:
            # Checked out later the same night or early next morning
            out_hour = random.randint(20, 23)
            out_minute = random.randint(0, 59)
            if random.random() < 0.7:
                # Same night
                time_out = f"{log_date} {out_hour:02d}:{out_minute:02d}:00"
            else:
                # Early next morning
                time_out = f"{log_date + datetime.timedelta(days=1)} {random.randint(0, 5):02d}:{out_minute:02d}:00"

        row = {
            "Timestamp": timestamp,
            "Host_Rank": host_rank,
            "Host_Name": host_name,
            "Host_EDIPI": host_edipi,
            "Visitor_Name": visitor_name,
            "Building": building,
            "Room": room,
            "Time_Out": time_out
        }

        row_hash = _compute_test_row_hash(row, previous_visitor_hash)
        ledger_rows.append({
            "LedgerTimestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "LogType": "visitor",
            "LogDate": log_date.isoformat(),
            "OriginalRowKey": f"{timestamp}|{visitor_name}",
            "PreviousHash": previous_visitor_hash,
            "RowHash": row_hash
        })

        visitor_rows.append([
            timestamp, host_rank, host_name, host_edipi,
            visitor_name, building, room, time_out
        ])

        previous_visitor_hash = row_hash

    # Write clean visitor log
    with open(visitor_log_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Timestamp", "Host_Rank", "Host_Name", "Host_EDIPI",
            "Visitor_Name", "Building", "Room", "Time_Out"
        ])
        writer.writerows(visitor_rows)

    # === WRITE TO INTEGRITY LEDGER ===
    if ledger_rows:
        ledger_file_exists = INTEGRITY_LEDGER.exists()
        with open(INTEGRITY_LEDGER, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "LedgerTimestamp", "LogType", "LogDate", "OriginalRowKey", "PreviousHash", "RowHash"
            ])
            if not ledger_file_exists:
                writer.writeheader()
            writer.writerows(ledger_rows)

    # ==================== CREATE BACKUP + FILE HASH (for legacy verifier) ====================
    backup_file = BACKUPS_DIR / f"liberty_log_{log_date.isoformat()}.csv.bak"
    hash_file = BACKUPS_DIR / f"liberty_log_{log_date.isoformat()}.sha256"

    shutil.copy2(liberty_log_file, backup_file)

    with open(backup_file, "rb") as f:
        file_hash = hashlib.sha256(f.read()).hexdigest()

    with open(hash_file, "w", encoding="utf-8") as f:
        f.write(file_hash)

    print("   -> Liberty log, visitor log, and integrity ledger entries created")

print(f"\nDONE! Generated {NUM_DAYS} days of test data.")
print(f"   Location (project root): {PROJECT_ROOT}")
print(f"   Liberty logs:            {LOGS_DIR}")
print(f"   Visitor logs:            {VISITOR_LOGS_DIR}")
print(f"   Integrity ledger:        {INTEGRITY_LEDGER}")
print(f"   Backups (.bak + .sha256): {BACKUPS_DIR}")
print("\nThe verifier and export functions should now see this data correctly.")

