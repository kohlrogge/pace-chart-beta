"""End-to-end test harness for the Race Planner (index.html).

Run from the repo root:   python3 -m pytest tests -q
Options:  APP=/path/to/index.html  to test another copy of the app.

The app is served at https://app.test/ so it gets a normal web origin (its own localStorage).
Every outside service is replaced with a local stand-in, so the tests run offline and the
same way every time:
  - Open-Meteo forecast, archive and geocoding  -> Weather / GEO below
  - FormSubmit (feedback email)                 -> Feedback below
  - jsPDF, autotable, SheetJS, pdf.js from CDNs -> tests/vendor/
Any uncaught page error fails the test.
"""
import datetime
import json
import os
import pathlib
import urllib.parse

import pytest
from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).parent
APP = pathlib.Path(os.environ.get("APP", HERE.parent / "index.html"))
VENDOR = HERE / "vendor"
ORIGIN = "https://app.test/"

VENDOR_ROUTES = {
    "**/jspdf@2.5.1/**": "jspdf.umd.min.js",
    "**/jspdf-autotable@3.8.2/**": "jspdf.plugin.autotable.min.js",
    "**/xlsx/0.18.5/**": "xlsx.full.min.js",
    "**/pdf.js/3.11.174/pdf.min.js": "pdf.min.js",
    "**/pdf.js/3.11.174/pdf.worker.min.js": "pdf.worker.min.js",
}

# Places the fake geocoder knows. Two Jamestowns on purpose: a wrong match is a real-world failure.
GEO = {
    "oneida": [("Oneida, Tennessee, United States", 36.50, -84.51)],
    "jamestown": [("Jamestown, Tennessee, United States", 36.43, -84.93),
                  ("Jamestown, New York, United States", 42.10, -79.24)],
    "robbins": [("Robbins, Tennessee, United States", 36.36, -84.59)],
    "nowhere": [],
}


def tz_for(lat, lon):
    """Time zone the fake weather service reports: west of -84.7 is Central (like Jamestown, TN)."""
    if lon < -84.7:
        return "America/Chicago"
    return "America/New_York"


class Weather:
    """Stand-in for Open-Meteo. Temperatures follow the local hour so tests can check the right hour is used."""

    def __init__(self):
        self.fail = False
        self.empty_lats = set()     # locations that come back with no data
        self.calls = []             # ("forecast" | "archive", n_locations)
        self.sunrise = "07:45"
        self.sunset = "18:40"

    def temp(self, iso_hour):
        h = int(iso_hour[11:13])
        return 40 + h            # 40F at midnight local, 63F at 11 PM

    def handle(self, route):
        u = route.request.url
        if self.fail:
            return route.abort()
        q = urllib.parse.parse_qs(urllib.parse.urlparse(u).query)
        lats = [float(x) for x in q["latitude"][0].split(",")]
        lons = [float(x) for x in q["longitude"][0].split(",")]
        d0 = datetime.date.fromisoformat(q["start_date"][0])
        d1 = datetime.date.fromisoformat(q["end_date"][0])
        days = [(d0 + datetime.timedelta(n)).isoformat() for n in range((d1 - d0).days + 1)]
        times = [f"{d}T{h:02d}:00" for d in days for h in range(24)]
        kind = "archive" if "archive-api" in u else "forecast"
        self.calls.append((kind, len(lats)))
        out = []
        for la, lo in zip(lats, lons):
            empty = round(la, 2) in self.empty_lats
            hourly = {"time": times, "temperature_2m": [None if empty else self.temp(t) for t in times]}
            if kind == "forecast":
                hourly["precipitation_probability"] = [None if empty else 20 for _ in times]
            else:
                hourly["precipitation"] = [None if empty else 0.0 for _ in times]
            out.append({"timezone": tz_for(la, lo), "hourly": hourly,
                        "daily": {"time": days, "sunrise": [f"{d}T{self.sunrise}" for d in days],
                                  "sunset": [f"{d}T{self.sunset}" for d in days]}})
        body = out if len(out) > 1 else out[0]
        route.fulfill(status=200, content_type="application/json",
                      headers={"access-control-allow-origin": "*"}, body=json.dumps(body))


def geocode(route):
    q = urllib.parse.parse_qs(urllib.parse.urlparse(route.request.url).query)
    name = q.get("name", [""])[0].lower()
    key = next((k for k in GEO if name.startswith(k)), None)
    hits = GEO.get(key, [])
    results = [{"name": n.split(",")[0], "admin1": n.split(", ")[1], "country": n.split(", ")[2],
                "latitude": la, "longitude": lo} for n, la, lo in hits]
    route.fulfill(status=200, content_type="application/json",
                  headers={"access-control-allow-origin": "*"}, body=json.dumps({"results": results} if results else {}))


class Feedback:
    def __init__(self):
        self.sent = []
        self.fail = False

    def handle(self, route):
        if self.fail:
            return route.abort()
        self.sent.append((route.request.url, json.loads(route.request.post_data or "{}")))
        route.fulfill(status=200, content_type="application/json",
                      headers={"access-control-allow-origin": "*"}, body='{"success":"true"}')


@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


