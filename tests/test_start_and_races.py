"""First run, fine print, My Races, multiple races, deleting, and moving older saved data forward."""
from conftest import chart, bags


def test_first_visit_shows_fine_print_then_empty_home(app):
    t = app.text(".legal")
    assert "merely a tool" in t and "beta testing" in t and "womens100milerproject@gmail.com" in t
    assert app.page.locator('.legal a[href^="mailto:womens100milerproject@gmail.com"]').count() == 1
    app.act("r-ack")
    assert "No races yet" in app.text()
    # acknowledgment is remembered
    app.page.reload()
    assert app.page.locator(".legal").count() == 0


def test_fine_print_reachable_from_home(app):
    app.seed()
    app.act("r-legal")
    assert "The fine print" in app.text()


def test_two_races_open_switch_and_delete(app):
    app.seed([{"chart": chart(name="Race A")}, {"chart": chart(name="Race B", startDate="2026-11-14")}])
    names = app.page.locator(".racegrid").inner_text()
    assert "Race A" in names and "Race B" in names
    # open B, check race home shows B
    app.page.locator('.racegrid > *', has_text="Race B").locator('[data-act="r-open"]').click()
    assert "Race B" in app.text("h1")
    app.act("r-home")
    # delete A with confirmation
    app.page.locator('.racegrid > *', has_text="Race A").locator('[data-act="r-del"]').click()
    app.act("r-delno")
    assert "Race A" in app.text(".racegrid")
    app.page.locator('.racegrid > *', has_text="Race A").locator('[data-act="r-del"]').click()
    app.page.locator('[data-act="r-delyes"]').click()
    assert "Race A" not in app.text(".racegrid")
    assert len(app.store()["races"]) == 1


def test_version1_saved_chart_is_migrated(app):
    # Only the version 1 key exists (a member who used the old pace chart).
    app.page.evaluate("""()=>{localStorage.clear();const c=JSON.parse(JSON.stringify(window.__pace.EXAMPLE));
        c.isExample=false;c.name='My V1 Chart';localStorage.setItem('pacechart.v1',JSON.stringify(c));}""")
    app.page.reload()
    app.act("r-ack")
    assert "My V1 Chart" in app.text(".racegrid")


def test_saved_races_handed_over_from_old_address(app):
    import base64, json
    app.seed()
    data = {"rp": {"races": [{"id": "x1", "created": 1, "updated": 1, "mode": "basic",
                               "chart": app.page.evaluate("(()=>{const c=JSON.parse(JSON.stringify(window.__pace.EXAMPLE));c.isExample=false;c.name='Carried Race';return c})()"),
                               "bags": None}]}}
    b = base64.urlsafe_b64encode(json.dumps(data).encode()).decode().rstrip("=")
    app.page.goto("https://app.test/#carry=" + b)
    app.page.reload()      # arriving from another address is a full page load
    assert "Carried Race" in app.text(".banner")
    assert "#carry" not in app.page.url        # link cleaned up
    app.act("r-carryyes")
    assert "Carried Race" in app.text(".racegrid")


def test_race_home_steps(app):
    app.seed([{"chart": chart(name="Home Test")}])
    app.open_race()
    t = app.text()
    assert "Race Home" in t and "Pace chart" in t and "Drop bags" in t and "Packing checklist" in t
    # checklist is disabled until there are bags
    assert app.page.locator('[data-act="r-check"]').is_disabled()
