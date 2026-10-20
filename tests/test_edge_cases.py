"""Harder cases: editing a chart after packing, odd text in names, clock-time cutoffs, metric climbs."""
import datetime

from conftest import chart, bags, BANDY, LAUREL, START, LOC_ONEIDA, LOC_JAMES, LOC_ROBBINS

SOON = (datetime.date.today() + datetime.timedelta(days=4)).isoformat()


def test_renaming_a_station_keeps_its_packed_bag(app):
    packed = {BANDY: {"items": [{"id": "socks", "name": "Socks", "qty": ""}], "dismissed": []}}
    app.seed([{"chart": chart(startDate=SOON), "bags": bags(locs={BANDY: LOC_JAMES}, bags=packed)}])
    app.open_race(); app.act("edit")
    i = [app.page.input_value(f"#w-n{k}") for k in range(app.page.locator('[id^="w-n"]').count())].index("Bandy Creek")
    app.page.fill(f"#w-n{i}", "Bandy Creek Trailhead")
    app.act("next"); app.act("next"); app.act("next")
    b = app.store()["races"][0]["bags"]
    key = next(k for k in b["picks"] if k.startswith("Bandy Creek"))
    assert key.startswith("Bandy Creek Trailhead@"), b["picks"]
    assert b["bags"][key]["items"][0]["name"] == "Socks"
    assert b["locs"].get(key), "location should follow the renamed station"


def test_moving_a_station_distance_keeps_its_packed_bag(app):
    packed = {BANDY: {"items": [{"id": "socks", "name": "Socks", "qty": ""}], "dismissed": []}}
    app.seed([{"chart": chart(startDate=SOON), "bags": bags(bags=packed)}])
    app.open_race(); app.act("edit")
    i = [app.page.input_value(f"#w-n{k}") for k in range(app.page.locator('[id^="w-n"]').count())].index("Bandy Creek")
    app.page.fill(f"#w-d{i}", "23.9")
    app.act("next"); app.act("next"); app.act("next")
    b = app.store()["races"][0]["bags"]
    assert "Bandy Creek@23.90" in b["picks"], b["picks"]
    assert b["bags"]["Bandy Creek@23.90"]["items"][0]["name"] == "Socks"


def test_html_in_names_is_shown_as_text(app):
    evil = '<img src=x onerror="window.__pwned=1">Ridge'
    app.seed([{"chart": chart(name='<b>Race</b>', startDate=SOON), "bags": bags(locs={})}])
    app.page.evaluate("""n=>{const s=JSON.parse(localStorage.getItem('raceplanner.v1')); s.races[0].chart.stations[1].name=n;
        s.races[0].bags.custom=[{id:'c1',name:n,cat:'other'}]; localStorage.setItem('raceplanner.v1',JSON.stringify(s));}""", evil)
    app.page.reload()
    assert "<b>Race</b>" in app.text(".racegrid")
    app.open_race(); app.act("r-chart")
    app.act("b-open"); app.page.wait_for_timeout(200)
    app.act("b-next"); app.act("b-next")
    assert not app.page.evaluate("window.__pwned||0")


def test_time_of_day_cutoffs_across_midnight(app):
    app.seed()
    app.act("r-new"); app.act("r-mode", mode="basic")
    p = app.page
    p.check('input[name="w-cf"][value="clock"]')
    rows = [("Night AS", 40, "11:30 PM"), ("Dawn AS", 70, "8:00 AM"), ("Finish", 100)]
    while p.locator('[id^="w-n"]').count() < 4:
        p.click('[data-act="addrow"]')
    for i, r in enumerate(rows, start=1):
        p.fill(f"#w-n{i}", r[0]); p.fill(f"#w-d{i}", str(r[1]))
        if len(r) > 2: p.fill(f"#w-c{i}", r[2])
    app.act("next")
    p.fill("#w-name", "Midnight"); p.fill("#w-start", "6:00 AM"); p.fill("#w-date", SOON)
    app.act("next")
    p.fill("#w-pt0", "26:00"); p.fill("#w-pt1", "28:00"); p.fill("#w-total", "32:00")
    app.act("next")
    st = app.store()["races"][0]["chart"]["stations"]
    assert st[1]["cutoff"] == 17 * 60 + 30          # 11:30 PM same day
    assert st[2]["cutoff"] == 26 * 60               # 8:00 AM next day


def test_time_of_day_cutoff_on_daylight_saving_weekend(app):
    """Start Sat Oct 31 2026 at 6:00 AM Eastern; a posted 8:00 AM Sunday cutoff is 27 real hours later (clocks fall back)."""
    app.seed()
    app.act("r-new"); app.act("r-mode", mode="basic")
    p = app.page
    p.check('input[name="w-cf"][value="clock"]')
    while p.locator('[id^="w-n"]').count() < 4:
        p.click('[data-act="addrow"]')
    p.fill("#w-n1", "Night AS"); p.fill("#w-d1", "40"); p.fill("#w-c1", "11:30 PM")
    p.fill("#w-n2", "Dawn AS"); p.fill("#w-d2", "70"); p.fill("#w-c2", "8:00 AM")
    p.fill("#w-n3", "Finish"); p.fill("#w-d3", "100")
    app.act("next")
    p.fill("#w-name", "DST"); p.fill("#w-start", "6:00 AM"); p.fill("#w-date", "2026-10-31")
    p.select_option("#w-tz", "America/New_York")
    app.act("next")
    p.fill("#w-pt0", "26:00"); p.fill("#w-pt1", "28:00"); p.fill("#w-total", "32:00")
    app.act("next")
    st = app.store()["races"][0]["chart"]["stations"]
    assert st[1]["cutoff"] == 17 * 60 + 30          # Sat 11:30 PM, before the change
    assert st[2]["cutoff"] == 27 * 60               # Sun 8:00 AM is 27 real hours after the start
    # the chart shows it back as 8:00 AM, and editing round-trips it unchanged
    p.click('[data-set="display"][data-val="clock"]')
    row = p.locator(".tablebox tbody tr").nth(2).inner_text().split("\t")
    assert row[-1].replace("\n", " ").endswith("8:00 AM")
    app.act("edit")
    assert (p.input_value("#w-c2"), p.input_value("#w-c2ap")) == ("8:00", "AM")
    app.act("next"); app.act("next"); app.act("next")
    assert app.store()["races"][0]["chart"]["stations"][2]["cutoff"] == 27 * 60


