"""Setting up a race, the pace chart math (even and advanced), display controls, and exports."""
import re

import pytest
from conftest import chart, details, new_race, set_when


def fill_stations(page, rows):
    """rows: list of (name, dist, cutoff) after the start; the last row is the finish."""
    # the blank draft has Start, one empty station, Finish
    while page.locator('[id^="w-n"]').count() < len(rows) + 1:
        page.click('[data-act="addrow"]')
    for i, row in enumerate(rows, start=1):
        name, dist = row[0], row[1]
        page.fill(f"#w-n{i}", name)
        page.fill(f"#w-d{i}", str(dist))
        if len(row) > 2 and row[2] and page.locator(f"#w-c{i}").count():
            page.fill(f"#w-c{i}", row[2])


def build_basic(app, mode="basic", rows=None, name="Test 50", start="6:00 AM", date="2026-10-24", goals=("11:00", "13:00"), total="15:00"):
    new_race(app, mode=mode, name=name, start=start, date=date, total=total)
    fill_stations(app.page, rows or [("Ridge", 12.5), ("Creek", 30, "9:00"), ("Finish", 50)])
    app.act("next")
    for i, g in enumerate(goals):
        app.page.fill(f"#w-pt{i}", g)
    app.act("next")


def rows(app):
    return [r.split("\t") for r in app.page.locator(".tablebox tbody tr").all_inner_texts()]


def test_build_basic_chart(app):
    build_basic(app)
    r = rows(app)
    assert [x[0].split("\n")[0] for x in r] == ["Start", "Ridge", "Creek", "Finish"]
    assert r[-1][-3:] == ["11:00", "13:00", "15:00"]
    # even pace: Ridge at 12.5/50 of 11:00 = 2:45
    assert r[1][3] == "2:45"
    s = app.store()
    assert s["races"][0]["mode"] == "basic" and s["races"][0]["chart"]["raceTz"]


@pytest.mark.parametrize("rows_,goals,total,msg", [
    ([("Ridge", ""), ("Finish", 50)], ("11:00", "13:00"), "15:00", "needs a distance"),
    ([("Ridge", 30), ("Creek", 20), ("Finish", 50)], ("11:00", "13:00"), "15:00", "farther than"),
])
def test_setup_catches_bad_aid_stations(app, rows_, goals, total, msg):
    new_race(app)
    fill_stations(app.page, rows_)
    app.act("next")
    assert msg in app.text(".err")


def test_setup_catches_bad_goals(app):
    build_basic(app, goals=("16:00", "13:00"), total="15:00")
    assert "faster than the overall cutoff" in app.text(".err")


def test_example_chart_math_holds_up(app):
    """On the built-in 100 miler: every plan finishes on target, times only go forward, and every posted
    cutoff is met with at least the margin."""
    app.seed([{"chart": chart()}])
    app.open_race()
    res = app.page.evaluate("""()=>{const s=window.__pace.store, r=s.races[0];
        const R=window.__pace.compute(r.chart); return {rows:R.rows.map(x=>({cut:x.cut,hard:x.hard,first:x.first})),
        plans:R.plans.map(p=>({target:p.target,times:p.times,misses:p.misses.length})),margin:R.margin};}""")
    for p in res["plans"]:
        t = p["times"]
        assert abs(t[-1] - p["target"]) < 0.01
        assert all(b >= a for a, b in zip(t, t[1:]))
        assert p["misses"] == 0
        for row, ti in zip(res["rows"], t):
            if row["hard"] and not row["first"]:
                assert ti <= row["cut"] - res["margin"] + 0.5


def test_advanced_chart_matches_the_formula(app):
    """10 mi with 2,500 ft up / 500 down, then 10 mi with 500 up / 2,500 down, 6:00 goal.
    Effort miles: climb 1.9 mi per 1,000 ft; descent -0.5 / 0 / +0.5 per 1,000 ft."""
    c = {"isExample": False, "adv": True, "descent": "runnable", "name": "Hills", "unit": "mi", "entryUnit": "mi",
         "display": "elapsed", "startDate": "", "startTime": 360, "cutoffFormat": "elapsed", "raceTz": "America/New_York",
         "labels": {"cut": "Cutoff"}, "plans": [{"label": "Goal", "time": 360}], "total": 600, "margin": 15,
         "stations": [{"name": "Start", "dist": 0, "cutoff": None},
                      {"name": "Hilltop", "dist": 10, "cutoff": None, "gain": 2500, "loss": 500},
                      {"name": "Finish", "dist": 20, "cutoff": None, "gain": 500, "loss": 2500}]}
    app.seed([{"chart": c, "mode": "advanced"}])
    app.open_race()
    app.act("r-chart")
    for setting, expect in [("runnable", "3:36"), ("mixed", "3:27"), ("steep", "3:19")]:
        app.page.click(f'[data-set="descent"][data-val="{setting}"]')
        assert rows(app)[1][4] == expect, setting
        assert rows(app)[1][3] == "+2,500 / -500"


