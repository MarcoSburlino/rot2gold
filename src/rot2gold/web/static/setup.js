// Rot2Gold setup page: small behaviours on top of a form that works without them.
// Shows only the fields for the chosen AI, adds a folder browser, suggests a local server's models,
// and after saving waits for the restarted app, then offers to open it.

(() => {
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];


  /* ── Fields for the chosen AI ───────────────────────────────────────── */

  const providerInputs = $$('input[name="provider"]');

  function showProviderFields() {
    const chosen = providerInputs.find(input => input.checked)?.value;
    $$('[data-for]').forEach(field => { field.hidden = field.dataset.for !== chosen; });
    if (chosen === 'local') loadModels();
  }

  providerInputs.forEach(input => input.addEventListener('change', showProviderFields));
  if (providerInputs.length) showProviderFields();


  /* ── Another folder: typing a path picks that option ─────────────────── */

  const otherVault = $('#vault-other');
  otherVault?.addEventListener('input', () => {
    const radio = $('[data-other-vault]');
    if (radio) radio.checked = true;
  });


  /* ── Local models: suggest what the server has ──────────────────────── */

  const localUrl = $('input[name="local_url"]');
  let modelsFor = null;

  async function loadModels() {
    const url = localUrl?.value.trim();
    if (!url || url === modelsFor) return;
    modelsFor = url;
    try {
      const response = await fetch(`/setup/models?url=${encodeURIComponent(url)}`);
      const { models } = await response.json();
      const list = $('#setup-models');
      list.replaceChildren(...models.map(name => Object.assign(document.createElement('option'), { value: name })));
      const model = $('input[name="model"]');
      if (models.length && !model.value) model.value = models[0];
    } catch {
      // The server isn't running: the field stays free text.
    }
  }

  localUrl?.addEventListener('change', loadModels);


  /* ── Folder browser ─────────────────────────────────────────────────── */

  const browser = $('#folder-browser');
  let target = null;
  let current = '';

  async function showFolder(path) {
    const response = await fetch(`/setup/dirs?path=${encodeURIComponent(path)}`);
    const folder = await response.json();
    current = folder.path;
    $('[data-folder-path]', browser).textContent = folder.path + (folder.vault ? '  (an Obsidian vault)' : '');
    const items = [];
    if (folder.parent) items.push(folderButton('↑ Up one folder', folder.parent));
    folder.dirs.forEach(dir => items.push(folderButton(dir.name, dir.path)));
    if (!folder.dirs.length) {
      items.push(Object.assign(document.createElement('li'), { className: 'muted', textContent: 'No folders inside.' }));
    }
    $('[data-folder-list]', browser).replaceChildren(...items);
    browser.dataset.free = folder.free;
  }

  function folderButton(label, path) {
    const item = document.createElement('li');
    const button = Object.assign(document.createElement('button'), { type: 'button', textContent: label });
    button.addEventListener('click', () => showFolder(path));
    item.append(button);
    return item;
  }

  $$('[data-browse]').forEach(button => {
    button.hidden = false;
    button.addEventListener('click', async () => {
      target = document.getElementById(button.dataset.browse);
      await showFolder(target.value.trim());
      browser.showModal();
    });
  });

  $('[data-folder-choose]')?.addEventListener('click', () => {
    target.value = current;
    target.dispatchEvent(new Event('input', { bubbles: true }));
    if (target.id === 'data-dir' && browser.dataset.free) $('[data-free]').textContent = browser.dataset.free;
    browser.close();
  });

  $$('[data-close]').forEach(button => button.addEventListener('click', () => button.closest('dialog').close()));
  browser?.addEventListener('click', event => { if (event.target === browser) browser.close(); });


  /* ── After saving: wait for the restarted app, then offer to open it ─── */

  const done = $('[data-restart-from]');
  if (done?.dataset.restartFrom) {
    const started = Date.now();
    const poll = async () => {
      try {
        const status = await (await fetch('/setup/status', { cache: 'no-store' })).json();
        if (status.boot !== done.dataset.restartFrom) {
          const open = Object.assign(document.createElement('a'), { href: '/ideas', className: 'button button-primary' });
          open.textContent = `Open ${document.title.split(' · ').pop()}`;
          $('[data-restart-note]').replaceChildren(open);
          open.focus();
          return;
        }
      } catch {
        // Between the old app stopping and the new one starting nothing answers: keep waiting.
      }
      if (Date.now() - started < 30000) setTimeout(poll, 500);
    };
    setTimeout(poll, 800);
  }
})();
