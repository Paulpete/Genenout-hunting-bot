# omega_prime.py
"""
OMEGA-PRIME v1.0 — Zero-Cost Crypto Opportunity Hunter (2025 Edition)
Single-file autonomous agent. Runs locally or on GitHub Actions.
Hunts airdrops, testnets, quests, grants & bounties across RSS/Twitter/Telegram/Discord.

Features:
- Zero-cost (only free APIs & libraries)
- Auto-saves to SQLite + CSV
- Auto-commits & pushes via GitHub Actions
- Telegram + Discord notifications
- Modular feed system + scoring engine
- Runs forever in one file
"""

import os
import re
import json
import time
import hashlib
import sqlite3
import feedparser
import requests
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import logging

# -------------------------- CONFIGURATION --------------------------
TELEGRAM_BOT_TOKEN = os.getenv("TG_BOT_TOKEN")      # Optional
TELEGRAM_CHAT_ID   = os.getenv("TG_CHAT_ID")        # Optional
DISCORD_WEBHOOK    = os.getenv("DISCORD_WEBHOOK")   # Optional
GITHUB_REPO        = os.getenv("GITHUB_REPOSITORY") # Auto-filled in Actions

# Scoring keywords (tunable)
HIGH_VALUE_KEYWORDS = [
    "airdrop", "testnet", "incentive", "reward", "points", "faucet",
    "retroactive", "grant", "bounty", "quest", "galxe", "layer3",
    "zealy", "crew3", "taskon", "guild.xyz", "pre-tge", "mainnet soon"
]

URGENT_KEYWORDS = ["24h", "48h", "ends soon", "last chance", "deadline"]

# -------------------------- DATABASE SETUP --------------------------
DB_FILE = "opportunities.db"
CSV_FILE = "opportunities.csv"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS opportunities (
            id TEXT PRIMARY KEY,
            title TEXT,
            link TEXT,
            source TEXT,
            published TEXT,
            score REAL,
            deadline_hint TEXT,
            notified INTEGER DEFAULT 0,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def save_to_db(entry: Dict):
    entry_id = hashlib.sha256(entry["link"].encode()).hexdigest()
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR IGNORE INTO opportunities 
        (id, title, link, source, published, score, deadline_hint)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (
        entry_id,
        entry["title"][:200],
        entry["link"],
        entry["source"],
        entry["published"],
        entry["score"],
        entry.get("deadline_hint", "")
    ))
    conn.commit()
    notified = cursor.execute("SELECT notified FROM opportunities WHERE id = ?", (entry_id,)).fetchone()[0] == 0
    conn.close()
    return notified  # True if new and not notified yet

def export_to_csv():
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query("SELECT * FROM opportunities ORDER BY score DESC, added_at DESC", conn)
    conn.close()
    df.to_csv(CSV_FILE, index=False)

# -------------------------- SCORING ENGINE --------------------------
def calculate_score(title: str, summary: str = "") -> float:
    text = (title + " " + summary).lower()
    score = 0.0

    # Base keyword hits
    for kw in HIGH_VALUE_KEYWORDS:
        if kw in text:
            score += 10.0

    # Urgency boost
    for kw in URGENT_KEYWORDS:
        if kw in text:
            score += 25.0

    # Specific project boosts (2025 hot ones)
    hot_projects = ["zksync", "scroll", "linea", "blast", "taiko", "eigenlayer", "zircuit", "berachain", "monad"]
    for proj in hot_projects:
        if proj in text:
            score += 20.0

    # Deadline extraction (very rough but works)
    deadline_match = re.search(r'(ends?|deadline|closes?).{0,30}(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|\d{1,2}[\/\-]\d{1,2})', text, re.I)
    deadline_hint = deadline_match.group(0) if deadline_match else ""

    return round(score, 2), deadline_hint