def test_advanced_setup_and_paste(app):
    new_race(app, mode="advanced", name="Ridge 50", total="15:00")
    app.page.locator("details.paste").first.click()
    app.page.fill("#w-paste", "Start\t0\nRidge\t12.5\t\t3,200\t800\nCreek\t30\t9:00\t1000\t2900\nFinish\t50\t15:00\t1500\t1500")
    app.act("paste")
    assert app.page.input_value("#w-up1") == "3,200"
    assert app.page.input_value("#w-c3") == "15:00"      # finish row shows the overall cutoff
    app.act("next")
    app.page.fill("#w-pt0", "11:00"); app.page.fill("#w-pt1", "13:00")
    app.act("next")
    r = rows(app)
    assert r[1][3] == "+3,200 / -800"
    assert r[1][4] == "3:22"           # matches the hand-worked effort split
    assert app.store()["races"][0]["mode"] == "advanced"


def test_advanced_requires_some_elevation(app):
    new_race(app, mode="advanced")
    fill_stations(app.page, [("Ridge", 12.5), ("Finish", 50)])
    app.act("next")
    assert "Add the climb and descent" in app.text(".err")


def test_display_controls(app):
    app.seed([{"chart": chart(name="Ctl")}])
    app.open_race(); app.act("r-chart")
    first_mi = rows(app)[1][1]
    app.page.click('[data-set="unit"][data-val="km"]')
    assert float(rows(app)[1][1]) == pytest.approx(float(first_mi) * 1.609, abs=0.11)
    app.page.click('[data-set="display"][data-val="clock"]')
    assert re.search(r"(AM|PM)", rows(app)[1][3])
    # time zone menu shows up only for time of day
    assert app.page.locator('select[data-chartsel="showTz"]').count() == 1
    app.page.click('[data-set="display"][data-val="elapsed"]')
    assert app.page.locator('select[data-chartsel="showTz"]').count() == 0
    app.page.click('[data-set="showSeg"][data-val="hide"]')
    assert "Segment" not in app.text(".tablebox thead")
    app.page.click('[data-set="margin"][data-val="30"]')
    assert app.store()["races"][0]["chart"]["margin"] == 30


def test_time_zone_menu_converts_chart_times(app):
    app.seed([{"chart": chart(name="TZ", display="clock")}])
    app.open_race(); app.act("r-chart")
    start = lambda: rows(app)[0][3]
    assert start().endswith("6:00 AM")
    app.page.select_option('select[data-chartsel="showTz"]', "America/Chicago")
    assert start().endswith("5:00 AM")
    app.page.select_option('select[data-chartsel="showTz"]', "Pacific/Honolulu")
    assert start().endswith("12:00 AM")


def test_edit_chart_keeps_display_settings(app):
    app.seed([{"chart": chart(name="Keep", display="clock", showTz="America/Chicago", tempUnit="C")}])
    app.open_race(); app.act("edit")
    app.act("next"); app.act("next"); app.act("next")
    c = app.store()["races"][0]["chart"]
    assert c["showTz"] == "America/Chicago" and c["tempUnit"] == "C"


def test_pace_chart_pdf_and_excel(app, tmp_path):
    import subprocess, openpyxl
    app.seed([{"chart": chart(name="Export Test", display="clock")}])
    app.open_race(); app.act("r-chart")
    with app.page.expect_download() as d:
        app.act("pdf")
    pdf = tmp_path / "c.pdf"; d.value.save_as(pdf)
    txt = subprocess.run(["pdftotext", str(pdf), "-"], capture_output=True, text=True).stdout
    assert "Export Test" in txt and "Group Camp" in txt
    with app.page.expect_download() as d:
        app.act("xlsx")
    x = tmp_path / "c.xlsx"; d.value.save_as(x)
    assert d.value.suggested_filename.endswith(".xlsx")
    ws = openpyxl.load_workbook(x).active
    vals = [[c.value for c in r] for r in ws.iter_rows()]
    assert vals[0][0] == "Export Test"
    head = vals[3]
    assert head[0] == "Aid station" and "Cutoff type" in head
    assert "Excel files from the app" in app.text(".banner")


