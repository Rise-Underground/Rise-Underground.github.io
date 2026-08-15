"""
Infinity Rising — Monthly Catalog Discovery
==============================================

What this does
---------------
Reads the site's own filter checkboxes (Course on Aero Trails, Vehicle
on Calido Valley Raceway) and writes out the current list of every
course and vehicle the site knows about, as CSVs:

    catalog_courses.csv   — name, courseId
    catalog_vehicles.csv  — canonical_name, model_key

This is the automated version of the manual DOM-inspection we did by
hand to find the courseId_N / vehicleModel_X mappings. Run this
monthly (it's slow — uses a real browser — so don't run it constantly)
and if the game adds a new track or vehicle, it shows up here
automatically instead of requiring another round of manual digging.

fast_scraper.py should eventually read these CSVs instead of using
the hardcoded AERO_TRAILS_COURSES / CALIDO_VEHICLES /
VEHICLE_MODEL_TO_CANONICAL tables, so new content flows through
without any code changes.

Run
---
    pip install playwright
    playwright install chromium
    python discover_catalog.py
"""

import csv
import re
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

AERO_TRAILS_URL = "https://infinityrising.com/leaderboards/aero-trails"
CALIDO_URL = "https://infinityrising.com/leaderboards/calido-valley-raceway"


def load_page(page, url):
    print(f"Loading {url}...")
    page.goto(url, wait_until="domcontentloaded")
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except PWTimeout:
        pass


def discover_checkbox_filter(page, filter_heading_text, id_prefix):
    """Finds every checkbox <label for="{id_prefix}_X"> under the filter
    section titled filter_heading_text, and returns a list of
    (display_name, key) pairs, where key is whatever follows id_prefix_
    in the checkbox's id attribute."""
    results = []
    try:
        # All labels on the page whose "for" attribute starts with id_prefix
        labels = page.locator(f'label[for^="{id_prefix}_"]')
        count = labels.count()
        for i in range(count):
            label = labels.nth(i)
            for_attr = label.get_attribute("for")
            key = for_attr[len(id_prefix) + 1:]  # strip "id_prefix_"
            text = label.inner_text().strip()
            results.append((text, key))
    except Exception as e:
        print(f"  !! error reading '{filter_heading_text}' filter: {e}")
    return results


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # --- Courses ---
        load_page(page, AERO_TRAILS_URL)
        print("Reading Course filter...")
        courses = discover_checkbox_filter(page, "Course", "courseId")
        print(f"  -> found {len(courses)} courses")

        # --- Vehicles ---
        load_page(page, CALIDO_URL)
        print("Reading Vehicle filter...")
        vehicles = discover_checkbox_filter(page, "Vehicle", "vehicleModel")
        print(f"  -> found {len(vehicles)} vehicles")

        browser.close()

    with open("catalog_courses.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["name", "courseId"])
        for name, course_id in courses:
            writer.writerow([name, course_id])
    print("Written to catalog_courses.csv")

    with open("catalog_vehicles.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["canonical_name", "model_key"])
        for name, model_key in vehicles:
            writer.writerow([name, model_key])
    print("Written to catalog_vehicles.csv")

    print(f"\nTotal: {len(courses)} courses x {len(vehicles)} vehicles "
          f"= {len(courses) * len(vehicles)} Calido boards, "
          f"plus {len(courses)} Aero Trails boards, plus Holocache.")


if __name__ == "__main__":
    main()
