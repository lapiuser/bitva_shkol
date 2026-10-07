import sqlite3
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
source = BASE / 'data' / 'leaderboard.db'
backups = BASE / 'backups'
backups.mkdir(exist_ok=True)

timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
destination = backups / f'leaderboard_{timestamp}.db'

if not source.exists():
    raise SystemExit('data/leaderboard.db not found. Start the app once first.')

with sqlite3.connect(source) as src, sqlite3.connect(destination) as dst:
    src.backup(dst)

print(f'Backup created: {destination}')
