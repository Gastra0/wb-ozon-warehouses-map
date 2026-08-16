import urllib.request, xml.etree.ElementTree as ET
HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
instances = [
    "https://rsshub.app",
    "https://rsshub.rssforever.com",
    "https://hub.slarker.me",
    "https://rsshub.woodland.cafe",
    "https://rsshub.ktachibana.party",
    "https://rsshub.privacyredirect.com",
]
results = []
for base in instances:
    for channel in ["astra_intel", "bazabazon", "shot_shot"]:
        url = f"{base}/telegram/channel/{channel}"
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=10) as r:
                items = len(list(ET.fromstring(r.read()).iter("item")))
            line = f"OK {base}/{channel}: {items} items"
            results.append(line); print(line); break
        except Exception as e:
            line = f"FAIL {base}/{channel}: {str(e)[:70]}"
            results.append(line); print(line)
open("rsshub_test.txt","w").write("\n".join(results))
