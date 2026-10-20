"""Drive the real app in Firefox like a person would, and check each behaviour."""
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support.ui import WebDriverWait

B = "http://127.0.0.1:8740"
results = []

def check(name, ok, detail=""):
    results.append(ok)
    print(("PASS " if ok else "FAIL ") + name + (f"  ({detail})" if detail and not ok else ""))

o = Options(); o.add_argument("-headless")
d = webdriver.Firefox(options=o)
d.set_window_size(1440, 1000)
wait = WebDriverWait(d, 10)
q = lambda css: d.find_element(By.CSS_SELECTOR, css)
qs = lambda css: d.find_elements(By.CSS_SELECTOR, css)
js = d.execute_script
is_open = lambda id_: js(f"return document.getElementById('{id_}').open")

# 1. Keyboard: the first Tab reaches the skip link, and it becomes visible.
d.get(B + "/videos?status=skipped")
ActionChains(d).send_keys(Keys.TAB).perform()
check("first Tab focuses the visible skip link", js("const a=document.activeElement; return a.classList.contains('skip-link') && a.getBoundingClientRect().top >= 0"))

# 2. One Extract button for every collection, and a sentence saying what it does.
check("one 'Extract new videos' button, no checkboxes to pick",
      q(".extract button").text.strip() == "Extract new videos" and not qs("#sidebar input[type=checkbox]"), q(".extract button").text)
check("the sidebar explains what Extract does", "writes a note" in q(".extract .hint").text)

# 4. Add-collection dialog: opens, Escape closes, backdrop closes, a bad link returns here with an error.
q("[data-dialog='add-collection']").click()
check("+ opens the Add a collection card", is_open("add-collection"))
ActionChains(d).send_keys(Keys.ESCAPE).perform()
check("Escape closes it", not is_open("add-collection"))
q("[data-dialog='add-collection']").click()
from selenium.webdriver.common.actions.action_builder import ActionBuilder
backdrop = ActionBuilder(d); backdrop.pointer_action.move_to_location(20, 20).click(); backdrop.perform()
check("a click on the backdrop closes it", not is_open("add-collection"))
q("[data-dialog='add-collection']").click()
q("#add-collection input[name=url]").send_keys("https://example.com/not-a-collection")
q("#add-collection button[type=submit]").click()
wait.until(lambda _: "/videos" in d.current_url and qs(".banner-alert"))
check("a bad link comes back to the same page with an error", "status=skipped" in d.current_url and "collection" in q(".banner-alert").text.lower(), d.current_url)
check("the message is removed from the address", "err=" not in d.current_url, d.current_url)

# 5. Collection card: opens with its values; Cancel closes.
q("[data-dialog='collection-1']").click()
check("⋯ opens the collection card with its name", is_open("collection-1") and q("#collection-1 input[name=name]").get_attribute("value") == "Material")
check("cookies and backup links are folded away", not q("#collection-1 select[name=cookies_mode]").is_displayed())
q("#collection-1 [data-close].button").click()
check("Cancel closes it", not is_open("collection-1"))

# 6. Settings card: gear opens it, the panel loads, tabs work with clicks and arrow keys.
q("[data-open-settings]").click()
wait.until(lambda _: qs("#settings [role=tab]"))
check("the gear opens the Settings card with its tabs", is_open("settings") and len(qs("#settings [role=tab]")) == 3)
check("advanced settings and the API key start folded",
      not q("#settings input[name='notes.batch_size']").is_displayed() and not q("#settings input[name=key]").is_displayed())
size = lambda: js("const r=document.getElementById('settings').getBoundingClientRect(); return [r.width, r.height, r.top]")
time.sleep(0.3)  # let the 120 ms opening animation finish
first = size()
q("#tab-usage").click()
check("the card keeps its size and place when the tab changes", size() == first, f"{first} → {size()}")
check("clicking a tab shows its panel", q("#panel-usage").is_displayed() and not q("#panel-general").is_displayed())
q("#tab-usage").send_keys(Keys.ARROW_RIGHT)
check("arrow keys move between tabs", js("return document.activeElement.id") == "tab-about" and q("#panel-about").is_displayed())
q("#settings .dialog-head [data-close]").click()
check("the close button closes the card", not is_open("settings"))

# 7. Saving settings comes back to this page with the card reopened and the result inside it.
q("[data-open-settings]").click()
wait.until(lambda _: qs("#settings .settings-form"))
q("#settings .settings-form button[type=submit]").click()
wait.until(lambda _: is_open("settings") and qs("#settings [data-settings-flash] .banner"))
check("after saving, the card reopens on the same page with 'Settings saved.'",
      "/videos" in d.current_url and "Settings saved" in q("#settings [data-settings-flash]").text, d.current_url)
check("the main page doesn't repeat the message", not qs("main .banner"))
check("the address is clean again (filters kept)", d.current_url.endswith("/videos?status=skipped"), d.current_url)
q("#settings .dialog-head [data-close]").click()

# 8. Ideas: choosing an idea selects it and shows it.
d.get(B + "/ideas")
rows = qs(".idea-row")
title = rows[2].find_element(By.CSS_SELECTOR, ".row-title").text
rows[2].click()
wait.until(lambda _: "/ideas/idea-" in d.current_url)
check("clicking an idea opens it in the reading pane", q(".reading-title").text == title, q(".reading-title").text)
check("its row is marked as selected", q(".idea-row[aria-current]").find_element(By.CSS_SELECTOR, ".row-title").text == title)

