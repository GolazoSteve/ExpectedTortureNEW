import os
import json
import requests
import openai
from datetime import datetime, timedelta
import re

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# --- CONFIG ---
openai.api_key = os.environ["OPENAI_API_KEY"]
DRIVE_FOLDER_ID = os.environ["DRIVE_FOLDER_ID"]

# --- DETERMINE MOST RECENT GIANTS GAME ---
def find_most_recent_giants_game():
    yesterday = (datetime.now() - timedelta(days=1)).date().isoformat()
    url = f"https://statsapi.mlb.com/api/v1/schedule/games/?sportId=1&date={yesterday}"
    res = requests.get(url).json()
    games = res.get("dates", [])[0].get("games", [])
    for game in games:
        teams = game["teams"]
        if teams["away"]["team"]["name"] == "San Francisco Giants" or teams["home"]["team"]["name"] == "San Francisco Giants":
            return game["gamePk"], yesterday
    return None, None

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

# --- FORMAT PLAYS ---
def format_plays(plays):
    formatted = []
    for play in plays:
        try:
            inning = play["about"]["inning"]
            half = play["about"]["halfInning"]
            desc = play["result"]["description"]
            line = f"{half} {inning}: {desc}"
            formatted.append(line)
        except KeyError:
            continue
    return formatted

# --- NEW: Summarise runs with score tracking ---
def summarise_runs(formatted_plays):
    score = {'SF': 0, 'OPP': 0}
    timeline = []
    for play in formatted_plays:
        match = re.match(r'(top|bottom) (\d+): (.+)', play)
        if not match:
            continue
        half, inning, desc = match.groups()
        runs = desc.count("scores")
        if runs == 0:
            continue
        team = 'SF' if half == 'bottom' else 'OPP'
        score[team] += runs
        timeline.append(f"{half.capitalize()} {inning}: {desc} → Giants {score['SF']}, Opponent {score['OPP']}")
    final = f"Final Score: Giants {score['SF']}, Opponent {score['OPP']}"
    return final, timeline

# --- WADE RECAP GENERATION ---
def generate_recap(plays):
    with open("wade_prompt.txt", "r") as f:
        prompt = f.read()

    formatted_plays = format_plays(plays)
    final_score, score_timeline = summarise_runs(formatted_plays)

    scoring_summary = final_score + "\nScoring Timeline:\n" + "\n".join(score_timeline)

    full_prompt = (
        f"{prompt}\n\n"
        f"{scoring_summary}\n\n"
        f"Use this scoring sequence and final score exactly. Do not invent alternate scores.\n\n"
        f"PLAY BY PLAY DATA:\n" + "\n".join(formatted_plays) +
        "\n\nWrite a 300–400 word recap in WADE’s voice."
    )

    res = openai.chat.completions.create(
        model="gpt-4.1-nano",
        messages=[{"role": "user", "content": full_prompt}],
        temperature=0.6
    )

    return res.choices[0].message.content

# --- DRIVE UPLOAD ---
def upload_to_drive(html_path, html_filename):
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
    game_pk, game_date = find_most_recent_giants_game()
    if not game_pk:
        print("❌ No recent Giants game found.")
        exit()

    print(f"Checking result for: {game_date}")

    outcome, giants_score, opp_score, giants_team, opp_team = get_game_result(game_pk)
    print(outcome)

    plays = get_play_by_play(game_pk)
    recap_html = generate_recap(plays)

    html_filename = f"summary-{game_date}.html"
    html_path = f"./{html_filename}"

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(f"<h2>{outcome}</h2>\n")
        f.write(f"<p>Final Score: {giants_team} {giants_score}, {opp_team} {opp_score}</p>\n")
        f.write(f"<div>{recap_html}</div>\n")

    upload_to_drive(html_path, html_filename)
    print("✅ Recap uploaded.")
