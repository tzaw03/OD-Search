import os
import sqlite3
import json
import requests
import msal
from mutagen.flac import FLAC
from mutagen.mp4 import MP4
from mutagen.wave import WAVE
from mutagen.dsf import DSF
from io import BytesIO

# --- Configuration ---
TENANT_ID = os.getenv("O365_TENANT_ID")
CLIENT_ID = os.getenv("O365_CLIENT_ID")
CLIENT_SECRET = os.getenv("O365_CLIENT_SECRET")
TARGET_USER_ID = os.getenv("O365_USER_ID")

AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
SCOPE = ["https://graph.microsoft.com/.default"]
DB_FILE = "music_bot.db"
SUPPORTED_EXTENSIONS = ['.flac', '.wav', '.m4a', '.dsf']

# --- Global DB Connection ---
conn = None
cursor = None

def get_access_token():
    """Microsoft Graph API အတွက် Access Token ရယူခြင်း"""
    app = msal.ConfidentialClientApplication(
        client_id=CLIENT_ID,
        authority=AUTHORITY,
        client_credential=CLIENT_SECRET
    )
    print("Attempting to acquire token...")
    result = app.acquire_token_for_client(scopes=SCOPE)
    if "access_token" in result:
        print("Access Token acquired successfully.")
        return result['access_token']
    else:
        print(f"\nFailed to acquire access token: {result.get('error_description')}")
        return None

def get_metadata(file_content, file_name):
    """Mutagen ကိုသုံးပြီး သီချင်း metadata ဖတ်ခြင်း"""
    try:
        file_like_object = BytesIO(file_content)
        tags = None
        if file_name.lower().endswith('.flac'):
            tags = FLAC(fileobj=file_like_object)
        elif file_name.lower().endswith('.m4a'):
            tags = MP4(fileobj=file_like_object)
        elif file_name.lower().endswith('.wav'):
            tags = WAVE(fileobj=file_like_object)
        elif file_name.lower().endswith('.dsf'):
            tags = DSF(fileobj=file_like_object)

        if tags:
            title = tags.get('title', [os.path.splitext(file_name)[0]])[0]
            artist = tags.get('artist', ['Unknown Artist'])[0]
            album = tags.get('album', ['Unknown Album'])[0]
            return title, artist, album
    except Exception as e:
        print(f"  Could not read metadata for {file_name}. Error: {e}")
    return "Unknown Title", "Unknown Artist", "Unknown Album"

def scan_folder(headers, item_id, current_path):
    """OneDrive Folder များကို Recursive Scan လုပ်ပြီး songs နှင့် albums table များကို data ဖြည့်ခြင်း"""
    endpoint = f"https://graph.microsoft.com/v1.0/users/{TARGET_USER_ID}/drive/items/{item_id}/children"
    try:
        response = requests.get(endpoint, headers=headers)
        response.raise_for_status() # Raise an exception for bad status codes
    except requests.exceptions.RequestException as e:
        print(f"Error scanning folder {item_id}: {e}")
        return

    items = response.json().get('value', [])
    music_files_in_folder = [item for item in items if 'file' in item and os.path.splitext(item.get('name', ''))[1].lower() in SUPPORTED_EXTENSIONS]
    
    if music_files_in_folder:
        first_song = music_files_in_folder[0]
        download_url = first_song.get('@microsoft.graph.downloadUrl')
        if download_url:
            file_response = requests.get(download_url)
            if file_response.status_code == 200:
                _, artist, album = get_metadata(file_response.content, first_song.get('name'))
                if album != "Unknown Album":
                    try:
                        cursor.execute(
                            "INSERT INTO albums (album_name, artist_name, folder_id, folder_path) VALUES (?, ?, ?, ?)",
                            (album, artist, item_id, current_path)
                        )
                        conn.commit()
                        print(f"++ Indexed Album Folder: '{album}' by {artist}")
                    except sqlite3.IntegrityError:
                        pass # Folder already exists, skip.
                    except Exception as e:
                        print(f"Error inserting album to DB: {e}")

    for item in items:
        item_name = item.get('name')
        new_path = f"{current_path}/{item_name}"
        
        if 'folder' in item:
            print(f"Scanning subfolder: {new_path}")
            scan_folder(headers, item.get('id'), new_path)
        
        elif 'file' in item and item in music_files_in_folder:
            print(f"Found music file: {new_path}")
            download_url = item.get('@microsoft.graph.downloadUrl')
            if not download_url: continue

            file_response = requests.get(download_url)
            if file_response.status_code == 200:
                title, artist, album = get_metadata(file_response.content, item_name)
                cursor.execute(
                    "INSERT INTO songs (file_id, file_name, title, artist, album, file_path) VALUES (?, ?, ?, ?, ?, ?)",
                    (item.get('id'), item_name, title, artist, album, new_path)
                )
                conn.commit()
                print(f"  -- Indexed Song: {artist} - {album} - {title}")

def main():
    global conn, cursor
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        print("Successfully connected to database.")

        token = get_access_token()
        if not token:
            return

        headers = {'Authorization': f'Bearer {token}'}
        
        print("\nStarting OneDrive scan from root folder...")
        scan_folder(headers, 'root', '')
        
        print("\nIndexing complete.")
    except Exception as e:
        print(f"An error occurred in main: {e}")
    finally:
        if conn:
            conn.close()
            print("Database connection closed.")

if __name__ == "__main__":
    main()
