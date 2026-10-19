# Browser checks

Real-Firefox checks of the running app (not part of `pytest`; they need `vn ui` running on 127.0.0.1:8740 and Selenium).

- `pages.py <out-dir>` — every page at 390, 768, 1024 and 1440 px in light and dark: sideways scrolling, broken images, unnamed buttons, elements wider than the page; saves screenshots. (Image links in the video gallery are reported as unnamed, but their alt text names them: a known false alarm.)
- `interactions.py` — clicks through the app like a person: Extract label, dialogs (open, Escape, backdrop, cancel), Settings card and tabs, saving settings, idea selection and filters, video filters and search, the phone drawer, and a live run (it starts a real "Update downloaders", which is harmless). Nothing destructive: no delete, quit, undo or extract.

Setup, outside the project venv:

```
uv venv --python 3.14 /tmp/selenium-env && uv pip install --python /tmp/selenium-env/bin/python selenium pillow
/tmp/selenium-env/bin/python tests/browser/interactions.py
```
