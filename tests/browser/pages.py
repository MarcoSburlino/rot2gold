"""Screenshot every page at four widths in light and dark, and check each for layout bugs."""
import sys, pathlib
from selenium import webdriver
from selenium.webdriver.firefox.options import Options

OUT = pathlib.Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
B = "http://127.0.0.1:8740"
PAGES = {"ideas": "/ideas", "learnings": "/learnings", "idea": "/ideas/idea-write-a-five-year-plan-and-a-get-away-day", "videos": "/videos",
         "video": "/videos/7273505335577414944", "slides": "/videos/7282799479298788640", "history": "/runs", "runs": "/runs?conn=1",
         "run": "/runs/2", "preview": "/ideas/preview/3", "settings": "/settings"}
CHECKS = """
const doc = document.documentElement;
const out = {overflow: doc.scrollWidth - doc.clientWidth};
out.brokenImages = [...document.images].filter(i => i.complete && i.naturalWidth === 0 && !i.loading.includes('lazy')).map(i => i.src);
out.unnamedButtons = [...document.querySelectorAll('button, a')].filter(e => e.offsetParent !== null &&
  !(e.textContent.trim() || e.getAttribute('aria-label') || e.getAttribute('title'))).map(e => e.outerHTML.slice(0, 80));
out.wideElements = [...document.querySelectorAll('main *')].filter(e => {const r = e.getBoundingClientRect();
  return r.width > 0 && r.right > doc.clientWidth + 1 && !e.closest('.table-wrap, .log, pre, .prose table');}).slice(0, 5).map(e => e.tagName + '.' + e.className);
return out;
"""

def driver(dark):
    o = Options(); o.add_argument("-headless")
    if dark:
        o.set_preference("ui.systemUsesDarkTheme", 1)
        o.set_preference("layout.css.prefers-color-scheme.content-override", 0)
    return webdriver.Firefox(options=o)

problems = 0
for dark in (False, True):
    d = driver(dark)
    for width in (390, 768, 1024, 1440):
        d.set_window_size(width, 1000)
        for name, path in PAGES.items():
            d.get(B + path)
            r = d.execute_script(CHECKS)
            bad = {k: v for k, v in r.items() if v and not (k == "overflow" and v <= 0)}
            if bad:
                problems += 1
                print(f"{'dark' if dark else 'light'} {width} {name}: {bad}")
            if width in (390, 1440) or name in ("ideas", "video"):
                d.save_screenshot(str(OUT / f"{name}-{width}-{'dark' if dark else 'light'}.png"))
    d.quit()
print("pages with problems:", problems)
