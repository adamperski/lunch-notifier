"""One-off: inspect SchoolCafe endpoints for Foster Elementary."""
import urllib.request
A = "https://webapis.schoolcafe.com/api/"
SID = "6069506d-496e-4da1-b375-d8dad5a0b8e6"
out = []
for path in [f"GetMealType?schoolid={SID}&startdate=10/26/2026&enddate=11/06/2026",
             "GetGradesByDistrictId?isdId=1448",
             f"CalendarView/GetDailyMenuitems?SchoolId={SID}&ServingDate=10/28/2026&ServingLine=&MealType=Lunch"]:
    try:
        r = urllib.request.urlopen(urllib.request.Request(A + path, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"}), timeout=30)
        out.append(f"{path} -> {r.read().decode()[:2500]}")
    except Exception as e:
        out.append(f"{path} -> {e}")
print("::notice title=probe::" + "\n".join(out).replace("%", "%25").replace("\n", "%0A"))
