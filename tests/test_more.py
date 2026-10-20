"""Feedback and support popup, importing race charts, phones, kilometers, long courses, and daylight saving."""
import datetime

import pytest
from conftest import chart, bags, BANDY, LAUREL, START, LOC_ONEIDA, LOC_JAMES, LOC_ROBBINS

SOON = (datetime.date.today() + datetime.timedelta(days=4)).isoformat()
ALL_LOCS = {START: LOC_ONEIDA, BANDY: LOC_JAMES, LAUREL: LOC_ROBBINS}


# ---------- enjoy / feedback / support popup ----------

def open_checklist(app, donate_seen=False):
    app.seed([{"chart": chart(startDate=SOON), "bags": bags(locs=dict(ALL_LOCS), step="summary")}], donate_seen=donate_seen)
    app.open_race()
    app.act("b-open")
    app.page.wait_for_timeout(200)


def test_popup_yes_feedback_then_support(app):
    open_checklist(app)
    assert "Are you enjoying the Race Planner?" in app.text(".modal")
    app.act("r-like", v="yes")
    app.page.fill("#fb-text", "Love it!")
    app.page.press("#fb-text", "Enter")
    app.page.wait_for_timeout(300)
    url, body = app.feedback.sent[0]
    assert url.endswith("/ajax/womens100milerproject@gmail.com")
    assert body["_subject"] == "Race Planner Feedback" and body["Feedback"] == "Love it!" and body["Enjoying the app"] == "Yes"
    t = app.text(".modal")
    assert "glad you're enjoying" in t and "like the one you just planned" in t
    assert "isn't a registered nonprofit" in t and "Support us on Venmo" in t
    assert "donation" not in t.lower()
    # it only pops up once
    app.act("r-donclose")
    app.page.reload(); app.page.wait_for_timeout(200)
    assert app.page.locator(".modal").count() == 0


def test_popup_no_and_skip(app):
    open_checklist(app)
    app.act("r-like", v="no")
    assert "What could we do better" in app.text(".modal")
    app.act("r-fbskip")
    assert "Thank you" in app.text(".modal") and not app.feedback.sent


def test_popup_send_failure_offers_email(app):
    app.feedback.fail = True
    open_checklist(app)
    app.act("r-like", v="no")
    app.page.fill("#fb-text", "Broken thing")
    app.act("r-fbsend")
    app.page.wait_for_timeout(300)
    assert "couldn't send" in app.text(".modal")
    assert app.page.locator('.modal a[href^="mailto:womens100milerproject@gmail.com"]').count() == 1
    assert app.page.input_value("#fb-text") == "Broken thing"        # nothing typed is lost


def test_support_link_goes_straight_to_support(app):
    open_checklist(app, donate_seen=True)
    assert app.page.locator(".modal").count() == 0
    app.act("r-donate")
    assert "Support us on Venmo" in app.text(".modal")
    app.page.keyboard.press("Escape")
    assert app.page.locator(".modal").count() == 0


# ---------- importing a race's aid station chart ----------

def start_import(app, path):
    app.seed()
    app.act("r-new"); app.act("r-mode", mode="basic")
    app.page.locator("details.paste").nth(1).click()
    app.page.set_input_files("#w-file", str(path))
    app.page.wait_for_selector(".impmap, .wiz .err", timeout=15000)


def test_import_csv_with_climb_and_descent(app, tmp_path):
    p = tmp_path / "chart.csv"
    p.write_text('Aid Station,Mile,Elev Gain,Elev Loss,Cutoff,Lat,Lon\nStart,0,,,,36.50,-84.51\nRidge,12.5,"3,200",800,,36.43,-84.93\n'
                 'Creek,30,1000,2900,9:00,36.36,-84.59\nFinish,50,1500,1500,15:00,36.50,-84.51\n')
    start_import(app, p)
    assert "4 aid stations found" in app.text(".impmap") and "climb and descent" in app.text(".impmap")
    app.act("impapply")
    assert app.page.input_value("#w-up1") == "3,200"          # switched to climbs and descents on its own
    app.act("next"); app.page.fill("#w-name", "Imported"); app.page.fill("#w-start", "6:00 AM"); app.act("next")
    assert app.page.input_value("#w-total") == "15:00"        # finish cutoff became the overall cutoff


