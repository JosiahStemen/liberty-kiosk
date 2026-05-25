from pathlib import Path
import csv
import datetime
import hashlib
import random
import shutil

# ==================== CONFIG ====================
NUM_DAYS = 10
ENTRIES_PER_DAY = 60
DATA_DIR = Path("liberty_data")
LOGS_DIR = DATA_DIR / "daily_logs"
BACKUPS_DIR = DATA_DIR / "backups"

# Realistic test data
RANKS = ["SGT", "CPL", "LCPL", "PFC", "SSGT", "GYSGT", "MSGT", "1STLT", "CAPT"]
FIRST_NAMES = ["John", "Michael", "David", "James", "Robert", "Thomas", "Daniel", "Christopher", "Matthew", "Joseph"]
LAST_NAMES = ["SMITH", "JOHNSON", "WILLIAMS", "BROWN", "JONES", "GARCIA", "MILLER", "DAVIS", "RODRIGUEZ", "MARTINEZ"]
DESTINATIONS = ["Monterey Downtown", "Cannery Row", "Fisherman's Wharf", "Santa Cruz Beach", "Big Sur", "Carmel Beach", "17-Mile Drive", "San Francisco", "Napa Valley", "Home"]

# ==================== SETUP FOLDERS ====================
LOGS_DIR.mkdir(parents=True, exist_ok=True)
BACKUPS_DIR.mkdir(parents=True, exist_ok=True)

print(f"✅ Folders ready: {LOGS_DIR} and {BACKUPS_DIR}\n")

# ==================== GENERATE TEST DATA ====================
today = datetime.date.today()

for i in range(NUM_DAYS):
    log_date = today - datetime.timedelta(days=i)
    log_file = LOGS_DIR / f"liberty_log_{log_date.isoformat()}.csv"
    
    print(f"Creating log for {log_date} with {ENTRIES_PER_DAY} entries...")

    rows = []
    for _ in range(ENTRIES_PER_DAY):
        rank = random.choice(RANKS)
        first = random.choice(FIRST_NAMES)
        last = random.choice(LAST_NAMES)
        name = f"{last} {first}"
        edipi = f"{random.randint(1000000000, 9999999999)}"   # 10-digit EDIPI
        last_name = last
        first_name = first

        # 30% chance of buddy
        if random.random() < 0.3:
            buddy_first = random.choice(FIRST_NAMES)
            buddy_last = random.choice(LAST_NAMES)
            buddy_name = f"{buddy_last} {buddy_first}"
            buddy_edipi = f"{random.randint(1000000000, 9999999999)}"
            buddy_last_name = buddy_last
            buddy_first_name = buddy_first
        else:
            buddy_name = "Self"
            buddy_edipi = ""
            buddy_last_name = ""
            buddy_first_name = ""

        destination = random.choice(DESTINATIONS)
        
        hour_out = random.randint(16, 23)
        minute_out = random.randint(0, 59)
        time_out = f"{log_date} {hour_out:02d}:{minute_out:02d}:00"
        
        if random.random() > 0.6:
            time_in = ""
        else:
            hour_in = random.randint(1, 6)
            minute_in = random.randint(0, 59)
            time_in = f"{log_date + datetime.timedelta(days=1 if hour_in < 8 else 0)} {hour_in:02d}:{minute_in:02d}:00"

        rows.append([
            rank, name, edipi, last_name, first_name,
            buddy_name, buddy_edipi, buddy_last_name, buddy_first_name,
            destination, time_out, time_in
        ])

    # Write the log file with FULL new header
    with open(log_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Rank", "Name", "EDIPI", "Last_Name", "First_Name",
            "Buddy_Name", "Buddy_EDIPI", "Buddy_Last_Name", "Buddy_First_Name",
            "Destination", "Time_out", "Time_in"
        ])
        writer.writerows(rows)

    # ==================== CREATE BACKUP + HASH ====================
    backup_file = BACKUPS_DIR / f"liberty_log_{log_date.isoformat()}.csv.bak"
    hash_file = BACKUPS_DIR / f"liberty_log_{log_date.isoformat()}.sha256"

    shutil.copy2(log_file, backup_file)

    with open(backup_file, "rb") as f:
        file_hash = hashlib.sha256(f.read()).hexdigest()

    with open(hash_file, "w", encoding="utf-8") as f:
        f.write(file_hash)

    print(f"   → Backup + SHA256 hash created\n")

print(f"\n🎉 DONE! Generated {NUM_DAYS} test log files with the NEW full buddy columns.")
print(f"   Logs are in:      {LOGS_DIR}")
print(f"   Backups + hashes in: {BACKUPS_DIR}")
EOF

