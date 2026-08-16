#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WB Warehouse Monitor — runs daily via GitHub Actions.
1. Fetches RSS feeds for news about Wildberries warehouse attacks
2. If new articles found → asks Claude to analyse and update wh_data.json
3. Rebuilds index.html from updated data
"""

import os, json, re, math, hashlib, datetime, urllib.request, urllib.parse
import xml.etree.ElementTree as ET
import anthropic

# ── Config ──────────────────────────────────────────────────────────────────
FEEDS = [
    ("Meduza",           "https://meduza.io/rss/all"),
    ("Fontanka",         "https://www.fontanka.ru/export/rss.xml"),
    ("BBC Russian",      "https://feeds.bbci.co.uk/russian/rss.xml"),
    ("Ukrainska Pravda", "https://www.pravda.com.ua/rss/view_news/"),
    ("RBK",              "https://rssexport.rbc.ru/rbcnews/news/20/full.rss"),
    ("T-J",              "https://tjournal.ru/rss"),
]
KEYWORDS = [
    "wildberries", "вайлдберриз", "склад wildberries",
    "логистический центр wildberries", "вб склад", "wb склад",
    "логістичний центр wildberries",
]
SEEN_FILE   = ".github/seen_uids.json"
DATA_FILE   = "wh_data.json"
HTML_FILE   = "index.html"
LOG_FILE    = "news_raw.md"
TODAY       = datetime.datetime.utcnow().strftime("%Y-%m-%d")
NOW         = datetime.datetime.utcnow().strftime("%H:%M UTC")

# ── Helpers ──────────────────────────────────────────────────────────────────
def fetch(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=12) as r:
            return r.read()
    except Exception as e:
        print(f"  fetch error {url}: {e}")
        return b""

def parse_rss(raw):
    items = []
    try:
        root = ET.fromstring(raw)
        for item in root.iter("item"):
            t = (item.findtext("title")       or "").strip()
            l = (item.findtext("link")        or "").strip()
            d = (item.findtext("description") or "").strip()
            p = (item.findtext("pubDate")     or "").strip()
            items.append({"title": t, "link": l, "desc": d, "pub": p})
    except:
        pass
    return items

def relevant(item):
    text = (item["title"] + " " + item["desc"]).lower()
    return any(k in text for k in KEYWORDS)

def uid(item):
    return hashlib.md5((item["link"] + item["title"]).encode()).hexdigest()[:10]

# ── Step 1: collect new articles ─────────────────────────────────────────────
print(f"[{TODAY} {NOW}] Starting WB monitor")
os.makedirs(".github", exist_ok=True)

seen = set()
try:
    seen = set(json.load(open(SEEN_FILE)))
except:
    pass

hits = []
for name, url in FEEDS:
    raw = fetch(url)
    if not raw:
        continue
    for item in parse_rss(raw):
        if relevant(item):
            u = uid(item)
            if u not in seen:
                item["source"] = name
                item["uid"]    = u
                hits.append(item)
                print(f"  NEW [{name}]: {item['title'][:80]}")

# update seen
seen.update(h["uid"] for h in hits)
json.dump(list(seen)[-3000:], open(SEEN_FILE, "w"))

# write log
log_lines = [
    f"# WB Monitor — {TODAY}\n",
    f"_Зібрано о {NOW} · нових статей: {len(hits)}_\n\n",
]
if hits:
    for h in hits:
        log_lines += [
            f"## [{h['source']}] {h['title']}\n",
            f"**Дата:** {h['pub']}\n",
            f"**Посилання:** {h['link']}\n\n",
        ]
else:
    log_lines.append("_Нових повідомлень не знайдено._\n")
open(LOG_FILE, "w", encoding="utf-8").writelines(log_lines)

if not hits:
    print("No new articles — skipping Claude call and map rebuild")
    raise SystemExit(0)

# ── Step 2: ask Claude to analyse and update data ────────────────────────────
print(f"\nSending {len(hits)} articles to Claude for analysis...")

current_data = json.load(open(DATA_FILE, encoding="utf-8"))
warehouses   = current_data["warehouses"]

articles_text = ""
for h in hits[:12]:   # cap at 12 to stay within context/cost
    articles_text += f"\n---\nSource: {h['source']}\nTitle: {h['title']}\nURL: {h['link']}\nDate: {h['pub']}\nSnippet: {h['desc'][:400]}\n"

SYSTEM = """You are a data analyst updating a JSON database of Wildberries warehouse statuses in Russia.
You receive news articles and a current warehouse list.
You must return ONLY a valid JSON object — no prose, no markdown, no explanation.

Rules:
- status values: "ok" | "hit" | "burned"
  • "burned" = confirmed fire/explosion with significant damage
  • "hit" = strike confirmed but fire was minor/contained OR company says facility is operational
  • "ok" = no confirmed strike
- Only update entries where the article provides NEW confirmed information
- If an article mentions a city/location NOT in the warehouse list, add it as a new entry
- Preserve all existing fields; only change status, date, note for affected warehouses
- For new warehouses: guess tier from context (hub=very large, large=large, mid=smaller/SC)
- date format: "D місяця" in Ukrainian, e.g. "16 серпня"
- note: short Ukrainian sentence with key facts (casualties, fire area, source)
- Return JSON: {"warehouses": [...same structure as input...], "changes_summary": "brief EN summary of what changed"}
"""

USER = f"""Current warehouse data:
{json.dumps(warehouses, ensure_ascii=False, indent=2)}

New articles to analyse:
{articles_text}

Return updated warehouse list as JSON."""

client = anthropic.Anthropic()
response = client.messages.create(
    model   = "claude-haiku-4-5",
    max_tokens = 8000,
    system  = SYSTEM,
    messages= [{"role": "user", "content": USER}],
)

raw_response = response.content[0].text.strip()
print(f"Claude tokens: in={response.usage.input_tokens} out={response.usage.output_tokens}")

# parse Claude's response
try:
    # strip possible ```json fences
    clean = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_response, flags=re.M).strip()
    result = json.loads(clean)
    updated_warehouses = result["warehouses"]
    summary = result.get("changes_summary", "no summary")
    print(f"Changes: {summary}")
except Exception as e:
    print(f"ERROR parsing Claude response: {e}")
    print("Raw:", raw_response[:500])
    raise SystemExit(1)

# save updated data
current_data["warehouses"] = updated_warehouses
current_data["last_updated"] = TODAY
json.dump(current_data, open(DATA_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"Updated {DATA_FILE}")

# ── Step 3: rebuild index.html ───────────────────────────────────────────────
print("Rebuilding index.html...")
import subprocess, sys
result = subprocess.run([sys.executable, "scripts/build_map.py"], capture_output=True, text=True)
print(result.stdout)
if result.returncode != 0:
    print("BUILD ERROR:", result.stderr)
    raise SystemExit(1)

print("Done ✓")
