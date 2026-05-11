import arxiv
import google.generativeai as genai
import requests
import os
from datetime import datetime, timedelta, timezone

# ── Config ────────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID        = os.environ["CHAT_ID"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

MAX_PAPERS = 8   # Max papers to send per day (adjust as you like)

# ── arXiv categories you want ─────────────────────────────────────────────────
# q-fin.*     = all quant finance
# q-fin.TR    = trading and market microstructure
# q-fin.CP    = computational finance
# q-fin.RM    = risk management
# q-fin.PM    = portfolio management
# q-fin.ST    = statistical finance
CATEGORY = "cat:q-fin.*"   # Change to e.g. "cat:q-fin.TR" to narrow down


# ── Fetch papers from arXiv ───────────────────────────────────────────────────
def fetch_papers():
    client = arxiv.Client()
    search = arxiv.Search(
        query=CATEGORY,
        max_results=40,
        sort_by=arxiv.SortCriterion.SubmittedDate,
        sort_order=arxiv.SortOrder.Descending,
    )

    yesterday = datetime.now(timezone.utc) - timedelta(days=1)
    papers = []

    for result in client.results(search):
        if result.published >= yesterday:
            papers.append(result)
        if len(papers) >= MAX_PAPERS:
            break

    return papers


# ── Summarize with Gemini ─────────────────────────────────────────────────────
def summarize(paper):
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-2.0-flash")

    prompt = f"""You are a quant finance researcher. Summarize this paper for a practitioner.
Be concise and focus on practical relevance.

Title: {paper.title}
Abstract: {paper.summary}

Reply in exactly this format (no extra text):
🎯 *What it does:* (1-2 sentences)
📐 *Method:* (1 sentence on the technique used)
💡 *Quant relevance:* (1 sentence — trading, risk, forecasting, etc.)
"""

    response = model.generate_content(prompt)
    return response.text.strip()


# ── Send message to Telegram ──────────────────────────────────────────────────
def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    response = requests.post(url, json=payload)

    # If Markdown fails (special chars in title), retry as plain text
    if not response.ok:
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
            summary = f"_(Could not summarize: {e})_"

        # Truncate long titles
        title = paper.title if len(paper.title) < 100 else paper.title[:97] + "..."

        msg = (
            f"*{i}. {title}*\n\n"
            f"{summary}\n\n"
            f"🔗 [Read paper]({paper.entry_id})"
        )
        send_telegram(msg)

    send_telegram("✅ That's all for today! See you tomorrow.")


if __name__ == "__main__":
    main()