class App:
    """A fresh browser context with the app loaded, plus helpers."""

    def __init__(self, browser, viewport=(1200, 1000), timezone="America/New_York", mobile=False):
        opts = dict(viewport={"width": viewport[0], "height": viewport[1]}, timezone_id=timezone,
                    accept_downloads=True)
        if mobile:
            opts.update(has_touch=True, is_mobile=True, device_scale_factor=2)
        self.ctx = browser.new_context(**opts)
        self.ctx.set_default_timeout(8000)
        self.weather, self.feedback, self.errors = Weather(), Feedback(), []
        html = APP.read_text()
        self.ctx.route("**/fonts.googleapis.com/**", lambda r: r.abort())
        self.ctx.route("**/fonts.gstatic.com/**", lambda r: r.abort())
        self.ctx.route("**/api.open-meteo.com/**", self.weather.handle)
        self.ctx.route("**/archive-api.open-meteo.com/**", self.weather.handle)
        self.ctx.route("**/geocoding-api.open-meteo.com/**", geocode)
        self.ctx.route("**/formsubmit.co/**", self.feedback.handle)
        def serve(f):
            return lambda route: route.fulfill(path=str(VENDOR / f), content_type="application/javascript")
        for pat, f in VENDOR_ROUTES.items():
            self.ctx.route(pat, serve(f))
        self.ctx.route(ORIGIN + "**", lambda r: r.fulfill(status=200, content_type="text/html", body=html))
        self.page = self.ctx.new_page()
        self.page.on("pageerror", lambda e: self.errors.append(str(e)))
        self.page.goto(ORIGIN)

    # ---- set up state ----
    def seed(self, races=None, ack=True, cur=None, donate_seen=True, extra=None):
        """Replace saved data. races: list of dicts {chart, bags, mode, id}. chart 'EXAMPLE' uses the built-in example."""
        payload = {"ack": ack, "races": races or [], "cur": cur, "donateSeen": donate_seen}
        if extra:
            payload.update(extra)
        self.page.evaluate("""p=>{
            const ex=()=>{const c=JSON.parse(JSON.stringify(window.__pace.EXAMPLE));c.isExample=false;return c;};
            p.races=p.races.map((r,i)=>Object.assign({id:'r'+(i+1),created:i+1,updated:i+1,mode:'basic',bags:null},r,
              {chart: r.chart==='EXAMPLE'?ex():(r.chart&&r.chart.__example?Object.assign(ex(),r.chart,{__example:undefined}):r.chart)}));
            if(!p.cur&&p.races.length) p.cur=p.races[0].id;
            localStorage.clear(); localStorage.setItem('raceplanner.v1',JSON.stringify(p));
        }""", payload)
        self.page.reload()

    def store(self):
        return self.page.evaluate("JSON.parse(localStorage.getItem('raceplanner.v1')||'null')")

    # ---- interact ----
    def click(self, sel):
        self.page.click(sel)

    def act(self, name, **data):
        sel = f'[data-act="{name}"]' + "".join(f'[data-{k}="{v}"]' for k, v in data.items())
        self.page.locator(sel).first.click()

    def open_race(self, idx=0):
        self.page.locator('[data-act="r-open"]').nth(idx).click()

    def text(self, sel="body"):
        return self.page.inner_text(sel)

    def no_hscroll(self):
        return self.page.evaluate("document.documentElement.scrollWidth<=window.innerWidth+1")

    def close(self):
        self.ctx.close()


@pytest.fixture
def app(browser):
    a = App(browser)
    yield a
    errs = a.errors
    a.close()
    assert not errs, "page errors: " + "; ".join(errs)


@pytest.fixture
def make_app(browser):
    made = []

    def _make(**kw):
        a = App(browser, **kw)
        made.append(a)
        return a
    yield _make
    for a in made:
        errs = a.errors
        a.close()
        assert not errs, "page errors: " + "; ".join(errs)


# ---- shared race data ----
def chart(**over):
    """Example chart (built-in 100-mile course) with overrides; resolved by App.seed."""
    c = {"__example": True, "startDate": "2026-10-24", "raceTz": "America/New_York"}
    c.update(over)
    return c


BANDY, LAUREL, START = "Bandy Creek@23.60", "Laurel Hill@45.20", "Group Camp@0.00"
LOC_ONEIDA = {"name": "Oneida, Tennessee", "lat": 36.50, "lon": -84.51}
LOC_JAMES = {"name": "Jamestown, Tennessee", "lat": 36.43, "lon": -84.93}
LOC_ROBBINS = {"name": "Robbins, Tennessee", "lat": 36.36, "lon": -84.59}


def bags(picks=(BANDY, LAUREL), locs=None, step="pick", **over):
    b = {"picks": list(picks), "bags": {}, "custom": [], "morning": [], "step": step, "locs": locs or {}}
    b.update(over)
    return b


# ---- setup (wizard) helpers: step 1 race details, step 2 aid stations, step 3 targets ----
def details(app, name="Test Race", date="2026-10-24", start="6:00 AM", total="15:00", tz=None, display=None):
    p = app.page
    p.fill("#w-name", name)
    p.fill("#w-date", date)
    p.fill("#w-start", start)
    if tz:
        p.select_option("#w-tz", tz)
    if total is not None and p.locator("#w-total").count():
        p.fill("#w-total", total)
    if display:
        p.check(f'input[name="w-disp"][value="{display}"]')
    app.act("next")


def new_race(app, mode="basic", **kw):
    app.seed()
    app.act("r-new")
    app.act("r-mode", mode=mode)
    details(app, **kw)


def set_when(page, id_, day, time, ampm):
    """A time-of-day field: day index (0 = race day), 12-hour time, AM/PM."""
    page.select_option(f"#{id_}d", str(day))
    page.fill(f"#{id_}", time)
    page.select_option(f"#{id_}ap", ampm)
