import requests
from datetime import datetime, timezone
import pytz
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import json
import html

# 🔧 Налаштування
API_KEY = os.getenv("API_KEY")
CHANNEL_ID = 'UCfCVlxInB4VuaDFLGqEQqaA'
DATE_FROM = datetime(2025, 3, 10, tzinfo=timezone.utc)

# 🔗 Підключення до Google Sheets
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
try:
    with open("google-credentials.json", "r") as f:
        creds_dict = json.load(f)
    CREDS = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
    client = gspread.authorize(CREDS)
    sheet = client.open_by_url("https://docs.google.com/spreadsheets/d/1NtDI4dvKmukDH2NQSpDKsXCjIyVCJ-YjOx-wMfejd-c/edit").worksheet("Відео")
except FileNotFoundError as e:
    print(f"❌ Файл google-credentials.json не знайдено: {e}")
    exit(1)
except json.JSONDecodeError as e:
    print(f"❌ Помилка розшифровки JSON у google-credentials.json: {e}")
    exit(1)
except gspread.exceptions.APIError as e:
    print(f"❌ Помилка API Google Sheets при підключенні: {e}")
    exit(1)
except Exception as e:
    print(f"❌ Невідома помилка при підключенні до Google Sheets: {e}")
    exit(1)

def fetch_videos():
    base_url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "key": API_KEY,
        "channelId": CHANNEL_ID,
        "part": "snippet",
        "order": "date",
        "maxResults": 50,
        "type": "video",
        "publishedAfter": DATE_FROM.isoformat()
    }

    videos = []
    while True:
        try:
            resp = requests.get(base_url, params=params)
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"❌ Помилка запиту до API (fetch_videos): {e}")
            exit(1)
        data = resp.json()

        if not data.get("items", []):
            print("⚠️ Жодних відео не знайдено, завершення циклу.")
            break

        for item in data.get("items", []):
            title = html.unescape(item["snippet"]["title"])
            video_id = item["id"]["videoId"]
            video_url = f"https://www.youtube.com/watch?v={video_id}"
            published_at = datetime.fromisoformat(item["snippet"]["publishedAt"].replace("Z", "+00:00"))
            published_kyiv = published_at.astimezone(pytz.timezone("Europe/Kyiv"))
            thumbnail_url = item["snippet"]["thumbnails"]["high"]["url"]

            videos.append({
                "title": title,
                "id": video_id,
                "url": video_url,
                "date": published_kyiv.strftime("%Y-%m-%d"),
                "time": published_kyiv.strftime("%H:%M:%S"),
                "thumb": f'=IMAGE("{thumbnail_url}")'
            })

        if "nextPageToken" in data:
            params["pageToken"] = data["nextPageToken"]
        else:
            break

    print(f"✅ Отримано {len(videos)} відео.")
    return videos

def fetch_views_for_ids(video_ids):
    views_map = {}
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i+50]
        stats_url = "https://www.googleapis.com/youtube/v3/videos"
        stats_params = {
            "key": API_KEY,
            "part": "statistics",
            "id": ",".join(batch)
        }
        try:
            stats_resp = requests.get(stats_url, params=stats_params)
            stats_resp.raise_for_status()
        except requests.RequestException as e:
            print(f"❌ Помилка запиту статистики переглядів: {e}")
            exit(1)
        data = stats_resp.json()
        for item in data.get("items", []):
            views_map[item["id"]] = item["statistics"].get("viewCount", "0")
    print(f"✅ Отримано статистику переглядів для {len(views_map)} відео.")
    return views_map

def update_sheet(videos):
    try:
        all_rows = sheet.get_all_values()
        headers = ["Назва", "ID відео", "Посилання", "Дата", "Час", "Обкладинка", "Перегляди"]

        if not all_rows:
            sheet.append_row(headers)
            all_rows = [headers]

        existing_ids = {row[1]: idx for idx, row in enumerate(all_rows[1:], start=2)}
        new_rows = []

        for v in videos:
            if v["id"] not in existing_ids:
                print(f"📥 Додаю нове відео: {v['title']}")
                new_rows.append([
                    v["title"], v["id"], v["url"],
                    v["date"], v["time"], v["thumb"], "0"
                ])

        if new_rows:
            sheet.append_rows(new_rows)

        current_data = sheet.get_all_values()
        video_ids = [row[1] for row in current_data[1:]]
        views_map = fetch_views_for_ids(video_ids)
        views_column = []
        thumb_column = []

        for row in current_data[1:]:
            vid_id = row[1]
            thumb = f'=IMAGE("https://i.ytimg.com/vi/{vid_id}/hqdefault.jpg")'
            thumb_column.append([thumb])
            views_column.append([views_map.get(vid_id, "0")])

        sheet.update(range_name=f'F2:F{len(thumb_column)+1}', values=thumb_column, value_input_option='USER_ENTERED')
        sheet.update(range_name=f'G2:G{len(views_column)+1}', values=views_column)
        print("✅ Оновлено обкладинки і перегляди для всіх відео.")
    except gspread.exceptions.APIError as e:
        print(f"❌ Помилка API Google Sheets: {e}")
        exit(1)
    except Exception as e:
        print(f"❌ Невідома помилка: {e}")
        exit(1)

if __name__ == "__main__":
    videos = fetch_videos()
    update_sheet(videos)