def test_copy_table(app):
    app.ctx.grant_permissions(["clipboard-read", "clipboard-write"], origin="https://app.test")
    app.seed([{"chart": chart(name="Copy")}])
    app.open_race(); app.act("r-chart")
    app.act("copy")
    app.page.wait_for_function("document.querySelector('[data-act=copy]').textContent==='Copied' || !!document.getElementById('copyfall')")
    if app.page.locator("#copyfall").count():
        txt = app.page.input_value("#copyfall")
    else:
        txt = app.page.evaluate("navigator.clipboard.readText()")
    lines = txt.splitlines()
    assert lines[0].startswith("Aid station\t") and "Group Camp" in lines[1]


# ---------- race details first; time-of-day cutoffs with a day, time and AM/PM ----------

def test_race_details_come_first_and_date_is_required(app):
    app.seed()
    app.act("r-new"); app.act("r-mode", mode="basic")
    assert "Race details" in app.text(".steps .on")
    p = app.page
    p.fill("#w-name", "No Date"); p.fill("#w-start", "6:00 AM"); p.fill("#w-total", "30:00")
    app.act("next")
    assert "Pick the race date" in app.text(".err")
    p.fill("#w-date", "2026-10-24"); p.fill("#w-total", "")
    app.act("next")
    assert "overall cutoff" in app.text(".err")


def test_overall_cutoff_prefills_finish_and_edits_flow_back(app):
    new_race(app, total="30:00")
    p = app.page
    assert p.input_value("#w-c2") == "30:00"
    p.fill("#w-c2", "32:00")
    app.act("back")
    assert p.input_value("#w-total") == "32:00"


def clock_setup(app, cut_time, cut_ampm=None, day="0", total="15:00"):
    new_race(app, total=total)
    p = app.page
    p.check('input[name="w-cf"][value="clock"]')
    p.fill("#w-n1", "Charit"); p.fill("#w-d1", "19.2")
    p.fill("#w-c1", cut_time)
    if cut_ampm:
        p.select_option("#w-c1ap", cut_ampm)
    if day is not None:
        p.select_option("#w-c1d", day)
    p.fill("#w-n2", "Finish"); p.fill("#w-d2", "50")
    app.act("next")


def test_time_of_day_cutoff_needs_am_or_pm(app):
    clock_setup(app, "2:45")
    assert "Pick AM or PM" in app.text(".err")


def test_time_of_day_cutoff_rejects_24_hour_time(app):
    clock_setup(app, "14:45")
    assert "12-hour time" in app.text(".err")


def test_time_of_day_cutoff_needs_a_day(app):
    clock_setup(app, "2:45", "PM", day=None)
    assert "Pick the day for the cutoff at Charit" in app.text(".err")


def test_day_menu_lists_the_race_days(app):
    new_race(app, date="2026-10-24", total="34:00")
    app.page.check('input[name="w-cf"][value="clock"]')
    opts = app.page.eval_on_selector("#w-c1d", "e=>[...e.options].map(o=>o.text)")
    assert opts[:3] == ["Day", "Sat, Oct 24", "Sun, Oct 25"]
    # the finish row shows the overall cutoff as a day and time: 6:00 AM + 34 h = Sun 4:00 PM
    p = app.page
    assert (p.input_value("#w-c2d"), p.input_value("#w-c2"), p.input_value("#w-c2ap")) == ("1", "4:00", "PM")


def test_time_of_day_cutoff_with_day_and_menu(app):
    clock_setup(app, "2:45", "PM", day="0")
    p = app.page
    assert "Target times" in app.text(".steps .on")
    p.fill("#w-pt0", "11:00"); p.fill("#w-pt1", "13:00")
    app.act("next")
    assert app.store()["races"][0]["chart"]["stations"][1]["cutoff"] == 8 * 60 + 45
    # editing shows it back split into day, box and menu
    app.act("edit"); app.act("next")
    assert (p.input_value("#w-c1d"), p.input_value("#w-c1"), p.input_value("#w-c1ap")) == ("0", "2:45", "PM")


def test_next_day_cutoff(app):
    clock_setup(app, "5:00", "AM", day="1", total="30:00")
    app.page.fill("#w-pt0", "24:00"); app.page.fill("#w-pt1", "26:00")
    app.act("next")
    assert app.store()["races"][0]["chart"]["stations"][1]["cutoff"] == 23 * 60     # Sat 6 AM -> Sun 5 AM


def test_finish_cutoff_typed_as_day_and_time_sets_overall(app):
    new_race(app, total="30:00")
    p = app.page
    p.check('input[name="w-cf"][value="clock"]')
    p.fill("#w-n1", "Ridge"); p.fill("#w-d1", "10"); p.fill("#w-n2", "Finish"); p.fill("#w-d2", "20")
    set_when(p, "w-c2", 1, "2:00", "PM")
    app.act("next"); app.act("back"); app.act("back")
    assert p.input_value("#w-total") == "32:00"