def test_import_excel(app, tmp_path):
    import openpyxl
    wb = openpyxl.Workbook(); ws = wb.active
    ws.append(["Race chart"]); ws.append([])
    ws.append(["Station", "Distance (mi)", "Cutoff"])
    for r in [("Start", 0, None), ("Pickett", 6.8, None), ("Charit", 19.2, "6:00"), ("Finish", 31, "10:00")]:
        ws.append(list(r))
    p = tmp_path / "chart.xlsx"; wb.save(p)
    start_import(app, p)
    app.act("impapply")
    assert app.page.input_value("#w-n2") == "Charit" and app.page.input_value("#w-d2") == "19.2"


def test_import_pdf(app, tmp_path):
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    p = tmp_path / "chart.pdf"
    c = canvas.Canvas(str(p), pagesize=letter)
    y = 700
    for row in [("Aid Station", "Mile", "Cutoff"), ("Start", "0", ""), ("Pickett", "6.8", ""), ("Charit", "19.2", "6:00"), ("Finish", "31", "10:00")]:
        for x, cell in zip((72, 260, 360), row):
            c.drawString(x, y, cell)
        y -= 20
    c.save()
    start_import(app, p)
    assert "4 aid stations found" in app.text(".impmap") or "5 aid stations found" in app.text(".impmap")
    app.act("impapply")
    names = [app.page.input_value(f"#w-n{i}") for i in range(app.page.locator('[id^="w-n"]').count())]
    assert "Charit" in names


def test_import_unreadable_file(app, tmp_path):
    p = tmp_path / "photo.png"; p.write_bytes(b"\x89PNG\r\n")
    start_import(app, p)
    assert "isn't supported" in app.text(".wiz")


# ---------- phones ----------

def test_phone_layouts_have_no_sideways_scroll(make_app):
    app = make_app(viewport=(390, 844), mobile=True)
    app.seed([{"chart": chart(startDate=SOON, display="clock"), "bags": bags(locs=dict(ALL_LOCS))}])
    screens = []
    app.open_race(); screens.append(("race home", app.no_hscroll()))
    app.act("r-chart"); screens.append(("pace chart", app.no_hscroll()))
    app.act("b-open"); app.page.wait_for_timeout(300); screens.append(("drop bags", app.no_hscroll()))
    for _ in range(3):
        app.act("b-next"); app.page.wait_for_timeout(150)
        screens.append((app.page.locator(".dbsteps .on").inner_text(), app.no_hscroll()))
    app.act("b-exit"); app.act("edit"); app.page.click('[data-act="wadv"][data-v="1"]')
    screens.append(("setup with climbs", app.no_hscroll()))
    w = app.page.locator("#w-n1").bounding_box()["width"]
    bad = [n for n, ok in screens if not ok]
    assert not bad, bad
    assert w >= 120, "station name box too narrow on a phone: %d px" % w


def test_phone_long_press_drags_item_into_bag(make_app):
    app = make_app(viewport=(390, 844), mobile=True)
    app.seed([{"chart": chart(startDate=SOON), "bags": bags(locs=dict(ALL_LOCS), step="b:" + BANDY)}])
    app.open_race(); app.act("b-open"); app.page.wait_for_timeout(300)
    tile = app.page.locator('.tile.sug[data-id="socks"]')
    tile.scroll_into_view_if_needed()
    tb = tile.bounding_box()
    sack = app.page.locator("#sack"); sack.scroll_into_view_if_needed()
    # Simulate a touch: press, hold past the long-press delay, move onto the bag, lift.
    tb = tile.bounding_box(); sb = sack.bounding_box()
    sx, sy = tb["x"] + tb["width"] / 2, tb["y"] + tb["height"] / 2
    ex, ey = sb["x"] + sb["width"] / 2, sb["y"] + sb["height"] / 2
    app.page.evaluate("""([sx,sy,ex,ey])=>new Promise(res=>{
        const el=document.elementFromPoint(sx,sy);
        const ev=(t,x,y,target)=>(target||document.elementFromPoint(x,y)||document).dispatchEvent(new PointerEvent(t,{bubbles:true,clientX:x,clientY:y,pointerId:7,pointerType:'touch',isPrimary:true,button:0}));
        ev('pointerdown',sx,sy,el);
        setTimeout(()=>{ ev('pointermove',(sx+ex)/2,(sy+ey)/2,el); ev('pointermove',ex,ey,el); ev('pointerup',ex,ey,el); res(); },350);
    })""", [sx, sy, ex, ey])
    app.page.wait_for_timeout(200)
    assert "Socks" in app.page.locator("#sack .bnm").all_inner_texts()


