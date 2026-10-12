"""Zrzut demo/report.html do screenshots/dzien-zalogi.png (Playwright, Chromium)."""
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1280, "height": 900})
    pg.goto((ROOT / "demo" / "report.html").as_uri())
    (ROOT / "screenshots").mkdir(exist_ok=True)
    pg.screenshot(path=str(ROOT / "screenshots" / "dzien-zalogi.png"), full_page=True)
    b.close()
print("ok")
