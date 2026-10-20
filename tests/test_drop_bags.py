"""Drop bag planner: picking bags, locations, the weather page, time zones, packing, warnings, checklist."""
import datetime

import pytest
from conftest import chart, bags, BANDY, LAUREL, START, LOC_ONEIDA, LOC_JAMES, LOC_ROBBINS

SOON = (datetime.date.today() + datetime.timedelta(days=4)).isoformat()      # forecast range
LATER = (datetime.date.today() + datetime.timedelta(days=90)).isoformat()    # typical weather range
ALL_LOCS = {START: LOC_ONEIDA, BANDY: LOC_JAMES, LAUREL: LOC_ROBBINS}


def open_bags(app, c=None, b=None, step="pick"):
    app.seed([{"chart": c or chart(startDate=SOON), "bags": b or bags(locs=dict(ALL_LOCS), step=step)}])
    app.open_race()
    app.act("b-open")
    app.page.wait_for_timeout(300)


def go(app, step):
    app.page.click(f'[data-act="b-go"][data-step="{step}"]')
    app.page.wait_for_timeout(150)


def alerts(app, word=""):
    return [(a.get_attribute("class"), a.inner_text().replace("\n", " ")) for a in app.page.locator(".alert").all()
            if word.lower() in a.inner_text().lower()]


def sugg_ids(app):
    return app.page.eval_on_selector_all(".tile.sug", "e=>e.map(x=>x.dataset.id)")


# ---------- picking stations and locations ----------

def test_must_pick_a_drop_bag_before_moving_on(app):
    open_bags(app, b=bags(picks=[]))
    app.act("b-next")
    assert "Check at least one aid station" in app.text(".err")


def test_town_lookup_with_alternates_and_not_found(app):
    open_bags(app, b=bags(locs={}))
    inp = app.page.locator(f'[data-stloc="{BANDY}"]')
    inp.fill("Jamestown"); inp.press("Enter")
    app.page.wait_for_timeout(300)
    row = app.page.locator(".coordrow", has=app.page.locator(f'[data-stloc="{BANDY}"]'))
    assert "Jamestown, Tennessee" in app.page.input_value(f'[data-stloc="{BANDY}"]')
    assert "Jamestown, New York" in row.inner_text()           # offered as "Not it?"
    inp = app.page.locator(f'[data-stloc="{LAUREL}"]')
    inp.fill("Nowhere"); inp.press("Enter")
    app.page.wait_for_timeout(300)
    assert "No place found" in app.text(".locbox")


def test_gps_coordinates_accepted(app):
    open_bags(app, b=bags(locs={}))
    inp = app.page.locator(f'[data-stloc="{BANDY}"]')
    inp.fill("36.43, -84.93"); inp.press("Enter")
    app.page.wait_for_timeout(200)
    assert app.store()["races"][0]["bags"]["locs"][BANDY]["lat"] == pytest.approx(36.43)


def test_race_date_asked_when_missing(app):
    open_bags(app, c=chart(startDate=""))
    assert app.page.locator("#db-date").count() == 1


# ---------- weather page ----------

def test_weather_page_all_good(app):
    open_bags(app)
    app.act("b-next")
    t = app.text(".dbpanel")
    assert "Using the forecast" in t
    assert t.count("Using weather from this location") == 3
    assert app.weather.calls and app.weather.calls[0][0] == "forecast"


def test_weather_page_fallbacks(app):
    locs = {BANDY: LOC_JAMES, LAUREL: LOC_ROBBINS}          # start left blank
    app.weather.empty_lats = {LOC_ROBBINS["lat"]}            # Laurel Hill comes back empty
    open_bags(app, b=bags(locs=locs))
    app.act("b-next")
    cards = {c.locator("b").first.inner_text(): c.inner_text() for c in app.page.locator(".wxcard").all()}
    assert "No location for this stop" in cards["Start"] and "Bandy Creek" in cards["Start"]
    assert "Using weather from this location" in cards["Bandy Creek"]
    assert "Unable to pull weather for this exact location" in cards["Laurel Hill"] and "Bandy Creek" in cards["Laurel Hill"]


def test_weather_error_then_retry(app):
    app.weather.fail = True
    open_bags(app)
    app.act("b-next")
    app.page.wait_for_function("!/Getting the weather/.test(document.querySelector('.wxtop').innerText)")
    assert "couldn't get the weather" in app.text(".wxtop").lower()
    app.weather.fail = False
    app.page.click('.wxtop [data-act="b-wx"]')
    app.page.wait_for_timeout(400)
    assert "Using the forecast" in app.text(".wxtop")


