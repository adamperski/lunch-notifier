"""One-off: call GetServiceLine for Foster Elementary."""
import re, urllib.request
H = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
js = urllib.request.urlopen(urllib.request.Request("https://www.schoolcafe.com/main.0caeaca0860ac7ccf09a.js", headers=H), timeout=30).read().decode("utf-8", "replace")
out = ["ctx: " + js[m.start()-100:m.end()+200] for m in re.finditer(r'GetServiceLine', js)]
SID = "6069506d-496e-4da1-b375-d8dad5a0b8e6"
for q in [f"schoolid={SID}&mealtype=Lunch", f"schoolid={SID}&mealtype=Lunch&startdate=10/26/2026&enddate=11/06/2026"]:
    try:
        out.append(q + " -> " + urllib.request.urlopen(urllib.request.Request("https://webapis.schoolcafe.com/api/GetServiceLine?" + q, headers=H), timeout=30).read().decode()[:1500])
    except Exception as e:
        out.append(f"{q} -> {e}")
print("::notice title=probe::" + "\n".join(out).replace("%", "%25").replace("\n", "%0A"))
