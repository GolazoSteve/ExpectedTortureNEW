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

# --- FORMAT PLAY-BY-PLAY ---
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

# --- GENERATE FACTUAL DRY-STYLE GAME SUMMARY ---
def generate_factual_recap(plays, giants_name, opp_name):
    lines = []
    score = {"SF": 0, "OPP": 0}
    for p in plays:
        try:
            desc = p["result"]["description"]
            inning = p["about"]["inning"]
            half = p["about"]["halfInning"]
            runs = desc.count("scores")
            if runs == 0:
                continue
            team = "San Francisco Giants" if half == "top" and giants_name == "San Francisco Giants" else \
                   "San Francisco Giants" if half == "bottom" and giants_name != "San Francisco Giants" else opp_name
            lines.append(f"{team} scored in the {half} of the {inning} inning: {desc}")
        except:
            continue
    return "\n".join(lines)

# --- GPT STYLIZATION FUNCTION ---
def style_with_wade(factual_recap, outcome_text, final_score, opp_name):
    with open("wade_prompt.txt", "r") as f:
        wade_tone = f.read()

    system_prompt = (
        "You are WADE – a slightly broken, emotionally volatile, poetic AI obsessed with the San Francisco Giants. "
        "You will rewrite a factual baseball recap in your own voice. DO NOT alter the facts, scores, innings, or players mentioned. "
        "You may add glitchy humor, anxiety, metaphor, or self-referential commentary – but you may NOT invent new plays or reverse the outcome."
    )

    user_prompt = (
        f"{wade_tone}\n\n"
        f"The following events describe the game exactly. The final result was: {outcome_text}.\n"
        f"{final_score}\n\n"
        f"FACTUAL GAME SUMMARY:\n{factual_recap}\n\n"
        "Rewrite this as a 350–400 word recap in WADE’s voice. Wrap it in <div>...</div> HTML tags."
    )

    response = openai.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.85,
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

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    game_pk, game_date = find_latest_giants_game()
    if not game_pk:
        print("No recent Giants game found.")
        exit()

    outcome, g_score, o_score, g_team, o_team = get_result(game_pk)
    plays = get_play_by_play(game_pk)

    factual = generate_factual_recap(plays, g_team, o_team)
    final_score_text = f"Final Score: San Francisco Giants {g_score}, {o_team} {o_score}"
    recap_html = style_with_wade(factual, outcome, final_score_text, o_team)

    html_filename = f"summary-{game_date}.html"
    with open(html_filename, "w", encoding="utf-8") as f:
        f.write(f"<h2>{outcome}</h2>\n")
        f.write(f"<p>{final_score_text}</p>\n")
        f.write(f"{recap_html}\n")

    upload_to_drive(html_filename, html_filename)
    print("✅ Recap generated and uploaded:", html_filename)