# 8b. Delete idea asks first, lists the videos it could delete, and Cancel deletes nothing.
check("no Delete button among the actions", not qs(".reading-actions [data-dialog='delete-idea']"))
q(".reading-head .menu > summary").click()
check("⋯ at the top right opens a menu with Delete idea", q(".menu-list .menu-item").is_displayed() and "Delete idea" in q(".menu-list").text)
ActionChains(d).send_keys(Keys.ESCAPE).perform()
check("Escape closes the menu", not q(".menu-list").is_displayed())
q(".reading-head .menu > summary").click()
q(".menu-list [data-dialog='delete-idea']").click()
check("Delete idea asks first (menu closed), with the videos unticked", is_open("delete-idea") and not q(".menu-list").is_displayed() and all(
    not box.is_selected() for box in qs("#delete-idea input[name=with_videos]")))
q("#delete-idea [data-close].button").click()
check("…and Cancel keeps the idea", not is_open("delete-idea") and q(".reading-title").text == title)

# 9. Filters stay while browsing ideas.
next(e for e in qs(".chip") if e.text.startswith("New")).click()
wait.until(lambda _: "status=new" in d.current_url)
qs(".idea-row")[1].click()
wait.until(lambda _: "/ideas/idea-" in d.current_url)
check("the status filter is kept when opening an idea", "status=new" in d.current_url, d.current_url)

# 10. The 'check older notes' card opens and cancels (it's offered only while some notes are unchecked).
if qs(".banner-action [data-dialog='find-ideas']"):
    q(".banner-action [data-dialog='find-ideas']").click()
    check("'Check them' opens its card, themes folded", is_open("find-ideas") and not qs("#find-ideas input[name=themes]")[0].is_displayed())
    q("#find-ideas [data-close].button").click()
else:
    check("no 'check older notes' offer when every note is checked", not qs("#find-ideas"))

# 11. Undo and quit confirmations open and cancel without doing anything.
d.get(B + "/runs/2")
q("[data-dialog='undo']").click()
check("'Undo' asks first", is_open("undo"))
q("#undo [data-close].button").click()
q("[data-dialog='quit']").click()
check("Quit asks first", is_open("quit"))
q("#quit [data-close].button").click()
check("…and Cancel leaves the app running", not is_open("quit") and "Extract · Material" in d.title, d.title)
check("a finished run shows one sentence, its log folded", q(".summary").text.startswith("Checked") and not q("[data-log]").is_displayed())

# 12. Video filters: chips only for groups that have videos, and search keeps them.
d.get(B + "/videos")
labels = [e.text.split()[0] for e in qs(".chips .chip")]
check("video chips are just All and Skipped", labels == ["All", "Skipped"], str(labels))
check("noted videos carry no status pill", not qs(".video-row .pill") or all(p.text != "NOTED" for p in qs(".video-row .pill")))
next(e for e in qs(".chip") if e.text.startswith("Skipped")).click()
wait.until(lambda _: "status=skipped" in d.current_url)
check("Skipped shows only skipped videos", bool(qs(".video-row")) and all("Skipped" in r.text for r in qs(".video-row")))
d.get(B + "/videos")
box = q("#video-search"); box.send_keys("napoleon"); box.send_keys(Keys.ENTER)
wait.until(lambda _: "q=napoleon" in d.current_url)
check("search finds the slideshow", len(qs(".video-row")) >= 1, d.current_url)

# 13. Phone: the drawer opens, traps the page, closes with Escape, and Settings opens from it.
d.set_window_size(390, 844)
d.get(B + "/ideas")
q("[data-open-sidebar]").click()
check("Menu opens the drawer", js("return 'open' in document.getElementById('sidebar').dataset") and q("#sidebar").is_displayed())
check("the page behind is inert and focus moves into the drawer", js("return document.getElementById('main').inert && document.activeElement.classList.contains('sidebar-close')"))
ActionChains(d).send_keys(Keys.ESCAPE).perform()
check("Escape closes it and returns focus to Menu", js("return !('open' in document.getElementById('sidebar').dataset) && document.activeElement.matches('[data-open-sidebar]')"))
q("[data-open-sidebar]").click()
q("#sidebar [data-open-settings]").click()
wait.until(lambda _: is_open("settings"))
check("Settings from the drawer closes the drawer first", not js("return 'open' in document.getElementById('sidebar').dataset"))
q("#settings .dialog-head [data-close]").click()
qs(".idea-row")[0].click()
wait.until(lambda _: "/ideas/idea-" in d.current_url)
check("on a phone an idea opens on its own, with a way back",
      q(".reading-pane").is_displayed() and not q(".list-pane").is_displayed() and q(".reading-pane .back-link").is_displayed())
check("no sideways scrolling on the phone", js("return document.documentElement.scrollWidth <= document.documentElement.clientWidth"))

# 14. Live progress: a real, harmless run (Update downloaders) streams into the page and the sidebar.
d.set_window_size(1440, 1000)
d.get(B + "/ideas")
q("[data-open-settings]").click()
wait.until(lambda _: qs("#tab-about"))
q("#tab-about").click()
q("#panel-about button[type=submit]").click()
wait.until(lambda _: "/runs/" in d.current_url)
run_url = d.current_url
saw_widget = bool(qs(".live"))
time.sleep(1)
lines_seen = len(qs("[data-log] li"))
wait.until(lambda _: qs(".summary") and not qs(".summary.live-line"), "run did not finish")
check("the run page opens while it's running, with the sidebar widget", saw_widget, run_url)
check("log lines arrive live", lines_seen >= 1, str(lines_seen))
check("when it ends the page refreshes with the result", "Downloaders updated" in q(".summary").text and not qs(".live"), q(".summary").text)

d.quit()
print(f"\n{sum(results)} of {len(results)} checks passed")
