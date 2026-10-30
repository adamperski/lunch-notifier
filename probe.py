"""One-off: find serving-line endpoint in SchoolCafe's site code."""
import re, urllib.request
js = urllib.request.urlopen(urllib.request.Request("https://www.schoolcafe.com/main.0caeaca0860ac7ccf09a.js", headers={"User-Agent": "Mozilla/5.0"}), timeout=30).read().decode("utf-8", "replace")
eps = sorted(set(re.findall(r'\{API_URL\}([A-Za-z/]+)', js)))
out = ["endpoints: " + ", ".join(e for e in eps if re.search(r"Serv|Line|Calendar|Menu", e))]
for m in list(re.finditer(r'ServingLine', js))[:12]:
    out.append("ctx: " + js[max(0, m.start()-150):m.end()+150])
print("::notice title=probe::" + "\n".join(out).replace("%", "%25").replace("\n", "%0A"))
