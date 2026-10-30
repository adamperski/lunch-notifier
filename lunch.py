#!/usr/bin/env python3
"""Fetch today's SchoolCafe lunch menu and push it to a phone via ntfy.sh.

Config via environment variables:
  NTFY_TOPIC   (required) ntfy topic name your phone is subscribed to
  DISTRICT     SchoolCafe short name            (default JEFFCOSD)
  SCHOOL       substring of the school name     (default Foster)
  MEAL_TYPES   comma-separated meals            (default Lunch)
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
                    menu[cat] = names
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


# How each SchoolCafe category is shown; None hides it (same every day).
SECTIONS = {
    "ENTREES": "Main dish (pick one)",
    "GRAINS": "Sides",
    "VEGETABLES": "Sides",
    "FRUITS": "Fruit",
    "FRUIT-J": "Juice",
    "MILK": None,
    "CONDIMENTS": None,
}


# Per-meal overrides of SECTIONS.
MEAL_SECTIONS = {"Breakfast": {"GRAINS": "Grains & cereal"}}
MEAL_ICONS = {"Breakfast": "☀️", "Lunch": "🍽️"}


def format_menu(menu, meal=""):
    sections = {**SECTIONS, **MEAL_SECTIONS.get(meal, {})}
    groups = {}
    for cat, items in menu.items():
        label = sections.get(cat.upper(), cat.title())
        if label:
            groups.setdefault(label, []).extend(i.removesuffix(", IW") for i in items)  # IW = individually wrapped
    lines = []
    for label, items in groups.items():
        if label.startswith("Main"):
            lines += [label + ":"] + [f"   • {i}" for i in items]
        else:
            lines.append(f"{label}: {' · '.join(items)}")
    return "\n".join(lines)


def ntfy_titles(topic):
    """Titles of messages sent or scheduled on the topic in the last day (used to avoid duplicates)."""
    url = f"https://ntfy.sh/{topic}/json?poll=1&sched=1&since=24h"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "lunch-notifier"}), timeout=30) as r:
            msgs = [json.loads(line) for line in r.read().decode().splitlines() if line.strip()]
    except Exception as e:  # better a duplicate than a missed menu
        log(f"ntfy check failed: {e}")
        return set()
    titles = {m.get("title") for m in msgs if m.get("event") == "message"}
    log(f"ntfy recent titles: {sorted(t for t in titles if t)}")
    return titles


def notify(topic, title, message, at=None):
    when = f" (deliver at {at:%Y-%m-%d %H:%M %Z})" if at else ""
    if os.environ.get("DRY_RUN"):
        log(f"--- DRY RUN: {title}{when} ---\n{message}")
        return
    payload = {"topic": topic, "title": title, "message": message, "tags": ["school"],
               "click": f"https://www.schoolcafe.com/{os.environ.get('DISTRICT', 'JEFFCOSD')}"}
    if at:
        payload["delay"] = str(int(at.timestamp()))
    req = urllib.request.Request("https://ntfy.sh/", data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=30)
    log(f"Sent: {title}{when}")


def main():
    """Evening runs schedule tomorrow's menu for 6:30am; morning and manual runs send today's menu now."""
    topic = os.environ.get("NTFY_TOPIC") or sys.exit("Set NTFY_TOPIC")
    meals = [m.strip() for m in os.environ.get("MEAL_TYPES", "Lunch").split(",")]
    force = bool(os.environ.get("FORCE"))
    now = dt.datetime.now(TZ)
    send_at = None
    if os.environ.get("MENU_DATE"):
        day = dt.date.fromisoformat(os.environ["MENU_DATE"])
    elif now.hour >= 12 and not force:
        day = now.date() + dt.timedelta(days=1)
        hour, minute = map(int, os.environ.get("SEND_TIME", "06:30").split(":"))
        send_at = dt.datetime.combine(day, dt.time(hour, minute), TZ)
    else:
        day = now.date()
    if day.weekday() >= 5:
        return log(f"{day} is a weekend, skipping.")
    title = f"{day:%A}'s {meals[0].lower() if len(meals) == 1 else 'menu'} · {day:%b %-d}"
    if not force and title in ntfy_titles(topic):
        return log(f"Already sent or scheduled: {title}")
    district_id, school_id, school_name = find_school(os.environ.get("DISTRICT", "JEFFCOSD"), os.environ.get("SCHOOL", "Foster"))
    sections = []
    for meal in meals:
        menu = fetch_menu(district_id, school_id, day, meal)
        if menu:
            header = f"{MEAL_ICONS.get(meal, '🍴')} {meal.upper()}\n" if len(meals) > 1 else ""
            sections.append(header + format_menu(menu, meal))
    if not sections:
        return log(f"No menu for {day} (holiday / no school?), not notifying.")
    notify(topic, title, "\n\n".join(sections), send_at)


if __name__ == "__main__":
    try:
        main()
    except BaseException as e:
        log(f"exit: {e!r}")
        raise
    finally:
        flush_log()
