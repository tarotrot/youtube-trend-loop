"""
YouTube トレンド自動取得・要約・スプレッドシート反映スクリプト

【処理の流れ】
1. YouTube Data API v3 でトレンド動画(TOP10)を取得
2. Gemini API(無料枠)で各動画を要約 + 全体傾向を分析(Loop: 品質評価→再生成)
3. Google Sheets API でスプレッドシートに追記

【必要な環境変数】(GitHub Actions の Secrets に設定する)
- YOUTUBE_API_KEY       : YouTube Data API v3 のAPIキー
- GEMINI_API_KEY        : Gemini APIキー(Google AI Studioで無料発行)
- GOOGLE_SERVICE_ACCOUNT_JSON : Google サービスアカウントのJSON(文字列そのまま)
- SPREADSHEET_ID        : 反映先スプレッドシートのID(URLの/d/と/editの間の文字列)
"""

import os
import json
import datetime
import time
import requests
import gspread
from google.oauth2.service_account import Credentials

# ============ 設定 ============
REGION_CODE = "JP"          # トレンド取得地域
MAX_RESULTS = 10            # 取得件数
SHEET_NAME = "trends"       # スプレッドシートのシート名
GEMINI_MODEL = "gemini-2.5-flash"   # 無料枠で使えるモデル

YOUTUBE_API_KEY = os.environ["YOUTUBE_API_KEY"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
GOOGLE_SERVICE_ACCOUNT_JSON = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
SPREADSHEET_ID = os.environ["SPREADSHEET_ID"]


# ============ 1. YouTubeトレンド取得 ============
def fetch_trending_videos():
    url = "https://www.googleapis.com/youtube/v3/videos"
    params = {
        "part": "snippet,statistics",
        "chart": "mostPopular",
        "regionCode": REGION_CODE,
        "maxResults": MAX_RESULTS,
        "key": YOUTUBE_API_KEY,
    }
    res = requests.get(url, params=params, timeout=30)
    res.raise_for_status()
    items = res.json().get("items", [])

    videos = []
    for i, item in enumerate(items, start=1):
        snippet = item["snippet"]
        stats = item.get("statistics", {})
        videos.append({
            "rank": i,
            "title": snippet.get("title", ""),
            "channel": snippet.get("channelTitle", ""),
            "description": snippet.get("description", "")[:500],
            "category_id": snippet.get("categoryId", ""),
            "view_count": stats.get("viewCount", "N/A"),
        })
    return videos


# ============ 2. Gemini APIで要約(Loop: 自己評価付き) ============
def call_gemini(prompt: str) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    res = requests.post(
        url,
        headers={"content-type": "application/json"},
        params={"key": GEMINI_API_KEY},
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": 500},
        },
        timeout=60,
    )
    res.raise_for_status()
    data = res.json()
    candidates = data.get("candidates", [])
    if not candidates:
        return ""
    parts = candidates[0].get("content", {}).get("parts", [])
    return "".join(p.get("text", "") for p in parts)


def summarize_video(video: dict) -> str:
    """1本の動画を要約。Loop: 3行以内かを自己評価し、超えていたら書き直させる。"""
    prompt = f"""以下のYouTubeトレンド動画の情報から、内容を3行以内で要約してください。
タイトルの言い換えではなく、動画を見なくても中身がわかるような要約にしてください。
出力は要約文のみ、前置きや番号は不要です。

タイトル: {video['title']}
チャンネル: {video['channel']}
説明文: {video['description']}
"""
    summary = call_gemini(prompt).strip()

    # --- Loop: 品質チェック(3行超なら1回だけ書き直させる) ---
    if summary.count("\n") >= 3 or len(summary) > 200:
        retry_prompt = prompt + f"""
【フィードバック】前回の要約が長すぎます:
「{summary}」
これを2〜3行、150文字以内に圧縮して書き直してください。要約文のみ出力してください。
"""
        summary = call_gemini(retry_prompt).strip()

    return summary


def analyze_overall_trend(videos: list, summaries: list) -> str:
    """全体傾向を1〜2文で分析。"""
    joined = "\n".join(f"- {v['title']}({v['category_id']}): {s}" for v, s in zip(videos, summaries))
    prompt = f"""以下は本日のYouTubeトレンドTOP{len(videos)}とその要約です。
これ全体を見て、どんなジャンル・テーマが伸びているか、傾向を1〜2文で簡潔に述べてください。
出力は傾向コメントのみにしてください。

{joined}
"""
    return call_gemini(prompt).strip()


# ============ 3. Google Sheetsに反映 ============
def append_to_sheet(videos: list, summaries: list, trend_comment: str):
    creds_dict = json.loads(GOOGLE_SERVICE_ACCOUNT_JSON)
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    gc = gspread.authorize(creds)

    sh = gc.open_by_key(SPREADSHEET_ID)
    try:
        ws = sh.worksheet(SHEET_NAME)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=SHEET_NAME, rows=1000, cols=8)
        ws.append_row(["日付", "順位", "動画タイトル", "チャンネル名", "再生回数", "要約", "カテゴリID", "全体傾向コメント"])

    today = datetime.date.today().isoformat()
    rows = []
    for i, (video, summary) in enumerate(zip(videos, summaries)):
        rows.append([
            today,
            video["rank"],
            video["title"],
            video["channel"],
            video["view_count"],
            summary,
            video["category_id"],
            trend_comment if i == 0 else "",  # 傾向コメントは先頭行のみ
        ])
    ws.append_rows(rows, value_input_option="USER_ENTERED")


# ============ メイン処理 ============
def main():
    print("1. YouTubeトレンド取得中...")
    videos = fetch_trending_videos()
    print(f"   -> {len(videos)}件取得")

    print("2. Gemini APIで要約中...")
    summaries = []
    for v in videos:
        s = summarize_video(v)
        summaries.append(s)
        print(f"   [{v['rank']}] {v['title'][:30]}... -> 要約完了")
        time.sleep(1)  # レート制限対策

    print("3. 全体傾向を分析中...")
    trend_comment = analyze_overall_trend(videos, summaries)
    print(f"   -> {trend_comment}")

    print("4. スプレッドシートに反映中...")
    append_to_sheet(videos, summaries, trend_comment)
    print("完了しました。")


if __name__ == "__main__":
    main()
