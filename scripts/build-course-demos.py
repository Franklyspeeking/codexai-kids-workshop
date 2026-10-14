"""Validate the hand-authored classroom demos before release.

The public demos are now authoritative. Do not copy old sibling course-products
onto them: those products use the previous desktop-first interface.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "codexai-site" / "dist"
COURSES = ("chore-bank", "weekend-planner", "screen-agreement", "family-trip",
           "habit-board", "sorting-challenge", "reading-exchange", "story-director")
INLINE_PRODUCTS = {"chore-bank": "家务积分银行", "reading-exchange": "我的阅读书房"}

def main():
    course_list = (SITE / "courses" / "index.html").read_text(encoding="utf-8")
    for slug in COURSES:
        folder = SITE / "demos" / slug
        html = (folder / "index.html").read_text(encoding="utf-8")
        for ref in re.findall(r'(?:src|href)="([^"#]+)"', html):
            if ":" in ref:
                continue
            path = SITE / ref.lstrip("/") if ref.startswith("/") else folder / ref
            if not path.exists():
                raise FileNotFoundError(path)
        if slug in INLINE_PRODUCTS:
            if INLINE_PRODUCTS[slug] not in html or "<script>" not in html or "studio-app.js" in html:
                raise ValueError(f"{slug}: expected the new self-contained product")
        elif "studio-app.js" not in html or "product-boot.js" in html:
            raise ValueError(f"{slug}: expected the mobile studio entrypoint")
        if slug != "story-director" and f'href="/demos/{slug}/"' not in course_list:
            raise ValueError(f"{slug}: course list does not link to its demo")
        print(f"OK /demos/{slug}/")
    for filename in ("index.html", "app.js", "studio-money.js", "sw.js"):
        if not (SITE / "money" / filename).is_file():
            raise FileNotFoundError(filename)
    print("OK /money/ — nine course tools ready")

if __name__ == "__main__":
    main()
