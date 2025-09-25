import sqlite3

conn = sqlite3.connect('music_bot.db')
cursor = conn.cursor()

# Songs table to store individual tracks
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

# Members table for subscription management
cursor.execute('''
CREATE TABLE IF NOT EXISTS members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER UNIQUE NOT NULL,
    first_name TEXT,
    added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expiry_date TIMESTAMP NOT NULL,
    status TEXT NOT NULL DEFAULT 'active'
)
''')

# Download tokens table for one-time links
cursor.execute('''
CREATE TABLE IF NOT EXISTS download_tokens (
    token TEXT PRIMARY KEY,
    song_id INTEGER,
    album_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
''')

# Albums table to store folder information
cursor.execute('''
CREATE TABLE IF NOT EXISTS albums (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    album_name TEXT NOT NULL,
    artist_name TEXT,
    folder_id TEXT NOT NULL UNIQUE,
    folder_path TEXT
)
''')

conn.commit()
conn.close()

print("Database 'music_bot.db' and all tables (including albums) created successfully.")