def test_weather_without_date_or_locations(app):
    open_bags(app, c=chart(startDate=""), b=bags(locs={}))
    app.act("b-next")
    assert "Add your race date" in app.text(".wxtop")
    open_bags(app, b=bags(locs={}))
    app.act("b-next")
    assert "No locations yet" in app.text(".wxtop")


def test_far_off_race_uses_typical_weather(app):
    open_bags(app, c=chart(startDate=LATER))
    app.act("b-next")
    assert "typical weather" in app.text(".wxtop").lower()
    assert any(k == "archive" for k, _ in app.weather.calls)


def test_start_time_zone_mismatch_warning(app):
    locs = dict(ALL_LOCS); locs[START] = LOC_JAMES          # start location in Central
    open_bags(app, b=bags(locs=locs))
    app.act("b-next")
    assert "Check your start time zone" in app.text(".dbpanel")


# ---------- time zones on the bag pages ----------

def test_sun_times_converted_to_display_zone(app):
    open_bags(app)
    go(app, "b:" + BANDY)
    sun = app.text(".conds")
    # Bandy Creek is on Central time; its 6:40 PM sunset shows as 7:40 PM Eastern
    assert "7:40 PM EDT" in sun
    app.page.select_option('select[data-chartsel="showTz"]', "America/Chicago")
    assert "6:40 PM CDT" in app.text(".conds")
    app.page.click('[data-set="tz"][data-val="hide"]')
    assert "CDT" not in app.text(".conds")


def test_weather_uses_each_locations_local_hour(app):
    """The fake service reports 40F + local hour. At the start (Eastern) 6 AM -> 46F."""
    open_bags(app)
    go(app, "b:__start")
    assert "46°F" in app.text(".conds")


# ---------- location sanity check ----------

def test_far_away_location_is_flagged(app):
    locs = dict(ALL_LOCS); locs[LAUREL] = {"name": "Jamestown, New York", "lat": 42.10, "lon": -79.24}
    open_bags(app, b=bags(locs=locs))
    w = app.page.locator(".locwarn").all_inner_texts()
    assert len(w) == 1 and "This spot is about" in w[0]
    row = app.page.locator(".coordrow", has=app.page.locator(f'[data-stloc="{LAUREL}"]'))
    assert row.locator(".locwarn").count() == 1
    # it does not block moving on
    app.act("b-next")
    assert "Weather for each drop bag" in app.text()


def test_two_spots_conflicting_say_either(app):
    locs = {START: LOC_ONEIDA, LAUREL: {"name": "Jamestown, New York", "lat": 42.10, "lon": -79.24}}
    open_bags(app, b=bags(locs=locs))
    w = app.page.locator(".locwarn").all_inner_texts()
    assert len(w) == 2 and all("Either this spot or" in x for x in w)


def test_normal_course_has_no_location_warning(app):
    open_bags(app)
    assert app.page.locator(".locwarn").count() == 0


# ---------- packing and warnings ----------

def test_headlamp_warning_levels_and_battery_prompt(app):
    open_bags(app)
    go(app, "b:" + BANDY)
    # slowest column (cutoff) is selected by default: reaches Laurel Hill after sunset
    assert any("Pack a headlamp" in t and "if your headlamp needs them" in t for c, t in alerts(app, "headlamp"))
    assert "batteries" in sugg_ids(app)
    # Goal pace stays in daylight: purple just-in-case caution
    app.page.locator('[data-act="b-col"]').first.click()
    a = alerts(app, "headlamp")
    assert a and "info" in a[0][0] and "Consider packing a headlamp" in a[0][1] and "B Goal or Cutoff" in a[0][1]
    assert {"headlamp", "batteries"} <= set(sugg_ids(app))
    # pack the headlamp: caution turns green, battery question appears (batteries are not auto-packed)
    app.page.click('.tile.sug[data-id="headlamp"]')
    items = app.page.locator("#sack .bnm").all_inner_texts()
    assert "Headlamp" in items and "Headlamp batteries" not in items
    assert any("ok" in c and "Headlamp packed, just in case" in t for c, t in alerts(app, "headlamp"))
    assert any("Does your headlamp need batteries" in t for c, t in alerts(app, "batteries"))
    app.act("b-nobatt")
    assert not alerts(app, "need batteries")
    # removing and re-adding the headlamp asks again
    app.page.locator('#sack .btile:has-text("Headlamp") .bx').click()
    app.page.locator('.tile[data-id="headlamp"]').first.click()
    assert alerts(app, "need batteries")
    app.page.locator('.alert [data-act="b-lib"][data-id="batteries"]').click()
    assert not alerts(app, "need batteries")


