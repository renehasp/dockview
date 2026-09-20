let containers = [];
let images = [];
let catalog = { 'docker-hub': [], ghcr: [] };
let catalogSearchResults = [];
let catalogView = [];
let selectedRepo = null;
let activeRegistry = 'docker-hub';
let refreshTimer = null;
let repoSearchTimer = null;
let pullPollTimer = null;
let pullModalOpen = false;

const REGISTRY_LABELS = {
  'docker-hub': 'Docker Hub',
  ghcr: 'GitHub Container Registry',
};

function toast(message, type = 'success') {
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = message;
  document.getElementById('toasts').appendChild(el);
  setTimeout(() => el.remove(), 4000);
}

async function api(url, options = {}) {
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
  return data;
}

function catalogLogo(repo) {
  const fallback = repo.icon || '🐳';
  if (repo.logo_url) {
    return `<img class="catalog-logo" src="${esc(repo.logo_url)}" alt="${esc(repo.name)}" onerror="this.outerHTML='<div class=\\'catalog-logo-fallback\\'>${fallback}</div>'">`;
  }
  return `<div class="catalog-logo-fallback">${fallback}</div>`;
}

function registryBadgeClass(repo) {
  return repo.registry_id === 'ghcr' ? 'catalog-registry ghcr' : 'catalog-registry';
}

function registryLinkLabel(repo) {
  return repo.registry_id === 'ghcr' ? 'GHCR ↗' : 'Docker Hub ↗';
}

function renderCatalogItem(repo, index) {
  const portMeta = repo.container_port
    ? `Port ${repo.container_port}`
    : 'No default port';
  const officialBadge = repo.is_official
    ? `<span class="catalog-registry catalog-official">Official</span>`
    : '';
  const pullStat = repo.registry_id === 'ghcr'
    ? `<span class="catalog-stat">⬇ <strong>${esc(repo.pull_count_label || '—')}</strong></span>`
    : `<span class="catalog-stat">⬇ <strong>${esc(repo.pull_count_label || '0')}</strong> pulls</span>`;
  return `
    <div class="catalog-item">
      <div class="catalog-item-main">
        ${catalogLogo(repo)}
        <div class="catalog-title-wrap">
          <div class="catalog-name">${esc(repo.name)}</div>
          <div class="catalog-image-tag">${esc(repo.image)}</div>
          <div class="catalog-badges">
            <span class="${registryBadgeClass(repo)}">${esc(repo.registry || REGISTRY_LABELS[activeRegistry])}</span>
            ${officialBadge}
          </div>
          <p class="catalog-desc">${esc(repo.description || 'No description available.')}</p>
        </div>
      </div>
      <div class="catalog-item-stats">
        <span class="catalog-stat">⭐ <strong>${esc(repo.star_count_label || '0')}</strong></span>
        ${pullStat}
      </div>
      <div class="catalog-meta">${portMeta}</div>
      <div class="catalog-item-actions">
        <button class="btn-primary" onclick="openDeployModal(${index})">Deploy</button>
        <a class="btn-ghost" href="${esc(repo.registry_url)}" target="_blank" rel="noopener">${registryLinkLabel(repo)}</a>
      </div>
    </div>
  `;
}

function renderCatalog(list) {
  catalogView = list;
  const grid = document.getElementById('catalogGrid');
  if (!list.length) {
    grid.innerHTML = `<div class="empty-state"><div class="icon">🔍</div><p>No repositories found.</p></div>`;
    return;
  }
  grid.innerHTML = list.map((repo, index) => renderCatalogItem(repo, index)).join('');
}

function updateRegistryUI() {
  const label = REGISTRY_LABELS[activeRegistry];
  document.querySelectorAll('#registrySwitch button').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.registry === activeRegistry);
  });
  document.getElementById('repoSearchInput').placeholder =
    activeRegistry === 'ghcr' ? 'Search GHCR packages...' : 'Search Docker Hub repos...';
  document.getElementById('catalogSectionLabel').textContent =
    `Top 10 Popular Repos — ${label}`;
}

async function loadCatalog(registry = activeRegistry) {
  const grid = document.getElementById('catalogGrid');
  const label = document.getElementById('catalogSectionLabel');
  const registryLabel = REGISTRY_LABELS[registry];
  try {
    catalog[registry] = await api(`/api/catalog?registry=${encodeURIComponent(registry)}`);
    if (registry === activeRegistry) {
      label.textContent = `Top 10 Popular Repos — ${registryLabel}`;
      const q = document.getElementById('repoSearchInput').value.trim();
      if (!q) {
        renderCatalog(catalog[registry]);
      }
    }
  } catch (e) {
    if (registry === activeRegistry) {
      grid.innerHTML = `<div class="empty-state"><div class="icon">⚠️</div><p>Could not load popular repos: ${esc(e.message)}</p><button class="btn-ghost" onclick="loadCatalog()">Retry</button></div>`;
    }
    throw e;
  }
}

