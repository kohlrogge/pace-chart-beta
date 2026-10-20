# Race Planner tests

End-to-end tests that click through the app in a real browser (Chromium) the way a runner would.

## Run them

```
pip install pytest playwright openpyxl reportlab
python3 -m playwright install chromium
python3 -m pytest tests -q
```

To test a different copy of the app: `APP=/path/to/index.html python3 -m pytest tests -q`

## What's covered

- **Start and races**: fine print, My Races, opening, switching and deleting races, carrying over old saved charts
- **Pace chart**: setup steps and their error messages, even-pace math (targets, cutoff margins), advanced climb/descent math, display controls, time zone menu, editing, PDF, Excel, copy table
- **Drop bags**: picking bags, town lookup, GPS, weather page (good, fallback, failed, no date, typical weather), time zone conversions, the location sanity check, headlamp and battery warnings, start kit, custom items, calories, checklist, checklist PDF, drop-bags-only races
- **More**: feedback and support popup, importing CSV, Excel and PDF charts, phone layouts and touch dragging, kilometer races, a 117-mile course with 40 aid stations, daylight saving weekends
- **Edge cases**: renaming or re-measuring a station after packing, odd characters in names, time-of-day cutoffs past midnight and across a clock change, metric climbs

## How it works

Every outside service is faked so the tests run offline and the same way every time
(weather, town lookup, feedback email, and the PDF/Excel libraries in `tests/vendor/`).
The fake weather reports 40°F plus the local hour, so a test can tell the right hour and time zone were used.
Any JavaScript error on the page fails the test.

## Not covered here

Safari, Firefox and real phones (see the device checklist), the real weather and feedback services,
and opening exports in Excel, Numbers or Google Sheets.
