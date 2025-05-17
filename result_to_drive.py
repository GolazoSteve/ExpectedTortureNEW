import os
import json
import requests
from datetime import datetime, timedelta
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from pytz import timezone
import openai

# --- SETUP ---

SCOPES = ['https://www.googleapis.com/auth/drive']
SERVICE_ACCOUNT_FILE = 'credentials.json'
DRIVE_FOLDER_ID = os.getenv('DRIVE_FOLDER_ID')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

# --- DATE LOGIC ---

sf_tz = timezone('America/Los_Angeles')
today = datetime.now(sf_tz).date()
yesterday = today - timedelta(days=1)

# --- GAME DATA ---

def get_game_result(game_date):
    url = f"https://statsapi.mlb.com/api/v1/schedule?teamId=137&date={game_date}"
    resp = requests.get(url).json()
    dates = resp.get("dates")
    if not dates:
        return None, None, None
    game = dates[0]['games'][0]
    teams = game['teams']
    status = game['status']['detailedState']
    is_final = status in ['Final', 'Game Over']
    if not is_final:
        return None, None, None
    home = teams['home']
    away = teams['away']
    home_name = home['team']['name']
    away_name = away['team']['name']
    home_score = home['score']
    away_score = away['score']
    result = "Giants Win!" if (
        (home_name == "San Francisco Giants" and home_score > away_score) or
        (away_name == "San Francisco Giants" and away_score > home_score)
    ) else "Giants Lose."
    final_score = f"{away_name} {away_score}, {home_name} {home_score}"
    game_pk = game['gamePk']
    return result, final_score, game_pk

# --- OPENAI GENERATION ---

def generate_recap(game_date, game_pk):
    with open("wade_prompt.txt", "r", encoding="utf-8") as f:
        base_prompt = f.read()

    play_url = f"https://statsapi.mlb.com/api/v1/game/{game_pk}/playByPlay"
    plays = requests.get(play_url).json()["allPlays"]

    play_summaries = []
    for play in plays:
        desc = play.get("result", {}).get("description")
        if desc:
            play_summaries.append(desc)
    context = "\n".join(play_summaries[:150])  # trim for token safety

    openai.api_key = OPENAI_API_KEY
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": base_prompt},
            {"role": "user", "content": f"Write a 300–400 word recap of the Giants game on {game_date}. Here are play-by-play summaries:\n\n{context}"}
        ],
        temperature=0.9
    )
    return response.choices[0].message.content

# --- HTML + DRIVE ---

def upload_to_drive():
    result, score, game_pk = get_game_result(yesterday.isoformat())
    if not result:
        print("No game found.")
        return

    print(f"Result: {result}")

    recap = generate_recap(yesterday.isoformat(), game_pk)

    html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <title>Giants Recap {yesterday}</title>
</head>
<body>
  <h1>{result}</h1>
  <h2>Final Score: {score}</h2>
  <h2>WADE Recap</h2>
  <div>{recap}</div>
</body>
</html>
"""
    filename = f"result-{yesterday}.html"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(html)

    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    service = build('drive', 'v3', credentials=creds)

    file_metadata = {
        'name': filename,
        'parents': [DRIVE_FOLDER_ID],
        'mimeType': 'text/html'
    }
    media = MediaFileUpload(filename, mimetype='text/html')

    # Optional: Delete existing file with same name first
    query = f"name='{filename}' and '{DRIVE_FOLDER_ID}' in parents and trashed=false"
    existing = service.files().list(q=query, spaces='drive').execute()
    for file in existing.get('files', []):
        service.files().delete(fileId=file['id']).execute()

    uploaded = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
    print(f"Uploaded as {filename} with ID {uploaded['id']}")

if __name__ == "__main__":
    upload_to_drive()
