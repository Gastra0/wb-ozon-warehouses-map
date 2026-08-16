import urllib.request, xml.etree.ElementTree as ET

HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
WORKING_INSTANCES = [
    "https://rsshub.rssforever.com",
    "https://hub.slarker.me",
    "https://rsshub.ktachibana.party",
]
CHANNELS = [
    "bazabazon",      # Baza — confirmed incidents
    "shot_shot",      # SHOT — operational news
    "rybar",          # Rybar — military analytics
    "mchsgov",        # MChS — official fires
    "readovkanews",   # Readovka — field news
    "astrapress",     # Astra press account
    "ostorozhno_novosti", # Obz news
    "warfakes",
    "rian_ru",        # RIA Novosti
    "tass_agency",    # TASS
]

results = []
for channel in CHANNELS:
    success = False
    for base in WORKING_INSTANCES:
        url = f"{base}/telegram/channel/{channel}"
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=10) as r:
                items = len(list(ET.fromstring(r.read()).iter("item")))
            line = f"OK {channel} via {base.split(".")[1]}: {items} items"
            results.append((channel, base, items))
            print(line); success=True; break
        except Exception as e:
            pass
    if not success:
        print(f"FAIL {channel}: not available on any instance")

open("rsshub_test.txt","w").write("\n".join(
    f"OK {ch} via {b}: {n}" for ch,b,n in results
))