async function loadAllCatalogs() {
  await Promise.all([
    loadCatalog('docker-hub'),
    loadCatalog('ghcr'),
  ]);
}

function switchRegistry(registry) {
  if (registry === activeRegistry) return;
  activeRegistry = registry;
  document.getElementById('repoSearchInput').value = '';
  updateRegistryUI();
  renderCatalog(catalog[registry] || []);
  if (!catalog[registry]?.length) {
    loadCatalog(registry);
  }
}

async function searchRepos() {
  const q = document.getElementById('repoSearchInput').value.trim();
  const label = document.getElementById('catalogSectionLabel');
  const grid = document.getElementById('catalogGrid');
  const registryLabel = REGISTRY_LABELS[activeRegistry];

  clearTimeout(repoSearchTimer);
  if (!q) {
    label.textContent = `Top 10 Popular Repos — ${registryLabel}`;
    renderCatalog(catalog[activeRegistry] || []);
    return;
  }

  repoSearchTimer = setTimeout(async () => {
    label.textContent = `Search results for "${q}" — ${registryLabel}`;
    grid.innerHTML = `<div class="empty-state"><span class="spinner"></span> Searching ${registryLabel}...</div>`;
    try {
      catalogSearchResults = await api(
        `/api/catalog/search?q=${encodeURIComponent(q)}&registry=${encodeURIComponent(activeRegistry)}`
      );
      renderCatalog(catalogSearchResults);
    } catch (e) {
      grid.innerHTML = `<div class="empty-state"><div class="icon">⚠️</div><p>${esc(e.message)}</p></div>`;
    }
  }, 350);
}

