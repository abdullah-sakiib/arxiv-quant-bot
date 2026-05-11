import time
import requests
import google.generativeai as genai
import os
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

# ── Config ────────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID        = os.environ["CHAT_ID"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

MAX_PAPERS = 8

# arXiv RSS feeds by category — pick one or combine
# q-fin    = all quant finance
# q-fin.TR = trading & market microstructure
# q-fin.CP = computational finance
# q-fin.RM = risk management
# q-fin.ST = statistical finance
# q-fin.PM = portfolio management
RSS_URL = "https://rss.arxiv.org/rss/q-fin"


# ── Fetch today's papers via RSS ──────────────────────────────────────────────
def fetch_papers():
    headers = {"User-Agent": "arxiv-digest-bot/1.0 (personal research tool)"}
    response = requests.get(RSS_URL, headers=headers, timeout=30)
    response.raise_for_status()

    root = ET.fromstring(response.content)
    ns = {"dc": "http://purl.org/dc/elements/1.1/"}

    papers = []
    items = root.findall(".//item")

    for item in items[:MAX_PAPERS]:
        title = item.findtext("title", "").strip()
        link  = item.findtext("link", "").strip()
        desc  = item.findtext("description", "").strip()

        # Clean HTML tags from description
        import re
        desc = re.sub(r"<[^>]+>", "", desc).strip()

        if title and desc:
            papers.append({"title": title, "link": link, "abstract": desc})

    return papers


# ── Summarize with Gemini ─────────────────────────────────────────────────────
from groq import Groq  # add at top

def summarize(paper):
    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    abstract = paper['abstract'][:800]

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{
            "role": "user",
            "content": f"""Summarize for a quant finance practitioner in 3 lines:
Title: {paper['title']}
Abstract: {abstract}

Format exactly:
🎯 What it does: (1 sentence)
📐 Method: (1 sentence)
💡 Quant use: (1 sentence)"""
        }],
        max_tokens=200,
        temperature=0.3
    )
    return response.choices[0].message.content.strip()

# ── Send message to Telegram ──────────────────────────────────────────────────
def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    r = requests.post(url, json=payload)
    if not r.ok:
        # Fallback: strip markdown if special chars cause issues
        payload["parse_mode"] = "HTML"
        payload["text"] = text.replace("*", "").replace("_", "")
        requests.post(url, json=payload)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    papers = fetch_papers()

    if not papers:
        send_telegram("📭 No new quant finance papers on arXiv today.")
        return

    date_str = datetime.now(timezone.utc).strftime("%B %d, %Y")
    header = (
        f"📊 *arXiv Quant Finance Digest*\n"
        f"📅 {date_str}\n"
        f"📄 {len(papers)} new paper(s) today\n"
        f"{'─' * 30}"
    )
    send_telegram(header)

    for i, paper in enumerate(papers, 1):
        try:
            summary = summarize(paper)
        except Exception as e:
            summary = f"_(Error: {str(e)[:200]})_"

        title = paper['title'] if len(paper['title']) < 100 else paper['title'][:97] + "..."

        msg = (
            f"*{i}. {title}*\n\n"
            f"{summary}\n\n"
            f"🔗 [Read paper]({paper['link']})"
        )
        send_telegram(msg)

        # Wait 6 seconds between Gemini calls (max 10 req/min on free tier)
        time.sleep(6)

    send_telegram("✅ That's all for today! See you tomorrow.")


if __name__ == "__main__":
    main()
