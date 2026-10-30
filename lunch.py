#!/usr/bin/env python3
"""Fetch today's SchoolCafe lunch menu and push it to a phone via ntfy.sh.

Config via environment variables:
  NTFY_TOPIC   (required) ntfy topic name your phone is subscribed to
  DISTRICT     SchoolCafe short name            (default JEFFCOSD)
  SCHOOL       substring of the school name     (default Foster)
  MEAL_TYPE    Lunch / Breakfast                (default Lunch)
  GRADE        grade code used by SchoolCafe    (default: auto)
  SERVING_LINE serving line name                (default: auto)
  MENU_DATE    YYYY-MM-DD to override "today"   (default: today, America/Denver)
  DRY_RUN=1    print instead of sending
"""
import datetime as dt
import json
import os
import sys
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

API = "https://webapis.schoolcafe.com/api"
TZ = ZoneInfo(os.environ.get("TZ_NAME", "America/Denver"))
LOG = []


def log(msg):
    print(msg, file=sys.stderr)
    LOG.append(msg)


def flush_log():
    """Attach the debug log to the GitHub Actions run as an annotation."""
    if os.environ.get("GITHUB_ACTIONS") and LOG:
        text = "\n".join(LOG)[-60000:]
        print("::notice title=lunch debug::" + text.replace("%", "%25").replace("\r", "").replace("\n", "%0A"))


def get(path, **params):
    url = f"{API}/{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read().decode()
    log(f"GET {url} -> {r.status} {body[:400]}")
    return json.loads(body) if body.strip() else None


def try_get(path, **params):
    try:
        return get(path, **params)
    except Exception as e:  # endpoint missing / changed
        log(f"  failed: {path}: {e}")
        return None


def first(d, *keys):
    for k in keys:
        if isinstance(d, dict) and d.get(k) not in (None, ""):
            return d[k]
    return None


def find_school(district, name):
    isd = get("GetISDByShortName", shortname=district)
    isd = isd[0] if isinstance(isd, list) else isd
    isd_id = first(isd, "ISDId", "IsdId", "Id")
    schools = get("GetSchoolsList", districtId=isd_id) or []
    for s in schools:
        if name.lower() in (first(s, "SchoolName", "Name") or "").lower():
            return isd_id, first(s, "SchoolId", "Id"), first(s, "SchoolName", "Name")
    sys.exit(f"No school matching {name!r}. Options: {[first(s, 'SchoolName', 'Name') for s in schools]}")


def candidate_lines(school_id, meal, day):
    if os.environ.get("SERVING_LINE"):
        return [os.environ["SERVING_LINE"]]
    d = day.strftime("%m/%d/%Y")
    data = try_get("GetServiceLine", schoolid=school_id, mealtype=meal, startdate=d, enddate=d) or []
    found = [first(x, "ServingLineDescription") for x in data if isinstance(x, dict)]
    return [x for x in found if x] or ["Main"]


def candidate_grades(district_id):
    if os.environ.get("GRADE"):
        return [os.environ["GRADE"]]
    grades = try_get("GetGradesByDistrictId", isdId=district_id) or []
    # Elementary menus are normally identical across grades; try a few typical ones.
    return [g for g in ("03", "01", "KG", "05") if g in grades] or grades[:3] or ["03"]


def parse_menu(data):
    """SchoolCafe returns {"CATEGORY": [{"MenuItemDescription": ...}, ...], ...}."""
    menu = {}
    if isinstance(data, dict):
        for cat, items in data.items():
            if isinstance(items, list):
                names = [first(i, "MenuItemDescription", "ItemName", "Description") for i in items]
                names = [n.strip() for n in names if n]
                if names:
                    menu[cat.title()] = names
    return menu


def fetch_menu(district_id, school_id, day, meal):
    for line in candidate_lines(school_id, meal, day):
        for grade in candidate_grades(district_id):
            data = try_get("CalendarView/GetDailyMenuitemsByGrade", SchoolId=school_id, ServingDate=day.strftime("%m/%d/%Y"),
                           ServingLine=line, MealType=meal, Grade=grade, PersonId="null")
            menu = parse_menu(data)
            if menu:
                return menu
    return {}


def notify(topic, title, message):
    if os.environ.get("DRY_RUN"):
        print(f"--- {title} ---\n{message}")
        return
    req = urllib.request.Request(f"https://ntfy.sh/{topic}", data=message.encode(),
                                 headers={"Title": title, "Tags": "fork_and_knife"})
    urllib.request.urlopen(req, timeout=30)


def main():
    topic = os.environ.get("NTFY_TOPIC") or (os.environ.get("DRY_RUN") and "dry") or sys.exit("Set NTFY_TOPIC")
    meal = os.environ.get("MEAL_TYPE", "Lunch")
    day = dt.date.fromisoformat(os.environ["MENU_DATE"]) if os.environ.get("MENU_DATE") else dt.datetime.now(TZ).date()
    if day.weekday() >= 5:
        return print("Weekend, skipping.")
    district_id, school_id, school_name = find_school(os.environ.get("DISTRICT", "JEFFCOSD"), os.environ.get("SCHOOL", "Foster"))
    menu = fetch_menu(district_id, school_id, day, meal)
    if not menu:
        return log(f"No menu for {day} (holiday / no school?), not notifying.")
    body = "\n".join(f"{cat}: {', '.join(items)}" for cat, items in menu.items())
    notify(topic, f"{meal} - {day:%a %b %-d}", body)
    print(body)


if __name__ == "__main__":
    try:
        main()
    except BaseException as e:
        log(f"exit: {e!r}")
        raise
    finally:
        flush_log()
