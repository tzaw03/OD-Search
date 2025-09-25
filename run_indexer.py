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
# GitHub Secrets ကနေ credentials တွေကိုဖတ်ခြင်း
TENANT_ID = os.getenv("O365_TENANT_ID")
CLIENT_ID = os.getenv("O365_CLIENT_ID")
CLIENT_SECRET = os.getenv("O365_CLIENT_SECRET")
TARGET_USER_ID = os.getenv("O365_USER_ID")

AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
SCOPE = ["https://graph.microsoft.com/.default"]
DB_FILE = "music_bot.db"
SUPPORTED_EXTENSIONS = ['.flac', '.wav', '.m4a', '.dsf']

# --- Database Connection ---
conn = sqlite3.connect(DB_FILE)
cursor = conn.cursor()
print("Successfully connected to database.")

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
        print("\nFailed to acquire access token.")
        print(f"Error: {result.get('error')}")
        print(f"Error Description: {result.get('error_description')}")
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
            title = tags.get('title', ['Unknown Title'])[0]
            artist = tags.get('artist', ['Unknown Artist'])[0]
            album = tags.get('album', ['Unknown Album'])[0]
            return title, artist, album
    except Exception as e:
        print(f"  Could not read metadata for {file_name}. Error: {e}")
    return "Unknown Title", "Unknown Artist", "Unknown Album"

def scan_folder(headers, item_id, current_path):
    """OneDrive Folder များကို Recursive Scan လုပ်ခြင်း"""
    endpoint = f"https://graph.microsoft.com/v1.0/users/{TARGET_USER_ID}/drive/items/{item_id}/children"
    response = requests.get(endpoint, headers=headers)
    if response.status_code != 200:
        print(f"Error scanning folder {item_id}: {response.text}")
        return

    items = response.json().get('value', [])
    for item in items:
        item_name = item.get('name')
        new_path = f"{current_path}/{item_name}"
        
        if 'folder' in item:
            print(f"Scanning subfolder: {new_path}")
            scan_folder(headers, item.get('id'), new_path)
        
        elif 'file' in item:
            file_extension = os.path.splitext(item_name)[1].lower()
            if file_extension in SUPPORTED_EXTENSIONS:
                print(f"Found music file: {new_path}")
                
                # Download file content
                download_url = item.get('@microsoft.graph.downloadUrl')
                if not download_url:
                    print(f"  No download URL for {item_name}")
                    continue

                file_response = requests.get(download_url)
                if file_response.status_code == 200:
                    title, artist, album = get_metadata(file_response.content, item_name)
                    
                    # Save to database
                    cursor.execute(
                        "INSERT INTO songs (file_id, file_name, title, artist, album, file_path) VALUES (?, ?, ?, ?, ?, ?)",
                        (item.get('id'), item_name, title, artist, album, new_path)
                    )
                    conn.commit()
                    print(f"  Indexed: {artist} - {album} - {title}")
                else:
                    print(f"  Failed to download {item_name}")

def main():
    token = get_access_token()
    if not token:
        return

    headers = {'Authorization': f'Bearer {token}'}
    
    print("\nStarting OneDrive scan from root folder...")
    # "root" folder ကနေစပြီး scan လုပ်ပါမယ်။
    scan_folder(headers, 'root', '')
    
    print("\nIndexing complete.")
    conn.close()

if __name__ == "__main__":
    main()