def test_metric_advanced_chart_shows_meters(app):
    c = {"isExample": False, "adv": True, "descent": "mixed", "name": "Metric", "unit": "km", "entryUnit": "km",
         "display": "elapsed", "startDate": "", "startTime": 360, "cutoffFormat": "elapsed", "raceTz": "Europe/Zurich",
         "labels": {"cut": "Cutoff"}, "plans": [{"label": "Goal", "time": 600}], "total": 900, "margin": 15,
         "stations": [{"name": "Start", "dist": 0, "cutoff": None},
                      {"name": "Col", "dist": 12.43, "cutoff": None, "gain": 3280.84, "loss": 328.084},
                      {"name": "Finish", "dist": 31.07, "cutoff": None, "gain": 328.084, "loss": 3280.84}]}
    app.seed([{"chart": c, "mode": "advanced"}])
    app.open_race(); app.act("r-chart")
    assert "(m)" in app.text(".tablebox thead")
    assert "+1,000 / -100" in app.text(".tablebox tbody")


def test_excel_time_of_day_without_race_date(app, tmp_path):
    import openpyxl
    app.seed([{"chart": chart(name="NoDate", startDate="", display="clock")}])
    app.open_race(); app.act("r-chart")
    with app.page.expect_download() as d:
        app.act("xlsx")
    x = tmp_path / "n.xlsx"; d.value.save_as(x)
    ws = openpyxl.load_workbook(x).active
    first = [c.value for c in list(ws.iter_rows())[4]]
    assert "6:00 AM" in str(first[3])


def test_back_keeps_what_was_typed_and_rows_reorder(app):
    app.seed()
    app.act("r-new"); app.act("r-mode", mode="basic")
    p = app.page
    while p.locator('[id^="w-n"]').count() < 4:
        p.click('[data-act="addrow"]')
    for i, (n, d) in enumerate([("B Station", 20), ("A Station", 10), ("Finish", 30)], start=1):
        p.fill(f"#w-n{i}", n); p.fill(f"#w-d{i}", str(d))
    p.click('[data-act="rowdown"][data-i="1"]')           # move B below A
    assert [p.input_value(f"#w-n{i}") for i in (1, 2)] == ["A Station", "B Station"]
    app.act("next"); p.fill("#w-name", "Keep Me"); app.act("back")
    assert p.input_value("#w-n1") == "A Station"
    app.act("next")
    assert p.input_value("#w-name") == "Keep Me"


def test_five_goal_columns_and_margin_check(app):
    app.seed()
    app.act("r-new"); app.act("r-mode", mode="basic")
    p = app.page
    p.fill("#w-n1", "Cut AS"); p.fill("#w-d1", "10"); p.fill("#w-c1", "1:00")
    p.fill("#w-n2", "Finish"); p.fill("#w-d2", "30")
    app.act("next"); p.fill("#w-name", "Goals"); p.fill("#w-start", "6:00 AM"); app.act("next")
    while p.locator('[data-act="addplan"]').count():
        p.click('[data-act="addplan"]')
    assert p.locator('[id^="w-pt"]').count() == 5
    for i, t in enumerate(["4:00", "4:30", "5:00", "5:30", "5:45"]):
        p.fill(f"#w-pt{i}", t)
    p.fill("#w-total", "6:00"); p.fill("#w-margin", "90")
    app.act("next")
    assert "longer than the time to the first cutoff" in app.text(".err")
    p.fill("#w-margin", "15"); app.act("next")
    assert p.locator(".tablebox thead th").count() == 3 + 5 + 1


def test_changing_race_date_refetches_weather(app):
    import datetime
    from conftest import LOC_ONEIDA, LOC_JAMES, LOC_ROBBINS, START, BANDY, LAUREL
    soon = (datetime.date.today() + datetime.timedelta(days=4)).isoformat()
    app.seed([{"chart": chart(startDate=soon), "bags": bags(locs={START: LOC_ONEIDA, BANDY: LOC_JAMES, LAUREL: LOC_ROBBINS})}])
    app.open_race(); app.act("b-open"); app.page.wait_for_timeout(300)
    n = len(app.weather.calls)
    app.act("b-exit"); app.act("edit"); app.act("next")
    later = (datetime.date.today() + datetime.timedelta(days=6)).isoformat()
    app.page.fill("#w-date", later); app.act("next"); app.act("next")
    app.act("b-open"); app.page.wait_for_timeout(300)
    assert len(app.weather.calls) > n


def test_deleting_the_open_race(app):
    app.seed([{"chart": chart(name="Keep")}, {"chart": chart(name="Gone")}], cur="r2")
    app.page.locator('.racegrid > *', has_text="Gone").locator('[data-act="r-del"]').click()
    app.page.locator('[data-act="r-delyes"]').click()
    app.page.locator('.racegrid > *', has_text="Keep").locator('[data-act="r-open"]').click()
    assert "Keep" in app.text("h1")
    app.act("b-open")
    assert "Where will you have drop bags" in app.text()
