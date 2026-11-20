// Admin page: sign in, collect files (drag and drop, file picker or folder picker),
// upload them straight to S3 with presigned URLs, then publish a new version.
// The API lives behind CloudFront at /api/*.

(function () {
  const API = "/api";
  const TOKEN_KEY = "govassist-admin-token";
  const PARALLEL_UPLOADS = 4;

  const $ = (id) => document.getElementById(id);
  let files = []; // { path, file }
  let deliverables = [];

  // ------------------------------------------------------------ API helpers

  function getToken() {
    try {
      return sessionStorage.getItem(TOKEN_KEY) || "";
    } catch {
      return "";
    }
  }

  function setToken(token) {
    try {
      if (token) sessionStorage.setItem(TOKEN_KEY, token);
      else sessionStorage.removeItem(TOKEN_KEY);
    } catch {
      /* private mode: the session simply ends with the tab */
    }
  }

  async function sha256Hex(text) {
    const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
    return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
  }

  // CloudFront signs requests to the Lambda function URL. For a request with a body
  // it needs the SHA-256 of the body in x-amz-content-sha256.
  async function api(path, options = {}) {
    const headers = { Accept: "application/json" };
    const token = getToken();
    if (token) headers["X-Admin-Token"] = token;
    let body;
    if (options.body !== undefined) {
      body = JSON.stringify(options.body);
      headers["Content-Type"] = "application/json";
      headers["x-amz-content-sha256"] = await sha256Hex(body);
    }
    const response = await fetch(API + path, { method: options.method || "GET", headers, body });
    let data = {};
    try {
      data = await response.json();
    } catch {
      /* non-JSON error page */
    }
    if (response.status === 401 && path !== "/login") {
      setToken("");
      showLogin();
    }
    if (!response.ok) throw new Error(data.error || `Request failed (${response.status}).`);
    return data;
  }

  // ------------------------------------------------------------ status and views

  function status(message, kind = "info") {
    const box = $("admin-status");
    box.hidden = !message;
    box.textContent = message || "";
    box.className = `admin-status admin-status-${kind}`;
  }

  function showLogin() {
    $("login-panel").hidden = false;
    $("work-panel").hidden = true;
  }

  async function showWork(username) {
    $("login-panel").hidden = true;
    $("work-panel").hidden = false;
    $("signed-in-as").textContent = `Signed in as ${username}`;
    await loadDeliverables();
  }

  function escapeHtml(value) {
    const el = document.createElement("div");
    el.textContent = value ?? "";
    return el.innerHTML;
  }

  function humanSize(n) {
    if (n < 1024) return `${n} B`;
    if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
    if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`;
    return `${(n / 1024 / 1024 / 1024).toFixed(2)} GB`;
  }

  // ------------------------------------------------------------ sign in

  $("login-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = $("login-button");
    button.disabled = true;
    status("Signing in…");
    try {
      const data = await api("/login", {
        method: "POST",
        body: { username: $("login-username").value.trim(), password: $("login-password").value },
      });
      setToken(data.token);
      $("login-password").value = "";
      status("");
      await showWork(data.username);
    } catch (error) {
      status(error.message, "error");
    } finally {
      button.disabled = false;
    }
  });

  $("sign-out").addEventListener("click", () => {
    setToken("");
    files = [];
    renderFiles();
    status("Signed out.");
    showLogin();
  });

  // ------------------------------------------------------------ collecting files

  function addFiles(list) {
    const known = new Set(files.map((f) => f.path));
    for (const item of list) {
      const path = (item.path || item.file.webkitRelativePath || item.file.name).replace(/^\/+/, "");
      if (!known.has(path)) {
        files.push({ path, file: item.file });
        known.add(path);
      }
    }
    files.sort((a, b) => a.path.localeCompare(b.path));
    renderFiles();
  }

  function renderFiles() {
    const list = $("upload-list");
    const total = files.reduce((sum, f) => sum + f.file.size, 0);
    list.innerHTML = files.length
      ? `<p class="upload-total">${files.length} file${files.length === 1 ? "" : "s"} · ${humanSize(total)}</p>` +
        files
          .map(
            (f, i) => `
          <div class="upload-row" data-index="${i}">
            <span class="upload-path">${escapeHtml(f.path)}</span>
            <span class="upload-size">${humanSize(f.file.size)}</span>
            <span class="upload-progress"><span style="width:0%"></span></span>
          </div>`
          )
          .join("")
      : "";
    $("clear-row").hidden = files.length === 0;

    const primary = $("primary");
    const current = primary.value;
    primary.innerHTML =
      '<option value="">Choose automatically</option>' +
      files.map((f) => `<option value="${escapeHtml(f.path)}">${escapeHtml(f.path)}</option>`).join("");
    if (files.some((f) => f.path === current)) primary.value = current;
  }

  function readAllEntries(reader) {
    return new Promise((resolve, reject) => {
      const all = [];
      const next = () =>
        reader.readEntries((batch) => {
          if (!batch.length) return resolve(all);
          all.push(...batch);
          next();
        }, reject);
      next();
    });
  }

  async function walkEntry(entry, prefix, out) {
    if (entry.isFile) {
      const file = await new Promise((resolve, reject) => entry.file(resolve, reject));
      out.push({ path: prefix + file.name, file });
    } else if (entry.isDirectory) {
      const children = await readAllEntries(entry.createReader());
      for (const child of children) await walkEntry(child, `${prefix}${entry.name}/`, out);
    }
  }

  const zone = $("drop-zone");
  ["dragenter", "dragover"].forEach((type) =>
    zone.addEventListener(type, (event) => {
      event.preventDefault();
      zone.classList.add("is-dragging");
    })
  );
  ["dragleave", "dragend"].forEach((type) => zone.addEventListener(type, () => zone.classList.remove("is-dragging")));
  zone.addEventListener("drop", async (event) => {
    event.preventDefault();
    zone.classList.remove("is-dragging");
    // Entries must be taken synchronously, before any await.
    const entries = Array.from(event.dataTransfer.items || [])
      .map((item) => (item.webkitGetAsEntry ? item.webkitGetAsEntry() : null))
      .filter(Boolean);
    if (!entries.length) {
      addFiles(Array.from(event.dataTransfer.files || [], (file) => ({ file })));
      return;
    }
    status("Reading dropped files…");
    const out = [];
    try {
      for (const entry of entries) await walkEntry(entry, "", out);
      addFiles(out);
      status("");
    } catch (error) {
      status(`Could not read the dropped folder: ${error.message}`, "error");
    }
  });

  $("pick-files").addEventListener("click", () => $("file-input").click());
  $("pick-folder").addEventListener("click", () => $("folder-input").click());
  $("file-input").addEventListener("change", (e) => {
    addFiles(Array.from(e.target.files, (file) => ({ file, path: file.name })));
    e.target.value = "";
  });
  $("folder-input").addEventListener("change", (e) => {
    addFiles(Array.from(e.target.files, (file) => ({ file, path: file.webkitRelativePath || file.name })));
    e.target.value = "";
  });
  $("clear-files").addEventListener("click", () => {
    files = [];
    renderFiles();
  });

  // ------------------------------------------------------------ deliverables

  async function loadDeliverables() {
    try {
      const data = await api("/deliverables");
      deliverables = data.deliverables || [];
    } catch (error) {
      status(error.message, "error");
      return;
    }
    const target = $("target");
    const chosen = target.value;
    target.innerHTML =
      '<option value="">A new deliverable</option>' +
      deliverables
        .map((d) => `<option value="${escapeHtml(d.slug)}">New version of: ${escapeHtml(d.title)}</option>`)
        .join("");
    if (deliverables.some((d) => d.slug === chosen)) target.value = chosen;

    $("admin-published").innerHTML = deliverables.length
      ? deliverables
          .map((d) => {
            const latest = d.versions[0];
            const fileCount = d.versions.reduce((n, v) => n + v.files.length, 0);
            return `
          <article class="archive-row">
            <span class="archive-date">${escapeHtml(latest.date)}</span>
            <div>
              <h3><a href="${escapeHtml(latest.url)}" target="_blank" rel="noopener">${escapeHtml(d.title)}</a></h3>
              <p>${d.versions
                .map((v) => `<a href="${escapeHtml(v.url)}" target="_blank" rel="noopener">${escapeHtml(v.version)}</a>`)
                .join(" · ")} · ${fileCount} file${fileCount === 1 ? "" : "s"} · <a href="${escapeHtml(d.url)}" target="_blank" rel="noopener">all versions</a></p>
            </div>
            <span class="archive-version">${escapeHtml(latest.version)}</span>
            <span class="archive-authors">${escapeHtml(d.kind)}</span>
          </article>`;
          })
          .join("")
      : '<p class="archive-empty">Nothing published yet.</p>';
  }

  $("target").addEventListener("change", () => {
    const d = deliverables.find((x) => x.slug === $("target").value);
    $("title").disabled = Boolean(d);
    $("kind").disabled = Boolean(d);
    if (d) {
      $("title").value = d.title;
      $("kind").value = d.kind;
      $("version").placeholder = `newer than ${d.versions[0].version}`;
    } else {
      $("version").placeholder = "v1.0";
    }
  });

  // ------------------------------------------------------------ upload and publish

  function putFile(target, item, row) {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("PUT", target.url);
      Object.entries(target.headers).forEach(([k, v]) => xhr.setRequestHeader(k, v));
      const bar = row?.querySelector(".upload-progress span");
      xhr.upload.onprogress = (e) => {
        if (bar && e.lengthComputable) bar.style.width = `${Math.round((e.loaded / e.total) * 100)}%`;
      };
      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          if (bar) bar.style.width = "100%";
          row?.classList.add("is-done");
          resolve();
        } else reject(new Error(`${item.path} failed to upload (${xhr.status}).`));
      };
      xhr.onerror = () => reject(new Error(`${item.path} failed to upload (network error).`));
      xhr.send(item.file);
    });
  }

  // The server answers in the same order as the files were sent, with each file's index.
  async function uploadAll(targets) {
    let next = 0;
    let done = 0;
    const worker = async () => {
      while (next < targets.length) {
        const target = targets[next++];
        const item = files[target.index];
        if (!item) throw new Error(`Could not match ${target.path} to a chosen file.`);
        const row = document.querySelector(`.upload-row[data-index="${target.index}"]`);
        await putFile(target, item, row);
        done += 1;
        status(`Uploading… ${done} of ${targets.length} files`);
      }
    };
    await Promise.all(Array.from({ length: Math.min(PARALLEL_UPLOADS, targets.length) }, worker));
  }

  $("publish-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const result = $("publish-result");
    result.hidden = true;
    if (!files.length) {
      status("Add at least one file first.", "error");
      return;
    }
    const button = $("publish-button");
    button.disabled = true;
    try {
      status("Preparing the upload…");
      const upload = await api("/uploads", {
        method: "POST",
        body: { files: files.map((f) => ({ path: f.path, size: f.file.size })) },
      });
      await uploadAll(upload.files);

      status("Publishing…");
      const slug = $("target").value;
      const published = await api("/publish", {
        method: "POST",
        body: {
          uploadId: upload.uploadId,
          slug: slug || undefined,
          title: $("title").value.trim(),
          kind: $("kind").value,
          version: $("version").value.trim(),
          date: $("date").value,
          authors: $("authors").value.split(/[,·]/).map((a) => a.trim()).filter(Boolean),
          changeSummary: $("summary").value.trim(),
          primaryPath: $("primary").value || undefined,
        },
      });
      status("Published.", "success");
      result.hidden = false;
      result.innerHTML = `<strong>Published ${escapeHtml(published.version)}.</strong>
        <a href="${escapeHtml(published.url)}" target="_blank" rel="noopener">Open the permanent page ↗</a>
        <a href="${escapeHtml(published.allVersionsUrl)}" target="_blank" rel="noopener">All versions ↗</a>`;
      files = [];
      renderFiles();
      $("version").value = "";
      $("summary").value = "";
      await loadDeliverables();
    } catch (error) {
      status(error.message, "error");
    } finally {
      button.disabled = false;
    }
  });

  // ------------------------------------------------------------ start

  $("date").value = new Date().toISOString().slice(0, 10);
  (async () => {
    if (!getToken()) return showLogin();
    try {
      const me = await api("/me");
      await showWork(me.username);
    } catch {
      showLogin();
    }
  })();
})();
