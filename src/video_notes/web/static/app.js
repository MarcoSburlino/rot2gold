(() => {
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const settingsDialog = $('#settings-dialog');
  const settingsContent = $('#settings-content');
  const url = new URL(location.href);
  const show = async (id) => {
    if (id === 'sidebar') {
      $('#sidebar').classList.add('is-open');
      return;
    }
    const dialog = document.getElementById(id);
    if (!dialog) return;
    if (id === 'settings-dialog') {
      try {
        const response = await fetch('/settings/panel');
        if (!response.ok) throw new Error('Settings could not be loaded.');
        settingsContent.innerHTML = await response.text();
        selectTab(url.searchParams.get('settings') || 'notes');
      } catch (error) {
        settingsContent.textContent = error.message;
        const link = document.createElement('a');
        link.href = '/settings';
        link.textContent = 'Open settings page';
        settingsContent.append(link);
      }
    }
    if (!dialog.open) dialog.showModal();
  };
  const selectTab = (tab) => {
    const root = settingsDialog.open ? settingsDialog : document;
    if (!$("[data-tab='" + tab + "']", root)) tab = 'notes';
    $$('[data-tab]', root).forEach(button => {
      const chosen = button.dataset.tab === tab;
      button.setAttribute('aria-selected', chosen ? 'true' : 'false');
      button.tabIndex = chosen ? 0 : -1;
    });
    $$('[data-panel]', root).forEach(panel => { panel.hidden = panel.dataset.panel !== tab; });
  };
  document.addEventListener('click', event => {
    const trigger = event.target.closest('[data-dialog]');
    if (trigger) {
      event.preventDefault();
      show(trigger.dataset.dialog);
      return;
    }
    const close = event.target.closest('[data-close]');
    if (close) {
      event.preventDefault();
      if (close.dataset.close === 'sidebar') $('#sidebar').classList.remove('is-open');
      else close.closest('dialog')?.close();
      return;
    }
    const tab = event.target.closest('[data-tab]');
    if (tab) selectTab(tab.dataset.tab);
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') $('#sidebar')?.classList.remove('is-open');
    const tab = event.target.closest('[role=tab]');
    if (!tab || !['ArrowLeft', 'ArrowRight'].includes(event.key)) return;
    const tabs = $$('[role=tab]', tab.parentElement);
    tabs[(tabs.indexOf(tab) + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length].focus();
    selectTab(document.activeElement.dataset.tab);
    event.preventDefault();
  });
  $$('#settings-dialog, dialog.card-dialog').forEach(dialog => {
    dialog.addEventListener('click', event => {
      if (event.target === dialog) dialog.close();
    });
  });
  if (url.searchParams.has('settings')) {
    if (location.pathname === '/settings') selectTab(url.searchParams.get('settings'));
    else show('settings-dialog');
  }
  const extract = $('#extract');
  if (extract) {
    const submit = $('.extract-submit', extract);
    const update = () => {
      const count = $$('input[name=conn]:checked', extract).length;
      submit.textContent = count === 0 ? 'Select a collection' : count === 1 ? 'Extract Material' : `Extract ${count} collections`;
      submit.disabled = count === 0 || !!$('.live-widget');
    };
    extract.addEventListener('change', update);
    update();
  }
  const stageList = $('#stages');
  const markStage = stage => {
    if (!stageList) return;
    const items = $$('[data-s]', stageList);
    const at = items.findIndex(item => item.dataset.s === stage);
    items.forEach((item, index) => {
      item.classList.toggle('done', at >= 0 && (index < at || stage === 'done'));
      item.classList.toggle('now', index === at && stage !== 'done');
    });
  };
  if (stageList) markStage(stageList.dataset.stage);
  const log = $('#log');
  const live = $('[data-live-run]');
  const runId = log?.dataset.running === 'true' ? log.dataset.runId : live?.dataset.liveRun;
  if (!runId) return;
  const after = log?.dataset.runId === runId ? log.dataset.after : '0';
  const events = new EventSource(`/runs/${runId}/events?after=${after}`);
  events.onmessage = message => {
    const item = JSON.parse(message.data);
    markStage(item.stage);
    const line = $('[data-live-line]');
    if (line) line.textContent = item.message;
    if (!log) return;
    const li = document.createElement('li');
    li.className = `lv-${item.level}`;
    const time = document.createElement('time');
    time.textContent = new Date(item.ts).toLocaleTimeString();
    li.append(time, document.createTextNode(item.message));
    log.append(li);
  };
  events.addEventListener('run', message => {
    const run = JSON.parse(message.data);
    markStage(run.stage);
    $$('[data-count]').forEach(node => { node.textContent = run[node.dataset.count]; });
    const liveStage = $('[data-live-stage]');
    if (liveStage) liveStage.textContent = run.stage || 'running';
    const status = $('#status');
    if (status) status.textContent = run.status;
  });
  events.addEventListener('end', () => { events.close(); location.reload(); });
})();
