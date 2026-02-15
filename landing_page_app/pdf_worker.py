from pathlib import Path
from playwright.sync_api import sync_playwright
import sys

html_path = Path(sys.argv[1])
pdf_path = Path(sys.argv[2])

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto(html_path.resolve().as_uri(), wait_until="networkidle")
    page.pdf(
        path=str(pdf_path),
        format="A4",
        print_background=True,
        margin={
            "top": "0mm",
            "bottom": "0mm",
            "left": "0mm",
            "right": "0mm",
        },
    )
    browser.close()