def test_quick_swipe_on_phone_does_not_add(make_app):
    app = make_app(viewport=(390, 844), mobile=True)
    app.seed([{"chart": chart(startDate=SOON), "bags": bags(locs=dict(ALL_LOCS), step="b:" + BANDY)}])
    app.open_race(); app.act("b-open"); app.page.wait_for_timeout(300)
    tile = app.page.locator('.tile.sug[data-id="socks"]'); tile.scroll_into_view_if_needed()
    tb = tile.bounding_box(); x, y = tb["x"] + 20, tb["y"] + 20
    app.page.evaluate("""([x,y])=>{const el=document.elementFromPoint(x,y);
        const ev=(t,yy)=>el.dispatchEvent(new PointerEvent(t,{bubbles:true,clientX:x,clientY:yy,pointerId:8,pointerType:'touch',isPrimary:true}));
        ev('pointerdown',y); ev('pointermove',y-60); ev('pointercancel',y-60);}""", [x, y])
    app.page.wait_for_timeout(400)
    assert "Socks" not in app.page.locator("#sack .bnm").all_inner_texts()


# ---------- kilometers, long courses, daylight saving ----------

def test_kilometer_race_drop_bags(app):
    app.seed([{"chart": chart(startDate=SOON, unit="km", entryUnit="km"), "bags": bags(locs=dict(ALL_LOCS))}])
    app.open_race(); app.act("b-open"); app.page.wait_for_timeout(300)
    assert " km" in app.text(".dbpicks") and " mi" not in app.text(".dbpicks")
    app.act("b-next"); app.act("b-next")
    assert app.page.locator(".conds").count() == 1


def test_long_course_with_many_aid_stations(app):
    st = [{"name": "Start", "dist": 0, "cutoff": None}] + \
         [{"name": f"AS{i}", "dist": round(i * 117 / 40, 1), "cutoff": (i * 48 * 60 // 40 if i % 10 == 0 else None)} for i in range(1, 40)] + \
         [{"name": "Finish", "dist": 117, "cutoff": None}]
    c = {"isExample": False, "name": "117 Miler", "unit": "mi", "entryUnit": "mi", "display": "clock", "startDate": SOON,
         "startTime": 360, "cutoffFormat": "elapsed", "raceTz": "America/New_York", "labels": {"cut": "Cutoff"},
         "plans": [{"label": "Goal", "time": 36 * 60}, {"label": "B Goal", "time": 42 * 60}], "total": 48 * 60, "margin": 30, "stations": st}
    app.seed([{"chart": c, "bags": bags(picks=["AS10@29.20", "AS20@58.50", "AS30@87.80"], locs={})}])
    app.open_race(); app.act("r-chart")
    assert app.page.locator(".tablebox tbody tr").count() == 41
    app.act("b-open"); app.page.wait_for_timeout(200)
    for _ in range(7):
        app.act("b-next"); app.page.wait_for_timeout(100)
    assert app.page.locator(".conds, .sumgrid, .mlist").count() >= 1


def test_race_across_daylight_saving_change(app):
    """Starts Sat Oct 31 2026, 6:00 AM Eastern. Clocks fall back at 2 AM Sunday, so 24 hours of racing later it's 5:00 AM."""
    st = [{"name": "Start", "dist": 0, "cutoff": None}, {"name": "Mid", "dist": 50, "cutoff": None}, {"name": "Finish", "dist": 100, "cutoff": None}]
    c = {"isExample": False, "name": "DST 100", "unit": "mi", "entryUnit": "mi", "display": "clock", "startDate": "2026-10-31",
         "startTime": 360, "cutoffFormat": "elapsed", "raceTz": "America/New_York", "labels": {"cut": "Cutoff"},
         "plans": [{"label": "Goal", "time": 24 * 60}], "total": 30 * 60, "margin": 15, "stations": st}
    app.seed([{"chart": c}])
    app.open_race(); app.act("r-chart")
    finish = app.page.locator(".tablebox tbody tr").last.inner_text().split("\t")
    assert finish[3].replace("\n", " ").endswith("5:00 AM") and "Sun" in finish[3]
