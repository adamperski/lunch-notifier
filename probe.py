"""One-off: discover SchoolCafe API endpoints used by the guest menu page."""
import re, urllib.request, urllib.parse
UA = {"User-Agent": "Mozilla/5.0", "Accept": "*/*"}
out = []
def fetch(u):
    return urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=30).read().decode("utf-8", "replace")
base = "https://www.schoolcafe.com/JEFFCOSD"
try:
    html = fetch(base)
    out.append(f"HTML {len(html)}: {html[:500]}")
    srcs = re.findall(r'src="([^"]+\.js[^"]*)"', html)
    out.append(f"scripts: {srcs}")
    for s in srcs:
        u = urllib.parse.urljoin(base + "/", s)
        try:
            js = fetch(u)
        except Exception as e:
            out.append(f"{u}: {e}"); continue
        hits = sorted(set(re.findall(r'[\'"`/]((?:api/)?[A-Za-z]*/?(?:Get|get)[A-Za-z]*(?:ServingLine|Grade|Menu|MealType|School)[A-Za-z]*)[\'"`?/]', js)))
        out.append(f"{s} ({len(js)}b): {hits}")
        for m in re.finditer(r'ServingLine', js):
            pass
        for kw in ("GetDailyMenuitemsByGrade", "ServingLines", "Grades"):
            for m in list(re.finditer(kw, js))[:3]:
                out.append(f"  ctx {kw}: {js[max(0,m.start()-250):m.end()+250]}")
except Exception as e:
    out.append(f"err {e!r}")
msg = "\n".join(out)[-60000:]
print("::notice title=probe::" + msg.replace("%", "%25").replace("\r", "").replace("\n", "%0A"))
