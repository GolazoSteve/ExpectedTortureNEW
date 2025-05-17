import datetime
import pytz
import requests
import os
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# === CONFIG ===
TEAM_ID = 137  # San Francisco Giants
TIMEZONE = 'US/Pacific'
DRIVE_FOLDER_ID = 'YOUR_DRIVE_FOLDER_ID'  # replace with real folder ID
HTML_FILENAME = 'index.html'
SERVICE_ACCOUNT_FILE = 'credentials.json'

# === DATE HANDLING ===
def get_yesterday_date():
    pacific = pytz.timezone(TIMEZONE)
    now = datetime.datetime.now(pacific)
    yesterday = now - datetime.timedelta(days=1)
    return yesterday.strftime('%Y-%m-%d')

# === MLB API ===
def get_giants_result(date_str):
    url = f'https://statsapi.mlb.com/api/v1/schedule?sportId=1&teamId={TEAM_ID}&date={date_str}'
    res = requests.get(url).json()
    games = res.get("dates", [])
    
    if not games:
        return None  # No game yesterday

    game = games[0]['games'][0]
    home = game['teams']['home']
    away = game['teams']['away']
    giants_score = home['score'] if home['team']['id'] == TEAM_ID else away['score']
    opponent_score = away['score'] if home['team']['id'] == TEAM_ID else home['score']
    
    return "Giants Win!" if giants_score > opponent_score else "Giants Lose!"

# === HTML FILE ===
def generate_html(result_text):
    html = f"""<html><head><title>Giants Result</title></head>
<body><h1>{result_text}</h1></body></html>"""
    with open(HTML_FILENAME, 'w') as f:
        f.write(html)

# === UPLOAD TO GOOGLE DRIVE ===
def upload_to_drive():
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=['https://www.googleapis.com/auth/drive'])
    service = build('drive', 'v3', credentials=creds)
    
    file_metadata = {
        'name': HTML_FILENAME,
        'parents': [DRIVE_FOLDER_ID],
        'mimeType': 'text/html'
    }

    media = MediaFileUpload(HTML_FILENAME, mimetype='text/html', resumable=True)

    # Check if file already exists (optional enhancement)
    service.files().create(body=file_metadata, media_body=media, fields='id').execute()

# === MAIN ===
if __name__ == '__main__':
    date_str = get_yesterday_date()
    result = get_giants_result(date_str)
    
    if result:
        generate_html(result)
        upload_to_drive()
        print(f"Uploaded result: {result}")
    else:
        print("No Giants game yesterday.")
