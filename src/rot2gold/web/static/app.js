// Rot2Gold: small page behaviours, no framework.
// Every page works without this file (plain links and forms); it adds dialogs, the phone
// drawer, the Settings card and live run updates.

(() => {
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];


  /* ── Dialogs ────────────────────────────────────────────────────────── */
  // [data-dialog="id"] opens <dialog id="id">; [data-close] closes its dialog; Escape is built in.

  function openDialog(id) {
    const dialog = document.getElementById(id);
    if (!dialog || dialog.open) return dialog;
    closeSidebar(false);
    dialog.showModal();
    return dialog;
  }

  // Close on a click on the backdrop, but only when the press also started there:
  // selecting text in a field and releasing outside must not throw the form away.
  let pressedOnBackdrop = false;
  document.addEventListener('pointerdown', event => {
    pressedOnBackdrop = event.target instanceof HTMLDialogElement;
  });

  document.addEventListener('click', event => {
    const opener = event.target.closest('[data-dialog]');
    if (opener) {
      event.preventDefault();
      openDialog(opener.dataset.dialog);
      return;
    }
    const closer = event.target.closest('[data-close]');
    if (closer) {
      closer.closest('dialog')?.close();
      return;
    }
    if (event.target instanceof HTMLDialogElement && pressedOnBackdrop) {
      event.target.close();
    }
  });


  /* ── ⋯ menus ────────────────────────────────────────────────────────── */
  // A <details data-menu> closes when you pick an item, click elsewhere or press Escape.

  document.addEventListener('click', event => {
    $$('details[data-menu][open]').forEach(menu => {
      if (!menu.contains(event.target) || event.target.closest('.menu-item')) menu.open = false;
    });
  });
  document.addEventListener('keydown', event => {
    const menu = event.key === 'Escape' && $('details[data-menu][open]');
    if (menu) {
      menu.open = false;
      $('summary', menu).focus();
    }
  });


  /* ── Phone drawer ───────────────────────────────────────────────────── */

  const sidebar = $('#sidebar');
  const scrim = $('.scrim');
  const menuButton = $('[data-open-sidebar]');
  const main = $('#main');

  function sidebarIsDrawer() {
    return !matchMedia('(min-width: 768px)').matches;
  }

  function openSidebar() {
    sidebar.dataset.open = '';
    scrim.hidden = false;
    menuButton.setAttribute('aria-expanded', 'true');
    document.body.dataset.drawer = '';
    main.inert = true;  // keyboard focus stays in the drawer while it's open
    $('.sidebar-close', sidebar).focus();
  }

  function closeSidebar(returnFocus = true) {
    if (!sidebar || !('open' in sidebar.dataset)) return;
    delete sidebar.dataset.open;
    scrim.hidden = true;
    menuButton.setAttribute('aria-expanded', 'false');
    delete document.body.dataset.drawer;
    main.inert = false;
    if (returnFocus && sidebarIsDrawer()) menuButton.focus();
  }

  menuButton?.addEventListener('click', openSidebar);
  $$('[data-close-sidebar]').forEach(element => element.addEventListener('click', () => closeSidebar()));
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && sidebar && 'open' in sidebar.dataset && !$('dialog[open]')) closeSidebar();
  });
  matchMedia('(min-width: 768px)').addEventListener('change', () => closeSidebar(false));


  /* ── Settings card ──────────────────────────────────────────────────── */

  const settingsDialog = $('#settings');

  function setupTabs(root, initial) {
    const tabs = $$('[role="tab"]', root);
    if (!tabs.length) return;
    const select = (tab, focus = false) => {
      tabs.forEach(item => {
        const selected = item === tab;
        item.setAttribute('aria-selected', String(selected));
        item.tabIndex = selected ? 0 : -1;
        $(`#${item.getAttribute('aria-controls')}`, root).hidden = !selected;
      });
      if (focus) tab.focus();
    };
    tabs.forEach((tab, index) => {
      tab.addEventListener('click', () => select(tab));
      tab.addEventListener('keydown', event => {
        const step = { ArrowRight: 1, ArrowLeft: -1 }[event.key];
        if (step) {
          event.preventDefault();
          select(tabs[(index + step + tabs.length) % tabs.length], true);
        } else if (event.key === 'Home' || event.key === 'End') {
          event.preventDefault();
          select(event.key === 'Home' ? tabs[0] : tabs[tabs.length - 1], true);
        }
      });
    });
    select(tabs.find(tab => tab.dataset.tab === initial) || tabs[0]);
  }

  // The result of a Settings form (msg/err in the address) shows inside the card, once.
  function showSettingsResult(root) {
    const slot = $('[data-settings-flash]', root);
    const { msg, err } = settingsDialog.dataset;
    if (!slot || !(msg || err)) return;
    const banner = document.createElement('p');
    banner.className = err ? 'banner banner-alert' : 'banner';
    banner.setAttribute('role', err ? 'alert' : 'status');
    banner.textContent = err || msg;
    slot.replaceChildren(banner);
    settingsDialog.dataset.msg = '';
    settingsDialog.dataset.err = '';
  }

  async function openSettings(tab) {
    if (!settingsDialog) return;
    closeSidebar(false);
    if (!settingsDialog.open) settingsDialog.showModal();
    const body = $('[data-settings-body]', settingsDialog);
    try {
      const response = await fetch('/settings/panel');
      if (!response.ok) throw new Error(`Settings could not be loaded (error ${response.status}).`);
      body.innerHTML = await response.text();  // server-rendered and escaped by the same app
      setupTabs(body, tab);
      showSettingsResult(body);
    } catch (error) {
      const message = document.createElement('p');
      message.className = 'banner banner-alert';
      message.textContent = `${error.message} `;
      const link = document.createElement('a');
      link.href = '/settings';
      link.textContent = 'Open the Settings page instead';
      message.append(link);
      body.replaceChildren(message);
    }
  }

  $$('[data-open-settings]').forEach(button => button.addEventListener('click', () => openSettings()));

  const page = new URL(location.href);
  const settingsTab = page.searchParams.get('settings');
  const settingsPage = $('[data-settings-page]');
  if (settingsPage) {
    setupTabs(settingsPage, settingsTab);
    showSettingsResult(settingsPage);
  } else if (settingsTab) {
    openSettings(settingsTab);
  }

  // Messages are one-off: take them out of the address so a reload doesn't repeat them.
  const oneOff = ['msg', 'err', 'settings'];
  if (oneOff.some(key => page.searchParams.has(key))) {
    oneOff.forEach(key => page.searchParams.delete(key));
    history.replaceState(null, '', page.pathname + (page.search || '') + page.hash);
  }


  /* ── Ideas list ─────────────────────────────────────────────────────── */
  // The list scrolls on its own beside the reading pane: show the selected row in it.

  const listPane = $('.list-pane');
  const selectedRow = listPane && $('[aria-current]', listPane);
  if (selectedRow && listPane.scrollHeight > listPane.clientHeight) {
    const top = selectedRow.offsetTop - listPane.offsetTop;
    if (top + selectedRow.offsetHeight > listPane.clientHeight) {
      listPane.scrollTop = top - listPane.clientHeight / 3;
    }
  }


  /* ── Live runs ──────────────────────────────────────────────────────── */
  // One stream per page feeds both the sidebar widget and, on a run page, the log.

  const log = $('[data-log][data-follow-run]');
  const widget = $('.live[data-follow-run]');
  const follow = log || widget;

  function markStages(stage, status) {
    const list = $('[data-stages]');
    if (!list) return;
    const items = $$('li', list);
    const at = items.findIndex(item => item.dataset.s === stage);
    const finished = status && status !== 'running';
    items.forEach((item, index) => {
      item.classList.toggle('done', stage === 'done' || (at >= 0 && index < at));
      item.classList.toggle('now', !finished && index === at && stage !== 'done');
    });
  }

  const stages = $('[data-stages]');
  if (stages) markStages(stages.dataset.stage, stages.dataset.status);

  function appendLog(event) {
    if (!log) return;
    $('.muted', log)?.remove();  // "No log lines yet."
    const nearBottom = log.scrollHeight - log.scrollTop - log.clientHeight < 80;
    const line = document.createElement('li');
    line.className = `log-${event.level}`;
    const time = document.createElement('time');
    time.dateTime = event.ts;
    time.textContent = new Date(event.ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    line.append(time, document.createTextNode(event.message));
    log.append(line);
    if (nearBottom) log.scrollTop = log.scrollHeight;
  }

  // Reload when the run ends, but never while a dialog is open (it may hold typing).
  function reloadWhenIdle() {
    const open = $('dialog[open]');
    if (!open) {
      location.reload();
      return;
    }
    open.addEventListener('close', reloadWhenIdle, { once: true });
  }

  if (follow && 'EventSource' in window) {
    const source = new EventSource(`/runs/${follow.dataset.followRun}/events?after=${follow.dataset.after || 0}`);
    source.onmessage = message => {
      const event = JSON.parse(message.data);
      appendLog(event);
      $$('[data-live-line]').forEach(line => { line.textContent = event.message; });
    };
    source.addEventListener('run', message => {
      const run = JSON.parse(message.data);
      $$('[data-count]').forEach(element => {
        if (run[element.dataset.count] !== undefined) element.textContent = run[element.dataset.count];
      });
      if (run.stage) $$('[data-live-stage]').forEach(stage => { stage.textContent = run.stage; });
      if (run.stage) markStages(run.stage, run.status);
    });
    source.addEventListener('end', () => {
      source.close();
      setTimeout(reloadWhenIdle, 600);
    });
  }
})();
