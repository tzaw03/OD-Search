import sqlite3
from datetime import datetime

# Connect to (or create) the database file
conn = sqlite3.connect('music_bot.db')
cursor = conn.cursor()

# Create the 'songs' table if it doesn't exist
cursor.execute('''
CREATE TABLE IF NOT EXISTS songs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id TEXT NOT NULL,
    file_name TEXT NOT NULL,
    title TEXT,
    artist TEXT,
    album TEXT,
    file_path TEXT
)
''')

# Create the 'members' table with new columns for expiry date and status
cursor.execute('''
CREATE TABLE IF NOT EXISTS members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER UNIQUE NOT NULL,
    first_name TEXT,
    added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expiry_date TIMESTAMP NOT NULL,
    status TEXT NOT NULL DEFAULT 'active' -- can be 'active', 'expired', 'banned'
)
''')

# Save the changes and close the connection
conn.commit()
conn.close()

print("Database 'music_bot.db' and updated tables ('songs', 'members') created successfully.")
