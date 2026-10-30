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
        u = urllib.parse.urljoin("https://www.schoolcafe.com/", s)
        if "pre-loader" in s or "polyfill" in s: continue
        try:
            js = fetch(u)
        except Exception as e:
            out.append(f"{u}: {e}"); continue
        for m in re.finditer(r'"\{API_URL\}([A-Za-z/]+)\?([^)]*)\)', js):
            if re.search(r"Grade|Meal|Serving|School", m.group(1)) and "Menuitems" not in m.group(1):
                out.append(f"  {m.group(1)}?{re.sub(r'encodeURIComponent', '', m.group(2))[:200]}")
except Exception as e:
    out.append(f"err {e!r}")
msg = "\n".join(out)[-60000:]
print("::notice title=probe::" + msg.replace("%", "%25").replace("\r", "").replace("\n", "%0A"))
