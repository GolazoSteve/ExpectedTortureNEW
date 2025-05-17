import os
import requests
from datetime import datetime, timedelta
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import pytz

SERVICE_ACCOUNT_FILE = 'credentials.json'

def get_yesterday_game_pk(team_id=137):
    pacific = pytz.timezone('US/Pacific')
    yesterday = datetime.now(pacific) - timedelta(days=1)
    date_str = yesterday.strftime('%Y-%m-%d')

    url = f"https://statsapi.mlb.com/api/v1/schedule?teamId={team_id}&date={date_str}"
    response = requests.get(url).json()
    games = response.get('dates', [])
    if games and games[0]['games']:
        return games[0]['games'][0]['gamePk']
    return None

def get_giants_result(game_pk):
    url = f"https://statsapi.mlb.com/api/v1/game/{game_pk}/boxscore"
    data = requests.get(url).json()
    home = data['teams']['home']
    away = data['teams']['away']
    home_name = home['team']['name']
    away_name = away['team']['name']
    home_score = home['teamStats']['teamSkaterStats']['runs']
    away_score = away['teamStats']['teamSkaterStats']['runs']
    giants_is_home = home['team']['id'] == 137
    giants_score = home_score if giants_is_home else away_score
    opponent_score = away_score if giants_is_home else home_score
    result = "Giants Win!" if giants_score > opponent_score else "Giants Lose!"
    print(f"Result: {result}")
    return result

def get_box_score_html(game_pk):
    url = f"https://statsapi.mlb.com/api/v1/game/{game_pk}/boxscore"
    data = requests.get(url).json()

    lines = []
    for team_type in ['home', 'away']:
        team = data['teams'][team_type]
        name = team['team']['name']
        players = team['players']

        lines.append(f"<h3>{name}</h3>")
        lines.append("<table border='1' cellpadding='4' cellspacing='0'>")
        lines.append("<tr><th>Player</th><th>AB</th><th>R</th><th>H</th><th>RBI</th></tr>")

        for player in players.values():
            stats = player.get('stats', {}).get('batting', {})
            if stats.get('atBats', 0) > 0:
                lines.append(f"<tr><td>{player['person']['fullName']}</td>"
                             f"<td>{stats.get('atBats', '')}</td>"
                             f"<td>{stats.get('runs', '')}</td>"
                             f"<td>{stats.get('hits', '')}</td>"
                             f"<td>{stats.get('rbi', '')}</td></tr>")
        lines.append("</table><br>")

    return "\n".join(lines)

def upload_to_drive():
    creds = Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=['https://www.googleapis.com/auth/drive']
    )
    service = build('drive', 'v3', credentials=creds)

    game_pk = get_yesterday_game_pk()
    if not game_pk:
        print("No game found.")
        return

    result = get_giants_result(game_pk)
    box_score_html = get_box_score_html(game_pk)

    html_content = f"""
    <html>
      <head><title>Giants Daily Result</title></head>
      <body>
        <h1>{result}</h1>
        <h2>Box Score</h2>
        {box_score_html}
      </body>
    </html>
    """

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html_content)

    file_metadata = {
        'name': f"giants-result-{datetime.now().strftime('%Y-%m-%d')}.html",
        'parents': [os.environ['DRIVE_FOLDER_ID']],
        'mimeType': 'text/html'
    }
    media = MediaFileUpload('index.html', mimetype='text/html')
    service.files().create(body=file_metadata, media_body=media, fields='id').execute()

if __name__ == "__main__":
    print(f"Checking result for: {(datetime.now(pytz.timezone('US/Pacific')) - timedelta(days=1)).strftime('%Y-%m-%d')}")
    upload_to_drive()
