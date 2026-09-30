/* ═══════════════════════════════════════════════════════════════════
   DocWiz frontend — vanilla JS, no framework, no build step.
   State lives in plain variables; rendering is plain DOM manipulation.
   ═══════════════════════════════════════════════════════════════════ */
"use strict";

(() => {
  const $ = (id) => document.getElementById(id);

  const els = {
    sidebar: $("sidebar"),
    sidebarToggle: $("sidebarToggle"),
    scrim: $("scrim"),
    uploadZone: $("uploadZone"),
    fileInput: $("fileInput"),
    uploadProgress: $("uploadProgress"),
    uploadProgressText: $("uploadProgressText"),
    docList: $("docList"),
    docsEmpty: $("docsEmpty"),
    docCount: $("docCount"),
    resetBtn: $("resetBtn"),
    statusChip: $("statusChip"),
    thread: $("thread"),
    threadInner: document.querySelector(".thread__inner"),
    emptyState: $("emptyState"),
    greetingText: $("greetingText"),
    exampleChips: $("exampleChips"),
    composer: $("composer"),
    composerAdd: $("composerAdd"),
    composerMeta: $("composerMeta"),
    questionInput: $("questionInput"),
    sendBtn: $("sendBtn"),
    toastRegion: $("toastRegion"),
  };

  const state = {
    busy: false,
    health: null,
    docs: [],
  };

  const PDF_ICON =
    '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H7a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7z"/><path d="M14 2v5h5"/><path d="M9.5 13.5h5M9.5 17h5"/></svg>';
  const X_ICON =
    '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>';

  /* ── tiny helpers ─────────────────────────────────────────────────── */

  function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }

  function formatBytes(bytes) {
    if (!bytes && bytes !== 0) return "";
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  function pageLabel(source) {
    if (source.page_end && source.page_end !== source.page_start) {
      return `Pages ${source.page_start}–${source.page_end}`;
    }
    return `Page ${source.page_start}`;
  }

  async function fetchJson(url, options = {}) {
    let response;
    try {
      response = await fetch(url, options);
    } catch (err) {
      throw Object.assign(new Error("Network error — is the DocWiz server running?"), { code: "network_error" });
    }
    let body = null;
    try {
      body = await response.json();
    } catch (err) {
      /* non-JSON error body */
    }
    if (!response.ok) {
      const message = body && body.error ? body.error.message : `Request failed (${response.status}).`;
      const code = body && body.error ? body.error.code : `http_${response.status}`;
      throw Object.assign(new Error(message), { code });
    }
    return body;
  }

  function toast(message, kind = "info", title = null) {
    const node = document.createElement("div");
    node.className = `toast${kind === "error" ? " toast--error" : ""}`;
    node.innerHTML = `${title ? `<strong>${escapeHtml(title)}</strong>` : ""}${escapeHtml(message)}`;
    els.toastRegion.appendChild(node);
    setTimeout(() => {
      node.style.opacity = "0";
      node.style.transition = "opacity 0.3s ease";
      setTimeout(() => node.remove(), 320);
    }, 5200);
  }

  function scrollToBottom() {
    els.thread.scrollTop = els.thread.scrollHeight;
  }

  /* ── health + status chip ─────────────────────────────────────────── */

  async function refreshHealth() {
    try {
      state.health = await fetchJson("/api/health");
      const h = state.health;
      if (!h.api_key_configured) {
        els.statusChip.textContent = "API key missing";
        els.statusChip.className = "chip chip--status chip--status-warn";
        els.statusChip.title =
          "Set GROQ_API_KEY in your .env file and restart DocWiz to enable answers.";
      } else {
        els.statusChip.textContent = "Ready";
        els.statusChip.className = "chip chip--status chip--status-ok";
        els.statusChip.title = `Groq model: ${h.groq_model}`;
      }
      if (els.composerMeta) {
        const providerLabel = (h.embedding_provider || "").replace(/(^|\s)\S/g, (c) => c.toUpperCase());
        els.composerMeta.textContent = h.groq_model || "";
        els.composerMeta.title = `Answers: ${h.groq_model} · Embeddings: ${providerLabel} (${h.embedding_model})`;
        els.composerMeta.hidden = false;
      }
    } catch (err) {
      els.statusChip.textContent = "Offline";
      els.statusChip.className = "chip chip--status chip--status-warn";
    }
  }

  /* ── documents ────────────────────────────────────────────────────── */

  function setDocs(docs) {
    state.docs = docs || [];
    renderDocs();
  }

  function renderDocs() {
    els.docList.innerHTML = "";
    els.docCount.textContent = String(state.docs.length);
    els.docsEmpty.hidden = state.docs.length > 0;

    for (const doc of state.docs) {
      const li = document.createElement("li");
      li.className = "doc-row";
      li.innerHTML = `
        <span class="doc-row__icon" aria-hidden="true">${PDF_ICON}</span>
        <span class="doc-row__body">
          <span class="doc-row__name" title="${escapeHtml(doc.filename)}">${escapeHtml(doc.filename)}</span>
          <span class="doc-row__meta">${doc.pages} page${doc.pages === 1 ? "" : "s"} · ${doc.chunk_count} passages${doc.size_bytes ? " · " + formatBytes(doc.size_bytes) : ""}</span>
        </span>
        <button type="button" class="doc-row__remove" aria-label="Remove ${escapeHtml(doc.filename)}" data-doc-id="${doc.doc_id}">${X_ICON}</button>`;
      li.querySelector(".doc-row__remove").addEventListener("click", onRemoveDoc);
      els.docList.appendChild(li);
    }
  }

  function showSkeletons(count) {
    els.docsEmpty.hidden = true;
    for (let i = 0; i < count; i += 1) {
      const li = document.createElement("li");
      li.className = "doc-row doc-row--skeleton";
      li.innerHTML = `
        <span class="doc-row__icon" aria-hidden="true">${PDF_ICON}</span>
        <span class="doc-row__body">
          <span class="doc-row__name">Skeleton</span>
          <span class="doc-row__meta">Skeleton meta line</span>
        </span>`;
      els.docList.appendChild(li);
    }
  }

  async function onRemoveDoc(event) {
    const button = event.currentTarget;
    if (!button.classList.contains("confirming")) {
      button.classList.add("confirming");
      button.textContent = "Remove?";
      setTimeout(() => {
        button.classList.remove("confirming");
        button.innerHTML = X_ICON;
      }, 3000);
      return;
    }
    const docId = button.dataset.docId;
    try {
      await fetchJson(`/api/documents/${docId}`, { method: "DELETE" });
      setDocs(state.docs.filter((d) => d.doc_id !== docId));
      refreshHealth();
    } catch (err) {
      toast(err.message, "error", "Could not remove document");
    }
  }

  async function uploadFiles(fileList) {
    const files = Array.from(fileList || []);
    if (!files.length) return;
    if (state.busy) {
      toast("Please wait until the current upload finishes.", "info");
      return;
    }
    state.busy = true;
    els.uploadProgress.hidden = false;
    els.uploadProgressText.textContent =
      files.length === 1 ? `Processing “${files[0].name}”…` : `Processing ${files.length} PDFs…`;
    showSkeletons(Math.min(files.length, 4));

    const formData = new FormData();
    for (const file of files) formData.append("files", file);

    try {
      const body = await fetchJson("/api/documents", { method: "POST", body: formData });
      setDocs(body.documents);
      for (const result of body.results) {
        if (!result.ok) {
          toast(result.error.message, "error", result.filename);
        }
      }
      const accepted = body.results.filter((r) => r.ok);
      if (accepted.length) {
        refreshHealth();
      }
    } catch (err) {
      toast(err.message, "error", "Upload failed");
      const refreshed = await fetchJson("/api/documents").catch(() => null);
      if (refreshed) setDocs(refreshed.documents);
    } finally {
      state.busy = false;
      els.uploadProgress.hidden = true;
      renderDocs();
    }
  }

  /* ── chat ─────────────────────────────────────────────────────────── */

  function hideEmptyState() {
    if (els.emptyState && els.emptyState.parentNode) els.emptyState.remove();
    if (els.exampleChips) els.exampleChips.remove(); // suggestions belong to the fresh chat
  }

  function appendUserMessage(text) {
    const wrap = document.createElement("div");
    wrap.className = "msg msg--user";
    const bubble = document.createElement("div");
    bubble.className = "msg__bubble";
    bubble.textContent = text;
    wrap.appendChild(bubble);
    els.threadInner.appendChild(wrap);
    scrollToBottom();
    return wrap;
  }

  function appendAssistantShell() {
    const wrap = document.createElement("div");
    wrap.className = "msg msg--assistant";
    wrap.innerHTML = `
      <div class="msg__card">
        <div class="msg__answer"><div class="typing" aria-label="DocWiz is thinking"><span></span><span></span><span></span></div></div>
      </div>`;
    els.threadInner.appendChild(wrap);
    scrollToBottom();
    return wrap;
  }

  /* Minimal, safe markdown-ish rendering: paragraphs, **bold**, *italic*,
     `code`, and simple bullet/numbered lists. Everything is escaped first. */
  function renderAnswer(container, text) {
    const lines = String(text || "").split("\n");
    const blocks = [];
    let listBuffer = [];
    let listType = null;

    const flushList = () => {
      if (listBuffer.length) {
        blocks.push({ type: listType, items: listBuffer });
        listBuffer = [];
        listType = null;
      }
    };

    for (const rawLine of lines) {
      const line = rawLine.trim();
      if (!line) {
        flushList();
        continue;
      }
      const bullet = line.match(/^[-*]\s+(.*)$/);
      const numbered = line.match(/^\d+[.)]\s+(.*)$/);
      if (bullet) {
        if (listType && listType !== "ul") flushList();
        listType = "ul";
        listBuffer.push(bullet[1]);
        continue;
      }
      if (numbered) {
        if (listType && listType !== "ol") flushList();
        listType = "ol";
        listBuffer.push(numbered[1]);
        continue;
      }
      flushList();
      blocks.push({ type: "p", text: line });
    }
    flushList();

    container.innerHTML = "";
    const generalSplit = String(text || "").includes("General knowledge:");
    for (const block of blocks) {
      let node;
      if (block.type === "ul" || block.type === "ol") {
        node = document.createElement(block.type);
        for (const item of block.items) {
          const li = document.createElement("li");
          li.innerHTML = inlineFormat(item);
          node.appendChild(li);
        }
      } else {
        node = document.createElement("p");
        const isGeneral = block.text.startsWith("General knowledge:");
        node.innerHTML = inlineFormat(block.text);
        if (isGeneral && generalSplit) node.className = "general-knowledge";
      }
      container.appendChild(node);
    }
  }

  function inlineFormat(text) {
    let html = escapeHtml(text);
    html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    html = html.replace(/(^|\s)\*([^*\n]+)\*(?=\s|[.,;:!?]|$)/g, "$1<em>$2</em>");
    html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
    return html;
  }

  function renderSources(card, sources) {
    if (!sources || !sources.length) return;
    const wrap = document.createElement("div");
    wrap.className = "sources";
    wrap.innerHTML = `<p class="sources__label">Sources used</p><div class="sources__list"></div>`;
    const list = wrap.querySelector(".sources__list");

    for (const source of sources) {
      const row = document.createElement("div");
      row.className = "source-row";
      row.innerHTML = `
        <span class="source-row__icon" aria-hidden="true">${PDF_ICON}</span>
        <div class="source-row__body">
          <div class="source-row__head">
            <span class="source-row__name">${escapeHtml(source.filename)}</span>
            <span class="source-row__page">${pageLabel(source)}</span>
          </div>
          ${source.excerpt ? `<p class="source-row__excerpt">“${escapeHtml(source.excerpt)}”</p>` : ""}
        </div>`;
      list.appendChild(row);
    }
    card.appendChild(wrap);
  }

  function appendErrorBanner(message, hint) {
    const wrap = document.createElement("div");
    wrap.className = "msg msg--assistant";
    wrap.innerHTML = `
      <div class="msg__error">
        <span aria-hidden="true">⚠</span>
        <div>${escapeHtml(message)}${hint ? `<br><span style="color:var(--muted-foreground)">${escapeHtml(hint)}</span>` : ""}</div>
      </div>`;
    els.threadInner.appendChild(wrap);
    scrollToBottom();
  }

  async function askQuestion(question) {
    hideEmptyState();
    appendUserMessage(question);
    const shell = appendAssistantShell();
    const answerBox = shell.querySelector(".msg__answer");
    const card = shell.querySelector(".msg__card");

    state.busy = true;
    els.sendBtn.disabled = true;
    try {
      const body = await fetchJson("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
      });
      renderAnswer(answerBox, body.answer);
      renderSources(card, body.sources);
      scrollToBottom();
    } catch (err) {
      shell.remove();
      const hints = {
        api_key_missing: "Add GROQ_API_KEY to your .env file and restart the server.",
        llm_auth_failed: "Verify the key in your .env file, then restart DocWiz.",
        no_documents: "Upload a PDF in the sidebar first.",
        network_error: "Make sure the DocWiz server is still running.",
      };
      appendErrorBanner(err.message, hints[err.code] || null);
    } finally {
      state.busy = false;
      updateSendState();
      els.questionInput.focus();
    }
  }

  function updateSendState() {
    els.sendBtn.disabled = state.busy || !els.questionInput.value.trim();
  }

  /* ── events ───────────────────────────────────────────────────────── */

  els.uploadZone.addEventListener("click", () => els.fileInput.click());
  if (els.composerAdd) {
    // The “+” inside the composer opens the same PDF picker as the sidebar zone.
    els.composerAdd.addEventListener("click", () => els.fileInput.click());
  }
  els.uploadZone.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      els.fileInput.click();
    }
  });
  els.fileInput.addEventListener("change", () => {
    uploadFiles(els.fileInput.files);
    els.fileInput.value = "";
  });

  ["dragenter", "dragover"].forEach((type) =>
    els.uploadZone.addEventListener(type, (event) => {
      event.preventDefault();
      els.uploadZone.classList.add("upload--dragging");
    })
  );
  ["dragleave", "drop"].forEach((type) =>
    els.uploadZone.addEventListener(type, (event) => {
      event.preventDefault();
      els.uploadZone.classList.remove("upload--dragging");
    })
  );
  els.uploadZone.addEventListener("drop", (event) => {
    if (event.dataTransfer && event.dataTransfer.files) uploadFiles(event.dataTransfer.files);
  });

  // Also allow dropping PDFs anywhere on the page.
  document.addEventListener("dragover", (event) => event.preventDefault());
  document.addEventListener("drop", (event) => {
    event.preventDefault();
    const files = Array.from((event.dataTransfer && event.dataTransfer.files) || []).filter((f) =>
      f.name.toLowerCase().endsWith(".pdf")
    );
    if (files.length) uploadFiles(files);
  });

  els.composer.addEventListener("submit", (event) => {
    event.preventDefault();
    const question = els.questionInput.value.trim();
    if (!question || state.busy) return;
    els.questionInput.value = "";
    autosize();
    updateSendState();
    askQuestion(question);
  });

  els.questionInput.addEventListener("input", () => {
    autosize();
    updateSendState();
  });
  els.questionInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      els.composer.requestSubmit();
    }
  });

  function autosize() {
    const input = els.questionInput;
    input.style.height = "auto";
    input.style.height = `${Math.min(input.scrollHeight, 168)}px`;
  }

  els.exampleChips.addEventListener("click", (event) => {
    const chip = event.target.closest(".example-chip");
    if (!chip) return;
    els.questionInput.value = chip.textContent.trim();
    autosize();
    updateSendState();
    els.questionInput.focus();
  });

  els.resetBtn.addEventListener("click", async () => {
    if (!state.docs.length) {
      toast("The library is already empty.", "info");
      return;
    }
    if (!window.confirm("Remove all uploaded documents and clear the index?")) return;
    try {
      await fetchJson("/api/reset", { method: "POST" });
      setDocs([]);
      refreshHealth();
      toast("Library cleared.", "info");
    } catch (err) {
      toast(err.message, "error", "Could not clear the library");
    }
  });

  function toggleSidebar(open) {
    const isOpen = open !== undefined ? open : !els.sidebar.classList.contains("open");
    els.sidebar.classList.toggle("open", isOpen);
    els.scrim.hidden = !isOpen;
    els.sidebarToggle.setAttribute("aria-expanded", String(isOpen));
  }
  els.sidebarToggle.addEventListener("click", () => toggleSidebar());
  els.scrim.addEventListener("click", () => toggleSidebar(false));
  window.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && els.sidebar.classList.contains("open")) toggleSidebar(false);
  });

  /* ── boot ─────────────────────────────────────────────────────────── */

  (async function init() {
    // Time-aware greeting for the fresh-chat state.
    if (els.greetingText) {
      const hour = new Date().getHours();
      els.greetingText.textContent =
        hour < 5 ? "Working late?" :
        hour < 12 ? "Good morning." :
        hour < 18 ? "Good afternoon." :
        "Good evening.";
    }
    autosize();
    updateSendState();
    refreshHealth();
    try {
      const body = await fetchJson("/api/documents");
      setDocs(body.documents);
    } catch (err) {
      setDocs([]);
    }
  })();
})();
