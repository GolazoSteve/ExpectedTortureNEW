import os
import datetime
import pytz
import requests
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# === CONFIGURATION ===
TEAM_ID = 137  # San Francisco Giants
TIMEZONE = 'US/Pacific'
HTML_FILENAME = 'index.html'
SERVICE_ACCOUNT_FILE = 'credentials.json'
DRIVE_FOLDER_ID = os.getenv('DRIVE_FOLDER_ID')

# === GET YESTERDAY’S DATE IN PACIFIC TIME ===
def get_yesterday_date_str():
    pacific = pytz.timezone(TIMEZONE)
    now = datetime.datetime.now(pacific)
    yesterday = now - datetime.timedelta(days=1)
    return yesterday.strftime('%Y-%m-%d')

# === GET GAME RESULT ===
def get_giants_result(date_str):
    url = f'https://statsapi.mlb.com/api/v1/schedule?sportId=1&teamId={TEAM_ID}&date={date_str}'
    res = requests.get(url).json()
    games = res.get("dates", [])

    if not games:
        return None  # No Giants game that day

    game = games[0]['games'][0]
    home = game['teams']['home']
    away = game['teams']['away']

    giants_is_home = home['team']['id'] == TEAM_ID
    giants_score = home['score'] if giants_is_home else away['score']
    opponent_score = away['score'] if giants_is_home else home['score']

    return "Giants Win!" if giants_score > opponent_score else "Giants Lose!"

# === GENERATE HTML FILE ===
def generate_html(content):
    html = f"""<html><head><title>Giants Result</title></head>
<body><h1>{content}</h1></body></html>"""
    with open(HTML_FILENAME, 'w') as f:
        f.write(html)

# === UPLOAD TO GOOGLE DRIVE ===
def upload_to_drive():
    creds = Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE,
        scopes=['https://www.googleapis.com/auth/drive']
    )
    service = build('drive', 'v3', credentials=creds)

    file_metadata = {
        'name': HTML_FILENAME,
        'parents': [DRIVE_FOLDER_ID],
        'mimeType': 'text/html'
    }

    media = MediaFileUpload(HTML_FILENAME, mimetype='text/html', resumable=False)
    service.files().create(body=file_metadata, media_body=media, fields='id').execute()

# === MAIN ===
if __name__ == '__main__':
    date_str = get_yesterday_date_str()
    print(f"Checking result for: {date_str}")
    
    result = get_giants_result(date_str)
    result_text = result if result else "No Giants game yesterday."

    print(f"Result: {result_text}")
    generate_html(result_text)
    upload_to_drive()
    print("HTML uploaded to Google Drive.")
