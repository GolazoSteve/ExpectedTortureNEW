import os
import json
import requests
import openai
from datetime import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# --- CONFIG ---
openai.api_key = os.environ["OPENAI_API_KEY"]
DRIVE_FOLDER_ID = os.environ["DRIVE_FOLDER_ID"]
game_pk = 777891  # A's at Giants — May 16, 2025
html_filename = f"summary-2025-05-16.html"
html_path = f"./{html_filename}"

# --- MLB RESULT FETCH ---
def get_game_result(game_pk):
    url = f"https://statsapi.mlb.com/api/v1/game/{game_pk}/boxscore"
    res = requests.get(url).json()
    teams = res["teams"]
    away = teams["away"]
    home = teams["home"]

    if home["team"]["name"] == "San Francisco Giants":
        giants = home
        opp = away
    else:
        giants = away
        opp = home

    giants_score = giants["teamStats"]["batting"]["runs"]
    opp_score = opp["teamStats"]["batting"]["runs"]
    outcome = "Giants Win!" if giants_score > opp_score else "Giants Lose."

    return outcome, giants_score, opp_score, giants["team"]["name"], opp["team"]["name"]

# --- PLAY BY PLAY FETCH ---
def get_play_by_play(game_pk):
    url = f"https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live"
    res = requests.get(url).json()
    all_plays = res["liveData"]["plays"]["allPlays"]
    return all_plays

# --- WADE RECAP GENERATION ---
def generate_recap(plays):
    with open("wade_prompt.txt", "r") as f:
        prompt = f.read()

    formatted_plays = "\n".join(
        f"{play['about']['inningHalf']} {play['about']['inning']}: {play['result']['description']}"
        for play in plays
    )

    full_prompt = f"{prompt}\n\nPLAY BY PLAY DATA:\n{formatted_plays}\n\nWrite a 300–400 word recap in WADE’s voice."

    res = openai.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": full_prompt}],
        temperature=0.7
    )

    return res.choices[0].message.content

# --- DRIVE UPLOAD ---
def upload_to_drive():
    creds_path = "credentials.json"
    with open(creds_path, "r") as f:
        creds_data = json.load(f)

    creds = service_account.Credentials.from_service_account_info(
        creds_data,
        scopes=["https://www.googleapis.com/auth/drive.file"]
    )
    service = build("drive", "v3", credentials=creds)

    file_metadata = {
        "name": html_filename,
        "parents": [DRIVE_FOLDER_ID],
        "mimeType": "text/html"
    }
    media = MediaFileUpload(html_path, mimetype="text/html")
    service.files().create(body=file_metadata, media_body=media, fields="id").execute()

# --- MAIN LOGIC ---
if __name__ == "__main__":
    print(f"Checking result for: 2025-05-16")

    outcome, giants_score, opp_score, giants_team, opp_team = get_game_result(game_pk)
    print(outcome)

    plays = get_play_by_play(game_pk)
    recap_html = generate_recap(plays)

    # Append recap to basic HTML
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(f"<h2>{outcome}</h2>\n")
        f.write(f"<p>Final Score: {giants_team} {giants_score}, {opp_team} {opp_score}</p>\n")
        f.write(f"<div>{recap_html}</div>\n")

    upload_to_drive()
    print("✅ Recap uploaded.")
