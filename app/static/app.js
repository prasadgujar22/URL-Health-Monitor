const list = document.querySelector('#list');
const form = document.querySelector('#add-form');
const message = document.querySelector('#message');

function say(text, error = false) {
  message.textContent = text;
  message.classList.toggle('error', error);
}

function time(value) {
  if (!value) return 'Never checked';
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

function statusLabel(status) {
  if (status === 'UP') return 'Up';
  if (status === 'DOWN') return 'Down';
  return 'Pending';
}

function statusClass(status) {
  if (status === 'UP') return 'up';
  if (status === 'DOWN') return 'down';
  return 'pending';
}

function setState(className, content) {
  list.replaceChildren();
  const el = document.createElement('div');
  el.className = `state ${className}`;
  if (typeof content === 'string') {
    el.textContent = content;
  } else {
    el.append(...content);
  }
  list.append(el);
}

async function refresh() {
  setState('loading', 'Loading monitored URLs…');
  try {
    const r = await fetch('/api/urls');
    if (!r.ok) throw new Error('Could not load monitored URLs.');
    const items = await r.json();
    if (!items.length) {
      const title = document.createElement('strong');
      title.textContent = 'Nothing monitored yet';
      setState('empty', [title, document.createTextNode('Add a public URL above to start checking.')]);
      return;
    }
    list.replaceChildren();
    for (const item of items) {
      const card = document.querySelector('#card').content.cloneNode(true);
      const el = card.querySelector('.card');
      const badge = card.querySelector('[data-role="badge"]');
      const label = card.querySelector('.badge-label');
      const link = card.querySelector('.url');
      const err = card.querySelector('.err');
      const status = item.status || 'PENDING';

      el.dataset.id = item.id;
      badge.classList.add(statusClass(status));
      badge.setAttribute('aria-label', `Status: ${statusLabel(status)}`);
      label.textContent = statusLabel(status);

      link.textContent = item.url;
      link.href = item.url;

      const pending = status === 'PENDING' || !item.status;
      card.querySelector('.meta').textContent = pending
        ? 'Pending first check'
        : `${statusLabel(status)} · ${item.http_code === null ? 'No HTTP response' : `HTTP ${item.http_code}`} · ${item.elapsed_ms} ms · ${time(item.checked_at)}`;

      if (item.error) {
        err.hidden = false;
        err.textContent = `Check failed: ${item.error.replaceAll('_', ' ')}`;
      }

      const del = card.querySelector('.delete');
      del.setAttribute('aria-label', `Delete ${item.url}`);
      del.addEventListener('click', () => remove(item.id));
      list.append(card);
    }
  } catch (e) {
    setState('error-state', e.message);
  }
}

async function remove(id) {
  const btn = list.querySelector(`[data-id="${id}"] .delete`);
  if (btn) btn.disabled = true;
  try {
    const r = await fetch(`/api/urls/${id}`, { method: 'DELETE' });
    if (!r.ok) throw new Error('Could not delete URL. Try again.');
    await refresh();
  } catch (e) {
    if (btn) btn.disabled = false;
    say(e.message, true);
  }
}

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  const btn = form.querySelector('button');
  btn.disabled = true;
  say('Adding URL…');
  try {
    const r = await fetch('/api/urls', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ url: form.url.value }),
    });
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || 'Could not add URL.');
    form.reset();
    say('URL added. Waiting for its first check.');
    await refresh();
  } catch (err) {
    say(err.message, true);
  } finally {
    btn.disabled = false;
  }
});

document.querySelector('#refresh').addEventListener('click', refresh);
refresh();
setInterval(refresh, 15000);
