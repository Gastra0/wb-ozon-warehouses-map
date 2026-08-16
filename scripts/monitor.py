#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WB Warehouse Monitor — GitHub Actions daily update."""

import os, sys, json, re, math, hashlib, datetime, traceback
import urllib.request, urllib.parse
import xml.etree.ElementTree as ET

# Change to repo root so all relative paths work
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT  = os.path.dirname(SCRIPT_DIR)
os.chdir(REPO_ROOT)
print(f"CWD: {os.getcwd()}")

TODAY    = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
NOW      = datetime.datetime.now(datetime.timezone.utc).strftime("%H:%M UTC")
SEEN_FILE = ".github/seen_uids.json"
DATA_FILE = "wh_data.json"
LOG_FILE  = "news_raw.md"

KEYWORDS = [
    "wildberries", "вайлдберриз", "склад wildberries",
    "логистический центр wildberries", "вб склад",
    "логістичний центр wildberries", "wb склад",
]

FEEDS = [
    ("Meduza",            "https://meduza.io/rss/all"),
    ("Fontanka",          "https://www.fontanka.ru/export/rss.xml"),
    ("BBC Russian",       "https://feeds.bbci.co.uk/russian/rss.xml"),
    ("Ukrainska Pravda",  "https://www.pravda.com.ua/rss/view_news/"),
    ("RBK",               "https://rssexport.rbc.ru/rbcnews/news/20/full.rss"),
    ("T-Journal",         "https://tjournal.ru/rss"),
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml,application/xml,text/xml,*/*",
}

print(f"[{TODAY} {NOW}] WB Monitor starting")
print(f"DATA_FILE exists: {os.path.exists(DATA_FILE)}")

# ── helpers ────────────────────────────────────────────────────────────────
def fetch(url):
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.read()
    except Exception as e:
        print(f"  fetch {url}: {e}")
        return b""

def parse_rss(raw):
    items = []
    try:
        root = ET.fromstring(raw)
        for item in root.iter("item"):
            items.append({
                "title": (item.findtext("title")       or "").strip(),
                "link":  (item.findtext("link")        or "").strip(),
                "desc":  (item.findtext("description") or "").strip(),
                "pub":   (item.findtext("pubDate")     or "").strip(),
            })
    except Exception as e:
        print(f"  XML parse error: {e}")
    return items

def relevant(item):
    text = (item["title"] + " " + item["desc"]).lower()
    return any(k in text for k in KEYWORDS)

def uid(item):
    return hashlib.md5((item["link"] + item["title"]).encode()).hexdigest()[:10]

# ── load seen uids ─────────────────────────────────────────────────────────
os.makedirs(".github", exist_ok=True)
seen = set()
try:
    seen = set(json.load(open(SEEN_FILE, encoding="utf-8")))
    print(f"Loaded {len(seen)} seen UIDs")
except Exception as e:
    print(f"seen_uids: {e} (starting fresh)")

# ── collect new articles ───────────────────────────────────────────────────
all_hits = []
for name, url in FEEDS:
    raw   = fetch(url)
    items = parse_rss(raw) if raw else []
    print(f"  {name}: {len(items)} items", end="")
    rel   = [i for i in items if relevant(i)]
    print(f" → {len(rel)} relevant")
    for item in rel:
        u = uid(item)
        if u not in seen:
            item["source"] = name
            item["uid"]    = u
            all_hits.append(item)
            print(f"    NEW: {item['title'][:80]}")

# update seen
seen.update(h["uid"] for h in all_hits)
json.dump(list(seen)[-3000:], open(SEEN_FILE, "w", encoding="utf-8"))

# ── write log ──────────────────────────────────────────────────────────────
log = [f"# WB Monitor — {TODAY}\n_Зібрано: {NOW} · нових: {len(all_hits)}_\n\n"]
if all_hits:
    for h in all_hits:
        log += [f"## [{h['source']}] {h['title']}\n",
                f"**Дата:** {h['pub']}\n**Посилання:** {h['link']}\n\n"]
else:
    log.append("_Нових повідомлень не знайдено._\n")
open(LOG_FILE, "w", encoding="utf-8").writelines(log)

if not all_hits:
    print("No new articles → no Claude call needed. Exiting cleanly.")
    sys.exit(0)

# ── Claude analysis ────────────────────────────────────────────────────────
print(f"\nSending {len(all_hits)} articles to Claude Haiku...")

try:
    import anthropic
except ImportError:
    print("ERROR: anthropic package not installed"); sys.exit(1)

api_key = os.environ.get("ANTHROPIC_API_KEY", "")
if not api_key:
    print("ERROR: ANTHROPIC_API_KEY not set"); sys.exit(1)

try:
    current_data = json.load(open(DATA_FILE, encoding="utf-8"))
except Exception as e:
    print(f"ERROR loading {DATA_FILE}: {e}"); sys.exit(1)

warehouses = current_data["warehouses"]
articles_text = ""
for h in all_hits[:10]:
    articles_text += (
        f"\n---\nSource: {h['source']}\nTitle: {h['title']}\n"
        f"URL: {h['link']}\nDate: {h['pub']}\nSnippet: {h['desc'][:400]}\n"
    )

SYSTEM = """You are a data analyst updating a JSON database of Wildberries warehouse statuses in Russia.
Analyse the news articles and return ONLY a JSON object. No prose. No markdown fences.

Status values: "ok" | "hit" | "burned"
  burned = fire/explosion with significant damage confirmed
  hit    = strike confirmed but fire was minor/contained OR company says operational
  ok     = no confirmed strike

Return: {"warehouses": [...], "changes_summary": "brief EN summary"}

For unchanged warehouses, keep exactly as-is. Only update entries with confirmed new info.
If a new city/warehouse is mentioned that's not in the list, add it with guessed tier.
date in Ukrainian, e.g. "16 серпня"
note: short Ukrainian sentence with facts."""

USER = (
    f"Current warehouses:\n{json.dumps(warehouses, ensure_ascii=False, indent=2)}\n\n"
    f"New articles:\n{articles_text}\n\n"
    "Return updated JSON."
)

try:
    client   = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model      = "claude-haiku-4-5",
        max_tokens = 8000,
        system     = SYSTEM,
        messages   = [{"role": "user", "content": USER}],
    )
    raw = response.content[0].text.strip()
    print(f"Claude: in={response.usage.input_tokens} out={response.usage.output_tokens} tokens")
except Exception as e:
    print(f"ERROR calling Claude API: {e}")
    traceback.print_exc()
    sys.exit(1)

# parse response
try:
    clean  = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.M).strip()
    result = json.loads(clean)
    new_warehouses = result["warehouses"]
    summary = result.get("changes_summary", "")
    print(f"Summary: {summary}")
except Exception as e:
    print(f"ERROR parsing Claude response: {e}")
    print("Raw response (first 800 chars):", raw[:800])
    traceback.print_exc()
    sys.exit(1)

# save
current_data["warehouses"]   = new_warehouses
current_data["last_updated"] = TODAY
json.dump(current_data, open(DATA_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"Saved {DATA_FILE}")

# rebuild map
print("Rebuilding index.html...")
import subprocess
result = subprocess.run(
    [sys.executable, "scripts/build_map.py"],
    capture_output=True, text=True, cwd=REPO_ROOT
)
print(result.stdout)
if result.returncode != 0:
    print("BUILD ERROR:", result.stderr)
    sys.exit(1)

print("Done ✓")