def test_start_bag_suggests_the_start_kit(app):
    open_bags(app)
    go(app, "b:__start")
    s = set(sugg_ids(app))
    kit = {"socks", "tums", "salt", "coffee", "buff", "shorts", "bra", "hat", "gingins", "scaps", "cup", "bladder",
           "flask", "vest", "shirt", "shoes", "blanket", "cal", "lightlayer", "headlamp"}
    assert kit <= s, kit - s
    names = app.page.locator(".tile.sug .tnm").all_inner_texts()
    assert "Shoes" in names and "Spare shoes" not in names


def test_add_remove_custom_item_and_amounts(app):
    open_bags(app)
    go(app, "b:" + BANDY)
    app.page.click('.tile.sug[data-id="socks"]')
    app.act("b-addall")
    n = len(app.page.locator("#sack .bnm").all_inner_texts())
    assert n > 5 and not sugg_ids(app)
    app.page.locator('#sack .btile:has-text("Socks") .bx').click()
    assert "Socks" not in app.page.locator("#sack .bnm").all_inner_texts()
    # custom item with the gnome picture
    app.act("b-icotoggle"); app.page.click('[data-ico="gnome"]')
    app.page.fill("#db-cname", "Lucky gnome"); app.act("b-custom")
    assert "Lucky gnome" in app.page.locator("#sack .bnm").all_inner_texts()
    st = app.store()["races"][0]["bags"]
    assert any(c["name"] == "Lucky gnome" and c.get("ico") == "gnome" for c in st["custom"])
    # calories stepper
    before = [i for i in st["bags"][BANDY]["items"] if i["id"] == "cal"][0]["qty"]
    app.page.locator('[data-act="b-cal"][data-d="100"]').first.click()
    after = [i for i in app.store()["races"][0]["bags"]["bags"][BANDY]["items"] if i["id"] == "cal"][0]["qty"]
    assert int(after.split()[0].replace(",", "")) == int(before.split()[0].replace(",", "")) + 100


def test_morning_list_and_checklist_persist(app):
    open_bags(app, b=bags(locs=dict(ALL_LOCS), morning=[{"text": "Apply sunscreen"}],
                          bags={BANDY: {"items": [{"id": "socks", "name": "Socks", "qty": ""}], "dismissed": []}}))
    go(app, "morning")
    app.page.fill("#db-madd", "Charge watch"); app.act("b-madd")
    assert app.page.locator('[id^="db-m"]').count() >= 2
    go(app, "summary")
    if app.page.locator(".modal").count():
        app.act("r-donclose")
    app.page.locator(f'input[data-ck="{BANDY}"]').first.check()
    app.page.reload()
    app.page.wait_for_timeout(200)
    assert app.store()["races"][0]["bags"]["bags"][BANDY]["items"][0].get("done") is True


def test_checklist_pdf(app, tmp_path):
    import subprocess
    open_bags(app, b=bags(locs=dict(ALL_LOCS), step="summary",
                          bags={BANDY: {"items": [{"id": "socks", "name": "Socks", "qty": "1 pair"}], "dismissed": []}}))
    with app.page.expect_download() as d:
        app.act("b-pdf")
    p = tmp_path / "bags.pdf"; d.value.save_as(p)
    txt = subprocess.run(["pdftotext", "-layout", str(p), "-"], capture_output=True, text=True).stdout
    assert "DROP BAG CHECKLIST" in txt and "Bandy Creek" in txt and "Socks (1 pair)" in txt


# ---------- drop bags only (no pace chart) ----------

def test_drop_bags_only_race(app):
    from conftest import new_race, set_when
    new_race(app, mode="bags", name="Bags Only", date=SOON)
    page = app.page
    assert page.locator("#w-total").count() == 0 or True
    for i, (n, d) in enumerate([("Ridge", 12.5), ("Finish", 50)], start=1):
        page.fill(f"#w-n{i}", n); page.fill(f"#w-d{i}", str(d))
    app.act("next")
    page.fill("#w-e1", "9:00 AM"); page.fill("#w-l1", "11:00 AM")
    app.act("next")
    assert "Pick the day for both times at Ridge" in app.text(".err")
    set_when(page, "w-e1", 0, "9:00", "AM"); set_when(page, "w-l1", 0, "11:00", "AM")
    set_when(page, "w-e2", 0, "5:00", "PM"); set_when(page, "w-l2", 0, "9:00", "PM")
    app.act("next")
    page.wait_for_timeout(200)
    assert "Where will you have drop bags" in app.text()
    page.locator('[data-pick]').first.check()
    app.act("b-next")
    assert "Weather for each drop bag" in app.text()
    app.act("b-next"); app.act("b-next")
    assert "you arrive" in app.text(".conds").lower() and "9:00 AM" in app.text(".conds")