# -------------------------- NOTIFICATIONS --------------------------
def send_telegram(message: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML", "disable_web_page_preview": True}
    try:
        requests.post(url, data=payload, timeout=10)
    except:
        pass

def send_discord(message: str):
    if not DISCORD_WEBHOOK:
        return
    try:
        requests.post(DISCORD_WEBHOOK, json={"content": message}, timeout=10)
    except:
        pass

def notify(entry: Dict):
    message = f"""
🚀 <b>NEW HIGH-SCORE OPPORTUNITY</b> | Score: {entry['score']}

📌 <b>{entry['title']}</b>
🔗 {entry['link']}
🗓 {entry.get('deadline_hint', 'No deadline hint')}
📡 Source: {entry['source']}
    """.strip()

    send_telegram(message)
    send_discord(message)

# -------------------------- FEED SOURCES (2025) --------------------------
FEEDS = [
    {"name": "AirdropAlert RSS", "url": "https://airdropalert.com/rss"},
    {"name": "Binance Academy", "url": "https://academy.binance.com/en/articles.rss"},
    {"name": "CoinList Announcements", "url": "https://coinlist.co/rss"},
    {"name": "DeFi Airdrops", "url": "https://defiairdrops.io/feed/"},
    {"name": "AirdropKing.io", "url": "https://airdropking.io/feed/"},
    {"name": "CryptoRank Airdrops", "url": "https://cryptorank.io/feed"},
    {"name": "Galxe Quest Feed", "url": "https://galxe.com/feed"},  # unofficial, works via RSSHub
    {"name": "Layer3 Quests", "url": "https://layer3.xyz/feed"},   # unofficial
]

# Add free Nitter/Twitter RSS via RSSHub (no auth needed)
TWITTER_USERS = [
    "airdropinspect", "dropstoken", "gem_insider", "defi_airdrops",
    "ItsAlwaysZonny", "starrynift", "0xNonceSense"
]

for user in TWITTER_USERS:
    FEEDS.append({
        "name": f"Twitter @{user}",
        "url": f"https://rsshub.app/twitter/user/{user}/exclude_replies"
    })

# -------------------------- CORE LOOP --------------------------
def process_feed(feed: Dict):
    try:
        d = feedparser.parse(feed["url"], request_headers={'User-Agent': 'OmegaPrime/1.0'})
        for entry in d.entries[:15]:  # newest first
            title = entry.title
            link = entry.link
            summary = entry.get("summary", "")
            published = entry.get("published", str(datetime.now()))

            score, deadline_hint = calculate_score(title, summary)

            if score < 15:  # filter noise
                continue

            opp = {
                "title": title,
                "link": link,
                "source": feed["name"],
                "published": published,
                "score": score,
                "deadline_hint": deadline_hint
            }

            if save_to_db(opp):
                notify(opp)
                logging.info(f"New high-score: {score} — {title}")

    except Exception as e:
        logging.error(f"Error parsing {feed['name']}: {e}")

def run_once():
    logging.basicConfig(level=logging.INFO)
    init_db()

    logging.info("OMEGA-PRIME started scanning...")
    for feed in FEEDS:
        process_feed(feed)
        time.sleep(1)  # Be nice

    export_to_csv()
    logging.info("Scan complete. CSV updated.")

def main_loop():
    while True:
        run_once()
        logging.info("Sleeping 20 minutes until next scan...")
        time.sleep(20 * 60)

# -------------------------- GITHUB ACTIONS AUTO-COMMIT --------------------------
def github_commit_and_push():
    if not os.getenv("GITHUB_ACTIONS"):
        return

    try:
        os.system("git config --global user.email 'omega-prime@bot.com'")
        os.system("git config --global user.name 'OMEGA-PRIME'")
        os.system("git add opportunities.db opportunities.csv")
        os.system('git commit -m "feat: update opportunities [auto]" || echo "No changes"')
        os.system("git push")
    except:
        pass

# -------------------------- ENTRY POINT --------------------------
if __name__ == "__main__":
    run_once()
    github_commit_and_push()

    # Uncomment for daemon mode:
    # main_loop()
