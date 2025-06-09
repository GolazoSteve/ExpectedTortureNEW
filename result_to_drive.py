import os
import json
import requests
import openai
from datetime import datetime, timedelta

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

# --- NEW: Extract structured scoring summary ---
def extract_scoring_summary(plays):
    summary = []
    score = {"away": 0, "home": 0}
    team_lookup = {}

    for play in plays:
        result = play.get("result", {})
        about = play.get("about", {})
        runners = play.get("runners", [])
        desc = result.get("description", "")
        inning = about.get("inning")
        half = about.get("halfInning")

        batting_team = about.get("battingTeamId")
        if batting_team:
            team_lookup[batting_team] = play["team"]["name"] if "team" in play else ""

        for runner in runners:
            if runner.get("details", {}).get("event") in ["score"]:
                runner_name = runner["details"].get("runner", {}).get("fullName", "Runner")
                team = half.upper()
                line = f"{team} {inning}: {runner_name} scores on {desc}"
                summary.append(line)

    return summary

# --- WADE RECAP GENERATION ---
def generate_recap(plays):
    with open("wade_prompt.txt", "r") as f:
        prompt = f.read()

    formatted_plays = []
    for play in plays:
        try:
            inning = play["about"]["inning"]
            half = play["about"]["halfInning"]
            desc = play["result"]["description"]
            line = f"{half} {inning}: {desc}"
            formatted_plays.append(line)
        except KeyError:
            continue

    scoring_summary = extract_scoring_summary(plays)
    scoring_text = "Scoring Summary:\n" + "\n".join(scoring_summary) + "\n\n"

    full_prompt = f"{prompt}\n\n{scoring_text}PLAY BY PLAY DATA:\n" + "\n".join(formatted_plays) + "\n\nWrite a 300–400 word recap in WADE’s voice."

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