function openCatalogPanel() {
  document.getElementById('catalogPanel').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function updateDeployPortPreview() {
  if (!selectedRepo) return;
  const hostPort = document.getElementById('deployHostPort').value || selectedRepo.default_host_port || '';
  const containerPort = selectedRepo.container_port;
  const preview = document.getElementById('deployPortPreview');
  if (!containerPort) {
    preview.textContent = 'No port mapping — container will start without published ports.';
    return;
  }
  preview.innerHTML =
    `Maps <strong>localhost:${esc(String(hostPort))}</strong> → container port <strong>${containerPort}</strong>`;
}

function openDeployModal(index) {
  selectedRepo = catalogView[index];
  if (!selectedRepo) return;
  const repo = selectedRepo;
  const safeId = (repo.id || repo.image || 'app').replace(/[^a-zA-Z0-9_.-]+/g, '-');
  document.getElementById('deployModalTitle').textContent = `Deploy ${repo.name}`;
  document.getElementById('deployImage').value = repo.image;
  document.getElementById('deployHostPort').value = repo.default_host_port || '';
  document.getElementById('deployHostPort').disabled = !repo.container_port;
  document.getElementById('deployName').value = `dockview-${safeId}`;
  updateDeployPortPreview();

  const envHint = document.getElementById('deployEnvHint');
  if (repo.env_defaults && Object.keys(repo.env_defaults).length) {
    const envText = Object.entries(repo.env_defaults).map(([k, v]) => `${k}=${v}`).join(', ');
    envHint.textContent = `Default env: ${envText}`;
    envHint.style.display = 'block';
  } else {
    envHint.style.display = 'none';
  }

  document.getElementById('deployModal').classList.add('open');
}

function closeDeployModal() {
  document.getElementById('deployModal').classList.remove('open');
  document.getElementById('deployHostPort').disabled = false;
  selectedRepo = null;
}

async function deployCatalogRepo() {
  if (!selectedRepo) return;
  const btn = document.getElementById('deployBtn');
  const hostPortRaw = document.getElementById('deployHostPort').value;
  const hostPort = hostPortRaw === '' ? null : parseInt(hostPortRaw, 10);
  const name = document.getElementById('deployName').value.trim();

  if (selectedRepo.container_port && (!hostPort || hostPort < 1 || hostPort > 65535)) {
    toast('Enter a valid host port (1–65535)', 'error');
    return;
  }

  btn.disabled = true;
  btn.textContent = 'Pulling & deploying...';
  try {
    const body = {
      id: selectedRepo.id,
      image: selectedRepo.image,
      name,
      host_port: hostPort,
      container_port: selectedRepo.container_port || null,
    };
    const r = await api('/api/catalog/deploy', {
      method: 'POST',
      body: JSON.stringify(body),
    });
    const extra = r.pulled ? ' (image downloaded)' : '';
    toast(r.message + extra);
    if (r.access_url) toast(`Access at ${r.access_url}`);
    closeDeployModal();
    await refreshAll();
  } catch (e) { toast(e.message, 'error'); }
  finally {
    btn.disabled = false;
    btn.textContent = 'Pull & Deploy';
  }
}

async function loadStats() {
  const s = await api('/api/stats');
  document.getElementById('statTotal').textContent = s.total_containers;
  document.getElementById('statRunning').textContent = s.running;
  document.getElementById('statStopped').textContent = s.stopped;
  document.getElementById('statImages').textContent = s.images;
}

async function loadImages() {
  images = await api('/api/images');
  const dl = document.getElementById('imageList');
  dl.innerHTML = images.map(i => `<option value="${i.tag}">`).join('');
  renderImages(images);
}

function renderImages(list) {
  const tbody = document.getElementById('imageTable');
  if (!list.length) {
    tbody.innerHTML = `<tr><td colspan="4"><div class="empty-state"><div class="icon">🖼️</div><p>No images found.</p></div></td></tr>`;
    return;
  }
  tbody.innerHTML = list.map(i => `
    <tr>
      <td class="image-tag">${esc(i.tag)}</td>
      <td class="container-id">${esc(i.id)}</td>
      <td class="image-size">${esc(i.size_label || '—')}</td>
      <td>
        <div class="actions">
          <button class="btn-danger" data-image-id="${esc(i.image_id || i.id)}" data-tag="${esc(i.tag)}" onclick="removeImage(this)">✕ Delete</button>
        </div>
      </td>
    </tr>
  `).join('');
}

function filterImages() {
  const q = document.getElementById('imageSearchInput').value.toLowerCase();
  const filtered = images.filter(i =>
    i.tag.toLowerCase().includes(q) ||
    i.id.toLowerCase().includes(q)
  );
  renderImages(filtered);
}

async function loadContainers() {
  containers = await api('/api/containers');
  renderContainers(containers);
  document.getElementById('lastRefresh').textContent =
    'Updated ' + new Date().toLocaleTimeString();
}

function renderContainers(list) {
  const tbody = document.getElementById('containerTable');
  if (!list.length) {
    tbody.innerHTML = `<tr><td colspan="5"><div class="empty-state"><div class="icon">📦</div><p>No containers found. Create one to get started.</p></div></td></tr>`;
    return;
  }
  tbody.innerHTML = list.map(c => `
    <tr data-name="${c.name.toLowerCase()}">
      <td>
        <div class="container-name">${esc(c.name)}</div>
        <div class="container-id">${esc(c.id)}</div>
        ${sourceBadge(c)}
      </td>
      <td>
        <span class="badge ${c.running ? 'running' : 'stopped'}">
          <span class="badge-dot"></span>
          ${c.running ? 'Running' : 'Stopped'}
        </span>
      </td>
      <td>${esc(c.image)}</td>
      <td class="ports">${c.ports.length ? c.ports.map(esc).join('<br>') : '—'}</td>
      <td>
        <div class="actions">
          ${c.running
            ? `<button class="btn-warning" onclick="stopContainer('${c.id}')">■ Stop</button>`
            : `<button class="btn-success" onclick="startContainer('${c.id}')">▶ Start</button>`}
          ${c.can_pull_latest
            ? `<button class="btn-info" data-id="${esc(c.id)}" data-name="${esc(c.name)}" data-source="${esc(c.update_source || '')}" data-github="${esc(c.github_repo || '')}" data-image="${esc(c.image)}" data-running="${c.running}" title="${esc(pullLatestTitle(c))}" onclick="pullLatest(this)">⬇ Pull Latest</button>`
            : ''}
          <button class="btn-danger" data-id="${c.id}" data-name="${esc(c.name)}" data-running="${c.running}" onclick="removeContainer(this)">✕ Remove</button>
        </div>
      </td>
    </tr>
  `).join('');
}

function esc(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

function filterContainers() {
  const q = document.getElementById('searchInput').value.toLowerCase();
  const filtered = containers.filter(c =>
    c.name.toLowerCase().includes(q) ||
    c.image.toLowerCase().includes(q) ||
    c.id.toLowerCase().includes(q)
  );
  renderContainers(filtered);
}

async function startContainer(id) {
  try {
    const r = await api(`/api/containers/${id}/start`, { method: 'POST' });
    toast(r.message);
    await refreshAll();
  } catch (e) { toast(e.message, 'error'); }
}

async function stopContainer(id) {
  try {
    const r = await api(`/api/containers/${id}/stop`, { method: 'POST' });
    toast(r.message);
    await refreshAll();
  } catch (e) { toast(e.message, 'error'); }
}

function sourceBadge(c) {
  if (!c.update_source) return '';
  const labels = { github: 'GitHub', compose: 'Compose', registry: 'Registry' };
  const label = c.update_source_label || labels[c.update_source] || c.update_source;
  const extra = c.github_repo ? ` · ${esc(c.github_repo)}` : '';
  return `<span class="source-badge ${esc(c.update_source)}">${esc(label)}${extra}</span>`;
}

function pullLatestTitle(c) {
  if (c.update_source === 'github') {
    return c.github_repo
      ? `Pull latest GitHub release/code for ${c.github_repo}, rebuild, and run`
      : 'Pull latest GitHub release/code, rebuild, and run';
  }
  if (c.update_source === 'compose') {
    return 'Rebuild from Docker Compose and run the latest image';
  }
  return `Pull the latest ${c.image} image and recreate this container`;
}

function pullLatestConfirmMessage(name, source, image, running, github) {
  const restart = running ? ' The container will restart.' : ' The container will be recreated (still stopped).';
  if (source === 'github') {
    const repo = github ? ` (${github})` : '';
    return `Pull the latest GitHub release and codebase for "${name}"${repo}, rebuild the Docker image, and run it?${restart}`;
  }
  if (source === 'compose') {
    return `Rebuild "${name}" from its local Docker Compose source, pull newer base images, and run it?${restart}`;
  }
  return `Pull the latest "${image}" image from the registry and recreate "${name}"?${restart}`;
}

function setPullModalState(status, message, logs) {
  const statusEl = document.getElementById('pullStatus');
  const logEl = document.getElementById('pullLog');
  const closeBtn = document.getElementById('pullCloseBtn');
  const closeX = document.getElementById('pullModalCloseX');
  const running = status === 'running';
  statusEl.className = `pull-status ${status}`;
  if (running) {
    statusEl.innerHTML = `<span class="spinner"></span>${esc(message || 'Working…')}`;
  } else {
    statusEl.textContent = message || (status === 'success' ? 'Done' : 'Failed');
  }
  closeBtn.disabled = running;
  closeX.disabled = running;
  logEl.textContent = (logs && logs.length) ? logs.join('\n') : '';
  logEl.scrollTop = logEl.scrollHeight;
}

function openPullModal(name) {
  pullModalOpen = true;
  document.getElementById('pullModalTitle').textContent = `Pull Latest — ${name}`;
  setPullModalState('running', 'Starting…', []);
  document.getElementById('pullModal').classList.add('open');
}

function closePullModal() {
  if (pullPollTimer) {
    clearInterval(pullPollTimer);
    pullPollTimer = null;
  }
  pullModalOpen = false;
  document.getElementById('pullModal').classList.remove('open');
}

async function pollPullJob(jobId) {
  const job = await api(`/api/jobs/${jobId}`);
  setPullModalState(job.status, job.message, job.logs || []);
  if (job.status === 'running') return false;
  if (pullPollTimer) {
    clearInterval(pullPollTimer);
    pullPollTimer = null;
  }
  if (job.status === 'success') {
    toast(job.message);
    await refreshAll();
  } else {
    toast(job.message || 'Pull Latest failed', 'error');
  }
  return true;
}

async function pullLatest(btn) {
  const id = btn.dataset.id;
  const name = btn.dataset.name;
  const source = btn.dataset.source;
  const github = btn.dataset.github;
  const image = btn.dataset.image;
  const running = btn.dataset.running === 'true';
  if (!id) return;
  if (!confirm(pullLatestConfirmMessage(name, source, image, running, github))) return;

  btn.disabled = true;
  openPullModal(name);
  try {
    const res = await fetch(`/api/containers/${id}/pull-latest`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok && res.status !== 202) {
      throw new Error(data.error || `Request failed (${res.status})`);
    }
    const job = data.job;
    if (!job || !job.id) throw new Error(data.error || 'Pull Latest did not start');
    setPullModalState(job.status || 'running', job.message, job.logs || []);
    if (job.status === 'running') {
      pullPollTimer = setInterval(async () => {
        try {
          await pollPullJob(job.id);
        } catch (e) {
          setPullModalState('error', e.message, []);
          clearInterval(pullPollTimer);
          pullPollTimer = null;
        }
      }, 1000);
      await pollPullJob(job.id);
    } else if (job.status === 'success') {
      toast(job.message);
      await refreshAll();
    } else if (job.status === 'error') {
      toast(job.message || 'Pull Latest failed', 'error');
    }
  } catch (e) {
    setPullModalState('error', e.message, []);
    toast(e.message, 'error');
  } finally {
    btn.disabled = false;
  }
}

async function removeImage(btn, force = false) {
  const tag = btn.dataset.tag;
  const imageId = btn.dataset.imageId;
  const ref = imageId || tag;
  const label = tag || imageId;
  if (!ref || ref === 'undefined') {
    toast('Could not determine image reference', 'error');
    return;
  }
  if (!force && !confirm(`Delete image "${label}"?`)) return;
  try {
    let data = await api('/api/images/delete', {
      method: 'POST',
      body: JSON.stringify({ ref, force }),
    });
    toast(data.message);
    await refreshAll();
  } catch (e) {
    if (!force && e.message.includes('must be forced')) {
      if (confirm(`${e.message}\n\nForce delete anyway?`)) {
        await removeImage(btn, true);
      }
      return;
    }
    toast(e.message, 'error');
  }
}

async function removeContainer(btn) {
  const id = btn.dataset.id;
  const name = btn.dataset.name;
  const running = btn.dataset.running === 'true';
  const msg = running
    ? `Force remove running container "${name}"?`
    : `Remove container "${name}"?`;
  if (!confirm(msg)) return;
  try {
    const url = `/api/containers/${id}${running ? '?force=true' : ''}`;
    const r = await api(url, { method: 'DELETE' });
    toast(r.message);
    await refreshAll();
  } catch (e) { toast(e.message, 'error'); }
}

function openModal() {
  document.getElementById('modal').classList.add('open');
  loadImages();
}

function closeModal() {
  document.getElementById('modal').classList.remove('open');
}

async function createContainer() {
  const btn = document.getElementById('createBtn');
  btn.disabled = true;
  btn.textContent = 'Creating...';
  try {
    const image = document.getElementById('imageInput').value.trim();
    const body = {
      image,
      name: document.getElementById('nameInput').value.trim(),
      ports: document.getElementById('portsInput').value.trim(),
      env: document.getElementById('envInput').value.trim(),
      command: document.getElementById('cmdInput').value.trim(),
    };
    const r = await api('/api/containers', { method: 'POST', body: JSON.stringify(body) });
    toast(r.message);
    closeModal();
    document.getElementById('imageInput').value = '';
    document.getElementById('nameInput').value = '';
    document.getElementById('portsInput').value = '';
    document.getElementById('envInput').value = '';
    document.getElementById('cmdInput').value = '';
    await refreshAll();
  } catch (e) { toast(e.message, 'error'); }
  finally {
    btn.disabled = false;
    btn.textContent = 'Create & Start';
  }
}

async function refreshContainers() {
  const btn = document.getElementById('refreshContainersBtn');
  btn.disabled = true;
  try {
    await Promise.all([loadStats(), loadContainers()]);
    toast('Containers refreshed');
  } catch (e) { toast(e.message, 'error'); }
  finally { btn.disabled = false; }
}

async function refreshImages() {
  const btn = document.getElementById('refreshImagesBtn');
  btn.disabled = true;
  try {
    await Promise.all([loadStats(), loadImages()]);
    toast('Images refreshed');
  } catch (e) { toast(e.message, 'error'); }
  finally { btn.disabled = false; }
}

async function refreshAll(fullPage = false) {
  if (fullPage) {
    location.reload();
    return;
  }

  const btn = document.getElementById('refreshBtn');
  btn.disabled = true;
  const results = await Promise.allSettled([
    loadStats(),
    loadAllCatalogs(),
    loadContainers(),
    loadImages(),
  ]);
  const failed = results.filter(r => r.status === 'rejected');
  if (failed.length) {
    toast(failed[0].reason?.message || 'Some data failed to load', 'error');
  }
  btn.disabled = false;
}

document.getElementById('modal').addEventListener('click', e => {
  if (e.target === e.currentTarget) closeModal();
});

document.getElementById('deployModal').addEventListener('click', e => {
  if (e.target === e.currentTarget) closeDeployModal();
});

document.getElementById('pullModal').addEventListener('click', e => {
  if (e.target === e.currentTarget && !document.getElementById('pullCloseBtn').disabled) {
    closePullModal();
  }
});

document.getElementById('deployHostPort').addEventListener('input', updateDeployPortPreview);

refreshAll();
refreshTimer = setInterval(() => {
  if (!pullModalOpen) refreshAll();
}, 10000);
