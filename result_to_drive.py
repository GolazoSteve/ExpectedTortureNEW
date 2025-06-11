import os
import json
import re
import requests
import openai
from datetime import datetime, timedelta
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# --- CONFIGURATION ---
openai.api_key = os.environ["OPENAI_API_KEY"]
DRIVE_FOLDER_ID = os.environ["DRIVE_FOLDER_ID"]

# --- FIND MOST RECENT GIANTS GAME ---
def find_latest_giants_game():
    date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={date}"
    data = requests.get(url).json()
    for game in data["dates"][0]["games"]:
        teams = game["teams"]
        if "San Francisco Giants" in [teams["home"]["team"]["name"], teams["away"]["team"]["name"]]:
            return game["gamePk"], date
    return None, None

# --- GET FINAL SCORE & OPPONENT ---
def get_result(game_pk):
    url = f"https://statsapi.mlb.com/api/v1/game/{game_pk}/boxscore"
    data = requests.get(url).json()
    home, away = data["teams"]["home"], data["teams"]["away"]
    if home["team"]["name"] == "San Francisco Giants":
        giants, opp = home, away
    else:
        giants, opp = away, home
    gs, os = giants["teamStats"]["batting"]["runs"], opp["teamStats"]["batting"]["runs"]
    return ("Giants Win!" if gs > os else "Giants Lose."), gs, os, giants["team"]["name"], opp["team"]["name"]

# --- GET PLAY-BY-PLAY DATA ---
def get_play_by_play(game_pk):
    url = f"https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live"
    data = requests.get(url).json()
    return data["liveData"]["plays"]["allPlays"]

# --- FORMAT PLAY-BY-PLAY FOR PROMPT ---
def format_plays(plays):
    out = []
    for p in plays:
        try:
            inn = p["about"]["inning"]
            half = p["about"]["halfInning"]
            desc = p["result"]["description"]
            out.append(f"{half} {inn}: {desc}")
        except KeyError:
            continue
    return out

# --- SCORING SUMMARY FROM PLAYS ---
def summarise_runs(formatted_plays):
    score = {"SF": 0, "OPP": 0}
    timeline = []
    for play in formatted_plays:
        match = re.match(r"(top|bottom) (\d+): (.+)", play)
        if not match:
            continue
        half, inning, desc = match.groups()
        runs = desc.count("scores")
        if runs == 0:
            continue
        team = "SF" if half == "bottom" else "OPP"
        score[team] += runs
        timeline.append(f"{half.capitalize()} {inning}: {desc} → Giants {score['SF']}, Opponent {score['OPP']}")
    final = f"Final Score: Giants {score['SF']}, Opponent {score['OPP']}"
    return final, timeline

# --- GENERATE WADE RECAP WITH SCORE LOCKING ---
def generate_recap(plays, giants_score, opp_score, opp_name):
    with open("wade_prompt.txt", "r") as f:
        wade_preamble = f.read()

    formatted_plays = format_plays(plays)
    final_score_text, scoring_timeline = summarise_runs(formatted_plays)
    scoring_block = final_score_text + "\nScoring Timeline:\n" + "\n".join(scoring_timeline)

    prompt = (
        f"{wade_preamble}\n\n"
        f"The San Francisco Giants played the {opp_name} and won {giants_score}–{opp_score}.\n\n"
        f"{scoring_block}\n\n"
        f"Write a 400-word recap in WADE’s voice. Be vivid, specific, emotionally volatile, and accurate to the scoring summary. "
        f"Do not invent scores or alternate outcomes. Use the timeline above.\n\n"
        f"PLAY-BY-PLAY DATA:\n" + "\n".join(formatted_plays)
    )

    response = openai.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.9,
    )

    return response.choices[0].message.content.strip()

# --- GOOGLE DRIVE UPLOAD ---
def upload_to_drive(filepath, filename):
    creds = service_account.Credentials.from_service_account_file(
        "credentials.json", scopes=["https://www.googleapis.com/auth/drive"]
    )
    service = build("drive", "v3", credentials=creds)
    file_metadata = {"name": filename, "parents": [DRIVE_FOLDER_ID], "mimeType": "text/html"}
    media = MediaFileUpload(filepath, mimetype="text/html")
    service.files().create(body=file_metadata, media_body=media, fields="id").execute()

# --- MAIN RUNNER ---
if __name__ == "__main__":
    game_pk, game_date = find_latest_giants_game()
    if not game_pk:
        print("No recent Giants game found.")
        exit()

    outcome, g_score, o_score, g_team, o_team = get_result(game_pk)
    plays = get_play_by_play(game_pk)
    recap_html = generate_recap(plays, g_score, o_score, o_team)

    html_filename = f"summary-{game_date}.html"
    with open(html_filename, "w", encoding="utf-8") as f:
        f.write(f"<h2>{outcome}</h2>\n")
        f.write(f"<p>Final Score: {g_team} {g_score}, {o_team} {o_score}</p>\n")
        f.write(f"<div>{recap_html}</div>\n")

    upload_to_drive(html_filename, html_filename)
    print("✅ Uploaded:", html_filename)
