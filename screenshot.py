"""
Captures a screenshot of the live leaderboard Top 10 standings for
attaching to X posts.

Requires: playwright (pip install playwright && playwright install chromium)
If playwright isn't available, capture_standings_screenshot() returns
False and the caller falls back to posting without an image -- this
keeps the poster script functional even if the screenshot step ever
fails to install in CI.
"""

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

LEADERBOARD_PAGE_URL = "https://rise-underground.github.io/leaderboard.html"


def capture_standings_screenshot(out_path="leaderboard_screenshot.png", url=LEADERBOARD_PAGE_URL, timeout_ms=15000):
    """
    Navigates to the live leaderboard page, waits for standings to
    actually render (not just the empty-state message), and screenshots
    just the standings section. Returns True on success, False if it
    couldn't get real data in time or playwright isn't installed (falls
    back to no-image posting).
    """
    if not PLAYWRIGHT_AVAILABLE:
        print("playwright not installed -- skipping screenshot, will post without image.")
        return False

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 900, "height": 1000})
            page.goto(url, wait_until="networkidle", timeout=timeout_ms)

            try:
                page.wait_for_selector(".standings .row", timeout=timeout_ms)
            except Exception:
                print("Standings didn't render in time (empty leaderboard or load failure) -- skipping screenshot.")
                return False

            # Screenshot the board-head (Top 10 title) through the standings
            # list together, not the whole page, so the image is tight and
            # readable at tweet-thumbnail size.
            board_head = page.query_selector(".board-head")
            standings = page.query_selector(".standings")
            if not board_head or not standings:
                print("Couldn't locate standings elements -- skipping screenshot.")
                return False

            head_box = board_head.bounding_box()
            stand_box = standings.bounding_box()
            if not head_box or not stand_box:
                print("Couldn't compute bounding box -- skipping screenshot.")
                return False

            clip = {
                "x": min(head_box["x"], stand_box["x"]),
                "y": head_box["y"],
                "width": max(head_box["width"], stand_box["width"]),
                "height": (stand_box["y"] + stand_box["height"]) - head_box["y"],
            }
            page.screenshot(path=out_path, clip=clip)
            return True
        finally:
            browser.close()


if __name__ == "__main__":
    ok = capture_standings_screenshot()
    print(f"Screenshot {'saved' if ok else 'FAILED'}.")