def test_start_time_needs_am_or_pm(app):
    app.seed()
    app.act("r-new"); app.act("r-mode", mode="basic")
    p = app.page
    p.fill("#w-name", "Start AMPM"); p.fill("#w-date", "2026-10-24"); p.fill("#w-start", "6:00"); p.fill("#w-total", "30:00")
    p.select_option("#w-startap", "")
    app.act("next")
    assert "Pick AM or PM for the start time" in app.text(".err")


def test_imported_times_split_into_box_and_menu(app, tmp_path):
    p_ = tmp_path / "c.csv"
    p_.write_text("Aid Station,Mile,Cutoff\nStart,0,\nCharit,19.2,6:00 PM\nGrand Gap,28.4,21:30\nLaurel,45.2,6:00\nFinish,50,\n")
    new_race(app, total="34:00")
    app.page.locator("details.paste").nth(1).click()
    app.page.set_input_files("#w-file", str(p_))
    app.page.wait_for_selector(".impmap")
    app.act("impapply")
    p = app.page
    assert (p.input_value("#w-c1"), p.input_value("#w-c1ap"), p.input_value("#w-c1d")) == ("6:00", "PM", "")
    assert (p.input_value("#w-c2"), p.input_value("#w-c2ap")) == ("9:30", "PM")    # 21:30 converted
    assert (p.input_value("#w-c3"), p.input_value("#w-c3ap")) == ("6:00", "")      # ambiguous: runner must pick
    app.act("next")
    assert "Pick the day for the cutoff at Charit" in app.text(".err")


def test_typed_am_pm_moves_into_the_menu(app):
    app.seed()
    app.act("r-new"); app.act("r-mode", mode="basic")
    p = app.page
    p.fill("#w-start", "6:30 pm")
    p.dispatch_event("#w-start", "change")
    assert (p.input_value("#w-start"), p.input_value("#w-startap")) == ("6:30", "PM")


# ---------- time boxes keep exactly what was typed ----------

@pytest.mark.parametrize("typed", ["200", "34", "6.45", "645", "28:30"])
def test_race_time_box_keeps_what_was_typed(app, typed):
    """No automatic colons: 200 stays 200 (200 hours), it is never turned into 2:00."""
    app.seed()
    app.act("r-new"); app.act("r-mode", mode="basic")
    p = app.page
    p.fill("#w-total", typed); p.dispatch_event("#w-total", "change")
    assert p.input_value("#w-total") == typed


def test_bare_number_is_hours(app):
    app.seed()
    app.act("r-new"); app.act("r-mode", mode="basic")
    p = app.page
    p.fill("#w-name", "Long"); p.fill("#w-date", "2026-10-24"); p.fill("#w-start", "6:00"); p.select_option("#w-startap", "AM")
    p.fill("#w-total", "200")
    app.act("next")
    p.fill("#w-n1", "Ridge"); p.fill("#w-d1", "100")
    p.fill("#w-n2", "Finish"); p.fill("#w-d2", "240")
    app.act("next")
    p.fill("#w-pt0", "80"); p.fill("#w-pt1", "190:30")
    app.act("next")
    c = app.store()["races"][0]["chart"]
    assert c["total"] == 200 * 60
    assert [x["time"] for x in c["plans"]] == [80 * 60, 190 * 60 + 30]


def test_period_is_not_turned_into_a_colon(make_app):
    app = make_app(viewport=(390, 844), mobile=True)
    app.seed()
    app.act("r-new"); app.act("r-mode", mode="basic")
    p = app.page
    p.click("#w-total"); p.keyboard.type("34.5")
    assert p.input_value("#w-total") == "34.5"


def test_time_boxes_open_the_full_keyboard(app):
    """Phones show their full keyboard (with the colon) for time boxes, with autocorrect off; distances keep the number pad."""
    app.seed()
    app.act("r-new"); app.act("r-mode", mode="basic")
    p = app.page
    boxes = lambda: p.eval_on_selector_all(".timein", "e=>e.map(x=>[x.getAttribute('inputmode'),x.getAttribute('autocorrect'),x.getAttribute('autocapitalize')])")
    assert boxes() and all(b == ["text", "off", "off"] for b in boxes())      # start time, overall cutoff
    p.fill("#w-name", "Kb"); p.fill("#w-date", "2026-10-24"); p.fill("#w-start", "6:00 AM"); p.fill("#w-total", "30:00")
    app.act("next")
    assert all(b == ["text", "off", "off"] for b in boxes())                  # race-time cutoffs and the finish
    p.check('input[name="w-cf"][value="clock"]')
    assert all(b == ["text", "off", "off"] for b in boxes())                  # time-of-day cutoffs
    assert p.get_attribute("#w-d1", "inputmode") == "decimal"
