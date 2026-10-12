"use strict";

const state = { catalog: [], summary: {}, work: null, pendingWorkId: null, detail: null, notes: [], reviews: new Map(), passageIndex: 0, contentsOffset: null, tab: "read", anchor: null, editingId: null, requestId: 0, saving: false };
const $ = (id) => document.getElementById(id);
const number = (value) => new Intl.NumberFormat("de-DE").format(Number(value) || 0);
const labels = {
  unreviewed: "Noch nicht geprüft", in_progress: "In Prüfung", reviewed: "Geprüft",
  soft_hyphen: "Unsichtbare Trennzeichen", remove_soft_hyphens: "Unsichtbare Trennzeichen",
  line_breaks: "Unterbrochene Zeilen", unwrap_lines: "Zeilenumbrüche im Fließtext",
  whitespace: "Abstände", normalize_whitespace: "Abstände", unicode: "Unicode-Zeichen",
  hyphenation: "Worttrennungen", dehyphenation: "Worttrennungen", join_hyphenated_words: "Worttrennungen",
  page_numbers: "Seitenzahlen", page_headers: "Seitenköpfe", repeated_headers: "Wiederholte Seitenköpfe",
  verse_line_wraps: "Umbrüche in Versen", paragraph_wraps: "Zeilenumbrüche im Fließtext",
  source_whitespace: "Quellbedingte Zeilenumbrüche und Abstände",
  attested_dehyphenation: "Worttrennungen mit Beleg im Korpus",
  ga040_prose_reflow: "GA 040: Umbrüche in den Prosateilen",
  reviewed_syllable_repair: "Geprüfte wiederkehrende Silbentrennungen",
  reviewed_ocr: "Am Druck geprüfte OCR-Wörter",
  ga040_calendar_stanzas: "GA 040: Wochenverse als Strophen",
  ga014_readability: "GA 014: Dialoge und Regieanweisungen",
  unresolved_hyphenation: "Worttrennung ohne sicheren Beleg",
  duplicate_paragraph: "Wiederholter Absatz",
  suspicious_page_label: "Unplausible Seitenzahl",
  ocr_suspect: "Möglicher OCR-Fehler",
  missing_illustration: "Fehlende Abbildung",
  private_use_glyph: "Sonderzeichen aus der Quellenschrift",
  ocr_source_review: "OCR-Stellen am Original prüfen",
  manuscript_transcription: "Handschriftentranskription prüfen",
  verse_paragraph_review: "Absatzgrenzen in Versen prüfen",
  verse_overrun_review: "Überlange Verszeilen prüfen",
};

function element(tag, className, content) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (content !== undefined && content !== null) node.textContent = String(content);
  return node;
}

async function api(path, options = {}) {
  const response = await fetch(`/api/proofreading${path}`, { headers: { "Content-Type": "application/json" }, ...options });
  const contentType = response.headers.get("content-type") || "";
  const body = contentType.includes("json") ? await response.json() : null;
  if (!response.ok) throw new Error(body?.error || `Die Anfrage konnte nicht gespeichert werden (${response.status}).`);
  return body;
}

function toast(message, error = false) {
  $("toast").textContent = message;
  $("toast").classList.toggle("error", error);
  $("toast").hidden = false;
  window.clearTimeout(toast.timer);
  toast.timer = window.setTimeout(() => { $("toast").hidden = true; }, error ? 7000 : 3500);
}

function setSaving(saving, failed = false) {
  state.saving = saving;
  $("save-indicator").textContent = saving ? "Wird gespeichert …" : failed ? "Speichern fehlgeschlagen" : "Notizen werden lokal gespeichert";
  $("save-indicator").classList.toggle("failed", failed);
  $("save-note").disabled = saving;
}

function isAvailable(work) { return work.available !== false && (work.available || Number(work.passage_count) > 0); }
function workNumber(work) { const value = String(work.ga_number ?? String(work.id).replace(/^ga[-_]?/i, "")); return /^GA\s/i.test(value) ? value : `GA ${value}`; }
function reviewFor(work) { return state.reviews.get(String(work.id)) || work.review_status || "unreviewed"; }
function changedCount(work) { return Number(work.change_count) || 0; }
function flagCount(work) { return Number(work.flag_count) || (Array.isArray(work.flags) ? work.flags.length : 0); }
function ruleLabel(rule) { return labels[rule] || String(rule || "Hinweis").replaceAll("_", " "); }
function excerpt(value) { return typeof value === "string" ? value : value?.text ?? JSON.stringify(value ?? ""); }
function sameSourceTitle(left, right) {
  return typeof left === "string" && typeof right === "string"
    && left.replace(/\s+/gu, " ").trim() === right.replace(/\s+/gu, " ").trim();
}

function applyReviews(reviews) {
  if (Array.isArray(reviews)) {
    for (const review of reviews) state.reviews.set(String(review.work_id ?? review.id), review.status || "unreviewed");
  } else if (reviews && typeof reviews === "object") {
    for (const [id, review] of Object.entries(reviews)) state.reviews.set(String(id), typeof review === "string" ? review : review.status || "unreviewed");
  }
}

function renderCatalog() {
  const search = $("work-search").value.toLocaleLowerCase("de").trim();
  const filter = $("work-filter").value;
  const numberQuery = search.match(/^(?:ga\s*-?\s*)?0*(\d+)([a-z]?(?:[\/-]\d+)?)$/i);
  const requestedId = numberQuery ? `${Number(numberQuery[1])}${numberQuery[2].replaceAll("/", "-")}` : null;
  const works = state.catalog.filter((work) => {
    const workId = String(work.id).replace(/^ga-/, "").replace(/^0+(?=\d)/, "");
    const match = requestedId ? workId === requestedId : !search || `${workNumber(work)} ${work.title || ""}`.toLocaleLowerCase("de").includes(search);
    if (!match) return false;
    if (filter === "changed") return changedCount(work) > 0;
    if (filter === "flagged") return flagCount(work) > 0;
    if (filter === "available") return isAvailable(work);
    if (filter === "unavailable") return !isAvailable(work);
    if (["unreviewed", "in_progress", "reviewed"].includes(filter)) return reviewFor(work) === filter;
    return true;
  });
  $("work-count").textContent = number(state.catalog.length);
  $("list-count").textContent = `${number(works.length)} ${works.length === 1 ? "Band" : "Bände"}${works.length !== state.catalog.length ? ` von ${number(state.catalog.length)}` : ""}`;
  const list = $("work-list");
  list.replaceChildren();
  if (!works.length) list.append(element("p", "loading-message", "Kein Band passt zu dieser Suche."));
  for (const work of works) {
    const selected = String(state.pendingWorkId || state.work?.id) === String(work.id);
    const button = element("button", `work-item${selected ? " selected" : ""}${!isAvailable(work) ? " unavailable" : ""}`);
    button.type = "button";
    button.dataset.id = work.id;
    if (selected) button.setAttribute("aria-current", "page");
    const line = element("div", "work-item-top");
    line.append(element("span", "work-item-number", workNumber(work)));
    const status = reviewFor(work);
    const dot = element("span", `work-review-dot ${status}`);
    dot.title = labels[status] || status;
    dot.setAttribute("aria-label", labels[status] || status);
    line.append(dot);
    button.append(line, element("span", "work-item-title", work.title || "Ohne Titel"));
    const meta = element("span", "work-item-meta");
    if (!isAvailable(work)) meta.append(element("span", "unavailable-tag", "Text nicht verfügbar"));
    else {
      meta.append(element("span", "", `${number(work.passage_count)} Abschnitte`));
      if (changedCount(work)) meta.append(element("span", "change-tag", `${number(changedCount(work))} Korrekturen`));
      if (flagCount(work)) meta.append(element("span", "flag-tag", `${number(flagCount(work))} Hinweise`));
    }
    button.append(meta);
    button.addEventListener("click", () => loadWork(String(work.id)));
    list.append(button);
  }
  const summary = $("catalog-summary");
  summary.replaceChildren();
  const values = [
    [state.catalog.filter(isAvailable).length, "mit Text"],
    [state.catalog.filter((w) => changedCount(w) > 0).length, "bearbeitet"],
    [state.catalog.filter((w) => reviewFor(w) === "reviewed").length, "geprüft"],
  ];
  for (const [value, label] of values) { const cell = element("div"); cell.append(element("strong", "", number(value)), element("span", "", label)); summary.append(cell); }
  const selected = list.querySelector(".selected");
  if (selected) {
    const itemRect = selected.getBoundingClientRect();
    const listRect = list.getBoundingClientRect();
    if (window.matchMedia("(max-width: 700px)").matches) {
      if (itemRect.left < listRect.left || itemRect.right > listRect.right) list.scrollLeft += itemRect.left - listRect.left - 18;
    } else if (itemRect.top < listRect.top || itemRect.bottom > listRect.bottom) list.scrollTop += itemRect.top - listRect.top - 10;
  }
}

async function initialize() {
  try {
    const [catalogResult, notesResult] = await Promise.allSettled([api("/catalog"), api("/notes")]);
    if (catalogResult.status !== "fulfilled") throw catalogResult.reason;
    const catalog = catalogResult.value;
    state.catalog = catalog.works || [];
    state.summary = catalog.summary || {};
    if (notesResult.status === "fulfilled") applyReviews(notesResult.value?.reviews);
    if (catalog.generated_at) {
      const date = new Date(catalog.generated_at);
      $("report-date").textContent = `Prüflauf ${Number.isNaN(date.getTime()) ? catalog.generated_at : date.toLocaleDateString("de-DE")}`;
    } else $("report-date").textContent = "Prüfbericht verfügbar";
    renderCatalog();
    const params = new URLSearchParams(window.location.search);
    const requested = params.get("ga") || params.get("work");
    const initial = state.catalog.find((work) => String(work.id) === requested || String(work.ga_number) === requested || (requested && String(work.ga_number).replace(/^GA\s*0*/i, "") === requested))
      || state.catalog.find((work) => /wahrspruch/i.test(work.title || "")) || state.catalog.find(isAvailable) || state.catalog[0];
    if (initial) await loadWork(String(initial.id), params.get("passage"), params.get("offset"));
  } catch (error) {
    $("work-list").replaceChildren(element("p", "loading-message", "Der Katalog konnte nicht geladen werden."));
    showError(`Die Korrekturwerkstatt ist noch nicht erreichbar. ${error.message}`);
  }
}

function showError(message) { $("main-error").textContent = message; $("main-error").hidden = false; }

async function loadWork(id, passageId, startOffset = null) {
  if (state.saving) return;
  saveDraft();
  const requestId = ++state.requestId;
  $("main-error").hidden = true;
  const next = state.catalog.find((work) => String(work.id) === id);
  state.pendingWorkId = id;
  renderCatalog();
  $("reading-main").classList.add("is-loading");
  $("notes-active").inert = true;
  try {
    const [detail, notes] = await Promise.all([api(`/works/${encodeURIComponent(id)}`), api(`/notes?work_id=${encodeURIComponent(id)}`)]);
    if (requestId !== state.requestId) return;
    state.detail = detail;
    state.work = { ...next, ...(detail.work || {}) };
    state.pendingWorkId = null;
    state.notes = notes.notes || [];
    applyReviews(notes.reviews);
    state.passageIndex = Math.max(0, (detail.passages || []).findIndex((passage) => String(passage.id) === String(passageId)));
    const offset = startOffset === null ? null : Number(startOffset);
    state.contentsOffset = offset !== null && validContentsOffset(currentPassage(), offset) ? offset : null;
    resetComposer(false);
    $("welcome").hidden = true;
    $("work-view").hidden = false;
    $("notes-inactive").hidden = true;
    $("notes-active").hidden = false;
    $("mobile-notes").hidden = false;
    renderWork();
    restoreDraft();
    setTab("read");
    renderNotes();
    renderCatalog();
    updateURL();
    if (state.contentsOffset !== null) scrollToContentsHeading();
  } catch (error) { if (requestId === state.requestId) { $("work-view").hidden = true; $("notes-active").hidden = true; $("notes-inactive").hidden = false; showError(error.message); } }
  finally { if (requestId === state.requestId) { state.pendingWorkId = null; $("reading-main").classList.remove("is-loading"); $("notes-active").inert = false; renderCatalog(); } }
}

function renderWork() {
  const work = state.work;
  const passages = state.detail.passages || [];
  $("work-number").textContent = workNumber(work);
  $("work-title").textContent = work.title || "Ohne Titel";
  $("source-status").textContent = isAvailable(work) ? "Text verfügbar" : "Quelle fehlt";
  $("source-status").classList.toggle("missing", !isAvailable(work));
  $("work-description").textContent = `${number(passages.length)} Abschnitte · ${number(work.character_count)} Zeichen`;
  $("review-status").value = reviewFor(work);
  $("review-status").querySelector('option[value="reviewed"]').disabled = !isAvailable(work);
  $("work-stats").replaceChildren();
  const stats = [
    [changedCount(work), "automatische Korrekturen", "changes"],
    [flagCount(work), "Prüfhinweise", "checks"],
    [state.notes.filter((note) => !resolved(note)).length, "offene Notizen", "notes"],
  ];
  for (const [value, label, target] of stats) {
    const stat = element("button", "work-stat"); stat.type = "button";
    stat.append(element("strong", "", number(value)), element("span", "", label));
    stat.addEventListener("click", () => { if (target === "notes") { if (window.matchMedia("(max-width: 1000px)").matches) toggleNotes(true); else $("note-body").focus(); } else setTab(target); });
    $("work-stats").append(stat);
  }
  $("passage-badge").textContent = number(passages.length);
  $("changes-badge").textContent = number(changedCount(work));
  $("flags-badge").textContent = number(flagCount(work));
  const select = $("passage-select"); select.replaceChildren();
  const contents = tableOfContents();
  // The calendar's existing date aliases and poem labels are built from its
  // validated reading sections; keep that navigation alongside source TOCs.
  if (contents.length && work.id !== "ga-040") renderSourceContents(select, contents, passages);
  else renderPassageContents(select, passages);
  select.disabled = !passages.length;
  renderPassage();
  renderChanges();
  renderChecks();
}

function renderSourceContents(select, contents, passages) {
  const indices = new Map(passages.map((passage, index) => [passage.id, index]));
  let group = null;
  for (const entry of contents) {
    // Pure source parts share their first child's target. A label preserves the
    // original hierarchy without adding a duplicate selectable destination.
    const firstChild = contents.find((candidate) => candidate.parent_id === entry.id);
    const isGroup = firstChild && firstChild.passage_id === entry.passage_id && firstChild.start_offset === entry.start_offset;
    if (group && entry.level <= group.level) group = null;
    if (isGroup) {
      const node = element("optgroup");
      node.label = `${"\u2003".repeat(entry.level - 1)}${entry.title}`;
      select.append(node);
      group = { node, level: entry.level };
      continue;
    }
    const index = indices.get(entry.passage_id);
    const option = element("option", "", `${"\u2003".repeat(entry.level - 1)}${entry.title}`);
    option.value = entry.start_offset === 0 ? String(index) : `${index}:${entry.start_offset}`;
    option.dataset.contentsId = entry.id;
    option.dataset.level = entry.level;
    if (entry.start_offset > 0) option.dataset.heading = "heading";
    (group?.node || select).append(option);
  }
}

function renderPassageContents(select, passages) {
  let group = null;
  let parent = select;
  passages.forEach((passage, index) => {
    const title = passage.metadata?.group_title || null;
    if (title !== group) {
      group = title;
      parent = title ? element("optgroup") : select;
      if (title) { parent.label = title; select.append(parent); }
    }
    const sections = readingSections(passage);
    const outline = sections.length ? sections : [{ title: passage.title || "Abschnitt ohne Überschrift", start_offset: 0, end_offset: passage.text.length }];
    const headings = readingBlocks(passage).filter((item) => item.kind === "heading");
    const calendar = /Seelenkalender/iu.test(title || "");
    outline.forEach((section, sectionIndex) => {
      const option = element("option", "", section.title);
      option.value = section.start_offset === 0 ? String(index) : `${index}:${section.start_offset}`;
      if (sections.length) option.dataset.section = section.label_kind;
      parent.append(option);
      let week = "";
      let weekOffset = null;
      const sectionHeadings = headings.filter((block) => block.start_offset >= section.start_offset && block.start_offset < section.end_offset);
      sectionHeadings.forEach((block, headingIndex) => {
        const heading = passage.text.slice(block.start_offset, block.end_offset);
        if (block.start_offset === section.start_offset && sameSourceTitle(heading, section.title)) return;
        const next = sectionHeadings[headingIndex + 1];
        if (calendar && block.level === 2 && next && /^\d+$/.test(passage.text.slice(next.start_offset, next.end_offset))) {
          week = heading;
          weekOffset = block.start_offset;
          return;
        }
        const calendarNumber = calendar && /^\d+$/.test(heading);
        if (!calendarNumber) { week = ""; weekOffset = null; }
        const label = calendarNumber ? `Spruch ${heading}${week ? ` · ${week}` : ""}` : heading;
        const entry = element("option", "", `${"\u2003".repeat(calendarNumber ? 2 : block.level ?? 2)}${label}`);
        entry.value = `${index}:${block.start_offset}`;
        entry.dataset.heading = calendarNumber ? "calendar-number" : "heading";
        if (calendarNumber && weekOffset !== null) entry.dataset.weekOffset = weekOffset;
        parent.append(entry);
      });
    });
  });
}

function currentPassage() { return state.detail?.passages?.[state.passageIndex]; }

function tableOfContents() {
  const entries = state.detail?.table_of_contents;
  if (!Array.isArray(entries) || !entries.length) return [];
  const passages = new Map((state.detail.passages || []).map((passage) => [passage.id, passage]));
  const seen = new Map();
  for (const entry of entries) {
    const passage = passages.get(entry?.passage_id);
    const parent = entry?.parent_id == null ? null : seen.get(entry.parent_id);
    if (!entry || typeof entry.id !== "string" || !entry.id.trim() || seen.has(entry.id)
      || typeof entry.title !== "string" || !entry.title.trim()
      || !Number.isInteger(entry.level) || entry.level < 1 || entry.level > 6
      || !passage || !validTextOffset(passage.text || "", entry.start_offset)
      || (entry.parent_id != null && (!parent || parent.level >= entry.level))) return [];
    seen.set(entry.id, entry);
  }
  return entries;
}

function validTextOffset(text, offset) {
  if (!Number.isInteger(offset) || offset < 0 || offset > text.length) return false;
  // JavaScript and native readers count UTF-16; never split a surrogate pair.
  return offset === 0 || offset === text.length || !(text.charCodeAt(offset - 1) >= 0xD800 && text.charCodeAt(offset - 1) <= 0xDBFF && text.charCodeAt(offset) >= 0xDC00 && text.charCodeAt(offset) <= 0xDFFF);
}

function readingBlocks(passage) {
  const blocks = passage?.metadata?.reading_blocks;
  if (!Array.isArray(blocks) || !blocks.length) return [];
  const text = passage.text || "";
  let end = 0;
  for (const block of blocks) {
    if (!block || !["heading", "verse", "prose", "attribution", "note"].includes(block.kind)
      || !validTextOffset(text, block.start_offset) || !validTextOffset(text, block.end_offset)
      || block.start_offset < end || block.end_offset <= block.start_offset
      || text.slice(end, block.start_offset).trim()
      || (block.level != null && (!Number.isInteger(block.level) || block.level < 1 || block.level > 6))
      || (block.poem_start != null && typeof block.poem_start !== "boolean")) return [];
    end = block.end_offset;
  }
  return text.slice(end).trim() ? [] : blocks;
}

function readingSections(passage) {
  const sections = passage?.metadata?.reading_sections;
  if (!Array.isArray(sections) || !sections.length) return [];
  const text = passage.text || "";
  const blocks = readingBlocks(passage);
  const ends = new Set(blocks.map((block) => block.end_offset));
  const ids = new Set();
  let end = 0;
  for (const section of sections) {
    const first = blocks.find((block) => block.start_offset === section?.start_offset);
    if (!section || typeof section.id !== "string" || !section.id || ids.has(section.id)
      || typeof section.title !== "string" || !section.title.trim()
      || !["source_title", "incipit"].includes(section.label_kind)
      || !first || !ends.has(section.end_offset) || section.start_offset < end || section.end_offset <= section.start_offset
      || text.slice(end, section.start_offset).trim()) return [];
    const firstLine = text.slice(first.start_offset, first.end_offset).split("\n")[0];
    if (section.label_kind === "incipit" ? first.kind !== "verse" || section.title !== firstLine
      : !(section.start_offset === 0 && section.title === passage.title || first.kind === "heading" && section.title === firstLine)) return [];
    ids.add(section.id); end = section.end_offset;
  }
  return text.slice(end).trim() ? [] : sections;
}

function validContentsOffset(passage, offset) {
  return tableOfContents().some((entry) => entry.passage_id === passage?.id && entry.start_offset === offset)
    || readingBlocks(passage).some((block) => block.kind === "heading" && block.start_offset === offset)
    || readingSections(passage).some((section) => section.start_offset === offset);
}

function sourceReferences(passage) {
  const text = passage.text || "";
  const notes = Array.isArray(passage.metadata?.annotations) ? passage.metadata.annotations : [];
  const references = [];
  notes.forEach((note, index) => {
    if (!note || typeof note.marker !== "string" || !note.marker || typeof note.text !== "string") return;
    if (note.start_offset != null || note.end_offset != null) {
      if (validTextOffset(text, note.start_offset) && validTextOffset(text, note.end_offset)
        && note.end_offset > note.start_offset && text.slice(note.start_offset, note.end_offset) === note.marker) {
        references.push({ start: note.start_offset, end: note.end_offset, index, note });
      }
    } else {
      let start = text.indexOf(note.marker);
      while (start !== -1) {
        references.push({ start, end: start + note.marker.length, index, note });
        start = text.indexOf(note.marker, start + note.marker.length);
      }
    }
  });
  references.sort((a, b) => a.start - b.start);
  let end = 0;
  return references.filter((reference) => {
    if (reference.start < end) return false;
    end = reference.end; return true;
  });
}

function renderReadingText(passage) {
  const root = $("passage-text");
  root.replaceChildren();
  const text = passage?.text || "";
  const references = passage ? sourceReferences(passage) : [];
  const append = (node, start, end) => {
    let offset = start;
    for (const reference of references.filter((item) => item.start >= start && item.end <= end)) {
      node.append(document.createTextNode(text.slice(offset, reference.start)));
      const link = element("a", "source-note-reference", text.slice(reference.start, reference.end));
      link.href = `#source-annotation-${reference.index + 1}`;
      link.id = `source-reference-${reference.index + 1}-${reference.start}`;
      link.setAttribute("aria-label", `Anmerkung ${reference.note.marker}`);
      link.addEventListener("click", () => {
        const notes = $("source-annotations"); if (notes) notes.open = true;
      });
      node.append(link); offset = reference.end;
    }
    node.append(document.createTextNode(text.slice(offset, end)));
  };
  const blocks = passage ? readingBlocks(passage) : [];
  const sections = passage ? readingSections(passage) : [];
  let offset = 0;
  for (const block of blocks) {
    append(root, offset, block.start_offset);
    const section = sections.find((item) => item.start_offset === block.start_offset);
    const sectionTitle = section?.label_kind === "source_title" && block.kind === "heading" && section.title === text.slice(block.start_offset, block.end_offset);
    const node = element(block.kind === "heading" ? sectionTitle ? "h3" : `h${Math.min(6, (block.level ?? 2) + 2)}` : "span", `reading-block reading-${block.kind}`);
    if (block.kind === "heading") {
      node.dataset.level = block.level ?? 2;
      node.dataset.startOffset = block.start_offset;
      node.id = `reading-heading-${block.start_offset}`;
    }
    if (block.kind === "verse" && block.poem_start === true) node.dataset.poemStart = "true";
    if (section && section.start_offset > 0) {
      node.classList.add("reading-unit-start");
      node.dataset.sectionStartOffset = section.start_offset;
      node.dataset.labelKind = section.label_kind;
    }
    if (section?.label_kind === "incipit") {
      const firstLineEnd = block.start_offset + section.title.length;
      const label = element("span", "reading-incipit");
      append(label, block.start_offset, firstLineEnd); node.append(label);
      append(node, firstLineEnd, block.end_offset);
    } else append(node, block.start_offset, block.end_offset);
    root.append(node); offset = block.end_offset;
  }
  append(root, offset, text.length);
  const notesRoot = $("source-annotations");
  notesRoot.replaceChildren();
  const notes = Array.isArray(passage?.metadata?.annotations) ? passage.metadata.annotations.filter((note) => note && typeof note.text === "string") : [];
  notesRoot.hidden = !notes.length; notesRoot.open = false;
  if (notes.length) {
    notesRoot.append(element("summary", "", "Anmerkungen der Ausgabe"));
    const list = element("ol");
    // Use the original array index so invalid notes cannot shift reference IDs.
    passage.metadata.annotations.forEach((note, index) => {
      if (!note || typeof note.text !== "string") return;
      const item = element("li"); item.id = `source-annotation-${index + 1}`; item.tabIndex = -1;
      item.append(element("strong", "", note.marker || String(index + 1)), element("div", "source-note-text", note.text));
      const reference = references.find((entry) => entry.index === index);
      if (reference) {
        const back = element("a", "source-note-back", "Zur Textstelle ↑");
        back.href = `#source-reference-${index + 1}-${reference.start}`; item.append(back);
      }
      list.append(item);
    });
    notesRoot.append(list);
  }
}

function renderPassage() {
  const passage = currentPassage();
  const length = state.detail?.passages?.length || 0;
  const select = $("passage-select");
  const target = state.contentsOffset === null || state.contentsOffset === 0 ? String(state.passageIndex) : `${state.passageIndex}:${state.contentsOffset}`;
  const option = [...select.options].find((entry) => entry.value === target)
    || [...select.options].find((entry) => entry.value.startsWith(`${state.passageIndex}:`) && entry.dataset.weekOffset === String(state.contentsOffset))
    || [...select.options].filter((entry) => Number(entry.value.split(":")[0]) < state.passageIndex).at(-1);
  const selectedContents = tableOfContents().find((entry) => entry.id === option?.dataset.contentsId);
  const displayTitle = selectedContents?.source_role === "table_of_contents" ? selectedContents.title : passage?.title;
  select.value = option?.value ?? String(state.passageIndex);
  $("passage-position").textContent = length ? `${state.passageIndex + 1} / ${number(length)}` : "0 / 0";
  $("previous-passage").disabled = state.passageIndex <= 0;
  $("next-passage").disabled = !length || state.passageIndex >= length - 1;
  $("next-passage-bottom").disabled = !length || state.passageIndex >= length - 1;
  $("passage-page").textContent = passage?.ga_page ? `${workNumber(state.work)} · ${/^S\.?\s/.test(String(passage.ga_page)) ? passage.ga_page : `Seite ${passage.ga_page}`}` : workNumber(state.work);
  $("passage-title").textContent = displayTitle || (length ? `Abschnitt ${state.passageIndex + 1}` : "Text nicht verfügbar");
  const firstBlock = readingBlocks(passage)[0];
  const firstHeading = firstBlock?.kind === "heading" && firstBlock.start_offset === 0
    ? passage.text.slice(firstBlock.start_offset, firstBlock.end_offset) : null;
  $("passage-title").hidden = Boolean(typeof passage?.metadata?.continuation_of === "string" && passage.metadata.continuation_of.trim())
    || sameSourceTitle(firstHeading, displayTitle);
  const sourceGroup = typeof passage?.metadata?.group_title === "string" ? passage.metadata.group_title : "";
  $("passage-group").textContent = sourceGroup;
  $("passage-group").hidden = !sourceGroup.trim() || sameSourceTitle(sourceGroup, displayTitle) || sameSourceTitle(sourceGroup, firstHeading);
  const dateline = typeof passage?.metadata?.source_dateline === "string" ? passage.metadata.source_dateline : "";
  $("passage-dateline").textContent = dateline;
  $("passage-dateline").hidden = !dateline.trim();
  $("reading-paper").classList.toggle("has-reading-sections", readingSections(passage).length > 0);
  renderReadingText(passage);
  $("passage-text").dataset.passageId = passage?.id || "";
  $("empty-text").hidden = Boolean(passage?.text);
  $("empty-text").textContent = "Für diesen Band liegt noch kein lesbarer Text vor. Der Prüfbericht dokumentiert den Stand der Quelle. Du kannst trotzdem eine Notiz zum Band hinterlegen.";
  if (state.editingId === null && !$("note-body").value.trim()) { state.anchor = null; renderAnchor(); }
  renderNotes();
}

function selectPassage(index, scroll = true, startOffset = null) {
  const passages = state.detail?.passages || [];
  if (!Number.isInteger(index) || index < 0 || index >= passages.length) return;
  state.passageIndex = index;
  state.contentsOffset = startOffset !== null && validContentsOffset(passages[index], startOffset) ? startOffset : null;
  renderPassage();
  updateURL();
  if (state.contentsOffset !== null) scrollToContentsHeading();
  else if (scroll) $("panel-read").scrollIntoView({ behavior: "smooth", block: "start" });
}

function scrollToContentsHeading() {
  (document.getElementById(`reading-heading-${state.contentsOffset}`)
    || document.querySelector(`[data-section-start-offset="${state.contentsOffset}"]`)
    || (state.contentsOffset === 0 ? $("passage-text") : null))?.scrollIntoView({ behavior: "instant", block: "start" });
}

function updateURL() {
  const url = new URL(window.location.href);
  url.searchParams.set("ga", state.work.id);
  const passage = currentPassage();
  if (passage) url.searchParams.set("passage", passage.id); else url.searchParams.delete("passage");
  if (state.contentsOffset !== null) url.searchParams.set("offset", state.contentsOffset); else url.searchParams.delete("offset");
  window.history.replaceState({}, "", url);
}

function setTab(name, focus = false) {
  state.tab = name;
  for (const tab of document.querySelectorAll(".tab")) {
    const active = tab.dataset.tab === name;
    tab.classList.toggle("active", active);
    tab.setAttribute("aria-selected", String(active));
    tab.tabIndex = active ? 0 : -1;
    $(`panel-${tab.dataset.tab}`).hidden = !active;
    if (active && focus) tab.focus();
  }
}

function reportHeading(container, eyebrow, title, text) {
  const header = element("header", "report-heading");
  header.append(element("p", "eyebrow", eyebrow), element("h3", "", title), element("p", "", text));
  container.append(header);
}

function passageLink(passageId) {
  if (!passageId) return null;
  const index = (state.detail.passages || []).findIndex((p) => String(p.id) === String(passageId));
  if (index < 0) return null;
  const link = element("button", "passage-link", `Abschnitt ${index + 1} lesen ↗`);
  link.type = "button";
  link.addEventListener("click", () => { selectPassage(index, false); setTab("read"); $("panel-read").scrollIntoView({ behavior: "smooth", block: "start" }); });
  return link;
}

function comparisonCard(sample, index) {
  const card = element("article", "comparison-card");
  const header = element("header");
  const title = sample.label || (sample.rule ? ruleLabel(sample.rule) : sample.title || `Stichprobe ${index + 1}`);
  header.append(element("h4", "", title));
  if (sample.count) header.append(element("span", "small-badge", `${number(sample.count)} Änderungen`));
  card.append(header);
  const link = passageLink(sample.passage_id); if (link) card.append(link);
  const comparison = element("div", "comparison");
  for (const [key, label, fallback] of [["before_excerpt", "Vorher", "before"], ["after_excerpt", "Nachher", "after"]]) {
    const column = element("div", `comparison-column ${fallback}`);
    column.append(element("p", "comparison-label", label), element("pre", "", excerpt(sample[key] ?? sample[fallback])));
    comparison.append(column);
  }
  card.append(comparison);
  if (sample.description || sample.reason) card.append(element("p", "card-description", sample.description || sample.reason));
  if (sample.newlines_before !== undefined) card.append(element("p", "card-description", `Zeilenumbrüche: ${number(sample.newlines_before)} → ${number(sample.newlines_after)}`));
  if (sample.replacements?.length) {
    const details = element("details", "replacement-details");
    const corpusEvidence = sample.replacements.some((replacement) => replacement.attested_word_count !== undefined || replacement.attested_work_count !== undefined);
    details.append(element("summary", "", `${number(sample.replacements.length)} ${corpusEvidence ? "Wortverbindungen mit Korpusbelegen" : "geprüfte Wortkorrekturen"}`));
    const tableWrap = element("div", "replacement-table-wrap");
    const table = element("table", "replacement-table");
    const head = element("thead"); const headings = element("tr");
    for (const label of ["Ausgangsform", "Korrigiert", "Ersetzt", ...(corpusEvidence ? ["Korpusbelege", "Bände"] : [])]) headings.append(element("th", "", label));
    head.append(headings); table.append(head);
    const body = element("tbody");
    for (const replacement of sample.replacements) {
      const row = element("tr");
      for (const value of [replacement.split ?? replacement.original, replacement.word, number(replacement.count), ...(corpusEvidence ? [number(replacement.attested_word_count), number(replacement.attested_work_count)] : [])]) row.append(element("td", "", value));
      body.append(row);
    }
    table.append(body); tableWrap.append(table); details.append(tableWrap);
    if (corpusEvidence) details.append(element("p", "card-description", "Die verbundene Form ist an anderen Stellen im Korpus belegt. Die ursprüngliche Trennung bleibt im Änderungsprotokoll nachvollziehbar."));
    card.append(details);
  }
  if (sample.evidence?.length) {
    const sources = element("div", "change-evidence"); sources.append(element("p", "comparison-label", "Geprüfte Druckquellen"));
    const list = element("ul");
    for (const evidence of sample.evidence) {
      const item = element("li");
      let url;
      try { url = new URL(evidence.url); } catch {}
      if (url && ["http:", "https:"].includes(url.protocol)) {
        const link = element("a", "", evidence.title || "Druckquelle öffnen"); link.href = url.href; link.target = "_blank"; link.rel = "noopener noreferrer"; item.append(link);
      } else item.textContent = evidence.title || "Druckquelle";
      list.append(item);
    }
    sources.append(list); card.append(sources);
  }
  return card;
}

function sampleCard(sample, index) {
  if (sample.before_excerpt !== undefined || sample.before !== undefined) return comparisonCard(sample, index);
  const card = element("article", "sample-card");
  const header = element("header");
  header.append(element("h4", "", sample.position || `Stichprobe ${index + 1}`), element("span", "small-badge", "Automatisch geprüft"));
  card.append(header, element("p", "sample-title", sample.title));
  const link = passageLink(sample.passage_id); if (link) card.append(link);
  card.append(element("pre", "sample-excerpt", excerpt(sample.excerpt ?? sample.text)));
  return card;
}

function paginatedCards(container, items, createCard, label) {
  const wrapper = element("div", "report-cards");
  const more = element("button", "button secondary show-more");
  more.type = "button";
  let shown = 0;
  function appendNext() {
    const end = Math.min(shown + 24, items.length);
    while (shown < end) { wrapper.append(createCard(items[shown], shown)); shown++; }
    more.textContent = `Weitere ${Math.min(24, items.length - shown)} ${label} anzeigen · ${number(shown)} / ${number(items.length)}`;
    more.hidden = shown === items.length;
  }
  more.addEventListener("click", appendNext);
  container.append(wrapper, more);
  appendNext();
}

function renderChanges() {
  const panel = $("panel-changes"); panel.replaceChildren();
  const changes = state.detail.changes || [];
  const samples = state.work.samples || state.detail.samples || [];
  reportHeading(panel, "Dokumentierte Bearbeitung", "Was wurde in diesem Band geändert?", "Der Bereinigungslauf protokolliert wiederkehrende Fehler und zeigt die Eingriffe an konkreten Textstellen. Die Umbrüche in den Stichproben bleiben sichtbar.");
  const ruleCounts = state.work.changes_by_rule || {};
  if (Object.keys(ruleCounts).length) {
    const list = element("div", "rule-summary");
    for (const [rule, value] of Object.entries(ruleCounts)) {
      const count = typeof value === "object" ? value.count : value;
      const row = element("div"); row.append(element("span", "", ruleLabel(rule)), element("strong", "", number(count))); list.append(row);
    }
    panel.append(list);
  }
  if (!changes.length && !samples.length) {
    panel.append(element("div", "empty-report", isAvailable(state.work) ? "In diesem Band hat der automatische Lauf keine sicheren Korrekturen vorgenommen. Auffällige Stellen findest du im Prüfbericht." : "Ohne verfügbare Textquelle konnten keine Korrekturen vorgenommen werden."));
    return;
  }
  if (samples.length) {
    panel.append(element("h4", "section-title", "Stichproben: Anfang, Mitte und Ende"));
    samples.forEach((sample, index) => panel.append(sampleCard(sample, index)));
  }
  if (changes.length) {
    panel.append(element("h4", "section-title", `${number(changes.length)} dokumentierte Textstellen`));
    paginatedCards(panel, changes, comparisonCard, "Textstellen");
  }
}

function renderChecks() {
  const panel = $("panel-checks"); panel.replaceChildren();
  reportHeading(panel, "Prüfbericht je GA", "Wo lohnt sich ein genauer Blick?", "Prüfhinweise zeigen Muster, die eine redaktionelle Entscheidung brauchen. Ein Hinweis ist noch keine bestätigte fehlerhafte Stelle. Halte notwendige Änderungen in den Notizen fest.");
  const source = state.work.source_summary || state.work.source;
  if (source) {
    const box = element("div", "source-report"); box.append(element("h4", "", "Textquelle & Bearbeitungsstand"));
    if (typeof source === "string") box.append(element("p", "", source));
    else {
      const dl = element("dl");
      for (const [key, value] of Object.entries(source)) {
        if (value === null || value === undefined) continue;
        dl.append(element("dt", "", ruleLabel(key)), element("dd", "", typeof value === "object" ? JSON.stringify(value) : String(value)));
      }
      box.append(dl);
    }
    panel.append(box);
  }
  const checks = state.work.checks || state.detail.checks;
  if (checks) {
    const box = element("div", "checks-box"); box.append(element("h4", "", "Automatische Kontrolle"));
    const list = element("ul");
    if (Array.isArray(checks)) {
      for (const check of checks) list.append(element("li", "", typeof check === "string" ? check : check.message || check.description || `${ruleLabel(check.rule || check.name)}: ${check.status || JSON.stringify(check)}`));
    } else {
      for (const [key, value] of Object.entries(checks)) list.append(element("li", "", `${ruleLabel(key)}: ${typeof value === "boolean" ? value ? "bestanden" : "auffällig" : typeof value === "object" ? JSON.stringify(value) : value}`));
    }
    box.append(list); panel.append(box);
  }
  const flags = state.detail.flags || state.work.flags || [];
  if (!flags.length) panel.append(element("div", "empty-report good", isAvailable(state.work) ? "Der automatische Prüflauf hat für diesen Band keine offenen Muster gemeldet. Eine vollständige Prüfung durch Lesen steht dir weiterhin offen." : "Der Text fehlt. Der Band bleibt im Katalog dokumentiert und kann nach Ergänzung der Quelle geprüft werden."));
  else {
    panel.append(element("h4", "section-title", `${number(flags.length)} dokumentierte Prüfhinweise`));
    paginatedCards(panel, flags, (flag) => {
      const card = element("article", "flag-card");
      const header = element("header"); header.append(element("h4", "", flag.label || ruleLabel(flag.rule || flag.type || flag.name)));
      if (flag.count) header.append(element("span", "small-badge warning", `${number(flag.count)} Treffer`));
      card.append(header);
      if (flag.message || flag.description || flag.reason) card.append(element("p", "", flag.message || flag.description || flag.reason));
      const link = passageLink(flag.passage_id); if (link) card.append(link);
      if (flag.excerpt || flag.text) card.append(element("pre", "flag-excerpt", excerpt(flag.excerpt || flag.text)));
      return card;
    }, "Prüfhinweise");
  }
}

function captureSelection() {
  if (!state.work || state.tab !== "read" || state.editingId !== null) return;
  const selection = window.getSelection();
  if (!selection || selection.isCollapsed || !selection.rangeCount) return;
  const range = selection.getRangeAt(0);
  const text = $("passage-text");
  if (!text.contains(range.startContainer) || !text.contains(range.endContainer)) return;
  const quote = range.toString();
  if (!quote.trim()) return;
  const before = range.cloneRange(); before.selectNodeContents(text); before.setEnd(range.startContainer, range.startOffset);
  const start = before.toString().length;
  state.anchor = { passage_id: currentPassage().id, checksum: currentPassage().checksum ?? null, quote, start_offset: start, end_offset: start + quote.length };
  renderAnchor();
  saveDraft();
}

function renderAnchor() {
  const anchor = state.anchor;
  $("quote-container").hidden = !anchor?.quote;
  $("selection-hint").hidden = Boolean(anchor?.quote);
  $("quote-text").textContent = anchor?.quote || "";
  $("clear-quote").hidden = state.editingId !== null;
  $("mobile-notes-label").textContent = anchor?.quote ? "Markierung notieren" : "Notizen öffnen";
  const index = (state.detail?.passages || []).findIndex((p) => String(p.id) === String(anchor?.passage_id));
  $("quote-context").textContent = index >= 0 ? `Textstelle · Abschnitt ${index + 1}` : "Textstelle";
}

function resetComposer(clearDraft = true) {
  state.anchor = null;
  state.editingId = null;
  $("note-body").value = "";
  $("note-resolved").checked = false;
  $("composer-title").textContent = "Neue Notiz";
  $("save-note").textContent = "Notiz speichern";
  $("cancel-edit").hidden = true;
  renderAnchor();
  if (clearDraft && state.work) { try { localStorage.removeItem(`ga-proofreading-draft-${state.work.id}`); } catch {} }
}

function saveDraft() {
  if (!state.work) return;
  const draft = { body: $("note-body").value, anchor: state.anchor, resolved: $("note-resolved").checked, editingId: state.editingId };
  try {
    if (draft.body || draft.anchor) localStorage.setItem(`ga-proofreading-draft-${state.work.id}`, JSON.stringify(draft));
    else localStorage.removeItem(`ga-proofreading-draft-${state.work.id}`);
  } catch {}
}

function restoreDraft() {
  try {
    const draft = JSON.parse(localStorage.getItem(`ga-proofreading-draft-${state.work.id}`) || "null");
    if (!draft) return;
    if (draft.editingId !== null && draft.editingId !== undefined && state.notes.some((note) => String(note.id) === String(draft.editingId))) {
      state.editingId = draft.editingId;
      $("composer-title").textContent = "Notiz bearbeiten";
      $("save-note").textContent = "Änderung speichern";
      $("cancel-edit").hidden = false;
    }
    state.anchor = draft.anchor || null;
    $("note-body").value = draft.body || "";
    $("note-resolved").checked = Boolean(draft.resolved);
    renderAnchor();
  } catch {}
}

function resolved(note) { return note.status === "resolved" || note.status === "done" || note.resolved === true; }
function noteDate(note) {
  const value = note.updated_at || note.created_at;
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit", year: "numeric" });
}

function renderNotes() {
  const filter = $("notes-filter").value;
  const notes = state.notes.filter((note) => filter === "all" || (filter === "open" && !resolved(note)) || (filter === "resolved" && resolved(note)) || (filter === "passage" && String(note.passage_id) === String(currentPassage()?.id)));
  $("notes-count").textContent = number(state.notes.length);
  $("mobile-notes-count").textContent = number(state.notes.length);
  $("notes-filter-count").textContent = number(notes.length);
  const list = $("notes-list"); list.replaceChildren();
  if (!notes.length) {
    const empty = element("div", "notes-empty");
    empty.append(element("span", "", "✎"), element("p", "", state.notes.length ? "Keine Notizen in dieser Ansicht." : "Deine erste Anmerkung beginnt mit einer Textstelle oder einer Idee."));
    list.append(empty); return;
  }
  for (const note of [...notes].sort((a, b) => String(b.created_at || b.id).localeCompare(String(a.created_at || a.id)))) {
    const card = element("article", `note-card${resolved(note) ? " resolved" : ""}`);
    const top = element("div", "note-top");
    top.append(element("span", `note-state ${resolved(note) ? "done" : "open"}`, resolved(note) ? "Erledigt" : "Offen"), element("time", "", noteDate(note)));
    card.append(top);
    if (note.quote) card.append(element("blockquote", "", note.quote));
    const link = passageLink(note.passage_id); if (link) card.append(link);
    card.append(element("p", "note-body", note.body));
    const actions = element("div", "note-actions");
    const toggle = element("button", "text-button", resolved(note) ? "Wieder öffnen" : "Als erledigt markieren"); toggle.type = "button"; toggle.addEventListener("click", () => updateNoteStatus(note));
    const edit = element("button", "text-button", "Bearbeiten"); edit.type = "button"; edit.addEventListener("click", () => editNote(note));
    const remove = element("button", "text-button delete-note", "Löschen"); remove.type = "button"; remove.addEventListener("click", () => deleteNote(note));
    actions.append(toggle, edit, remove); card.append(actions); list.append(card);
  }
}

function editNote(note) {
  state.editingId = note.id;
  state.anchor = { passage_id: note.passage_id, checksum: note.checksum ?? null, quote: note.quote || "", start_offset: note.start_offset ?? null, end_offset: note.end_offset ?? null };
  $("note-body").value = note.body || "";
  $("note-resolved").checked = resolved(note);
  $("composer-title").textContent = "Notiz bearbeiten";
  $("save-note").textContent = "Änderung speichern";
  $("cancel-edit").hidden = false;
  renderAnchor();
  saveDraft();
  $("note-body").focus();
  $("note-form").scrollIntoView({ behavior: "smooth", block: "center" });
}

async function saveNote(event) {
  event.preventDefault();
  const body = $("note-body").value.trim();
  if (!body || state.saving || !state.work) return;
  const payload = { work_id: String(state.work.id), passage_id: state.anchor?.passage_id ?? null, checksum: state.anchor?.checksum ?? null, quote: state.anchor?.quote || "", start_offset: state.anchor?.start_offset ?? null, end_offset: state.anchor?.end_offset ?? null, body, status: $("note-resolved").checked ? "resolved" : "open" };
  setSaving(true);
  try {
    const editing = state.editingId !== null;
    const result = await api(editing ? `/notes/${encodeURIComponent(state.editingId)}` : "/notes", { method: editing ? "PUT" : "POST", body: JSON.stringify(payload) });
    const note = result.note || result;
    if (editing) state.notes = state.notes.map((existing) => String(existing.id) === String(state.editingId) ? note : existing);
    else state.notes.push(note);
    resetComposer(); renderNotes(); renderWorkStats();
    toast(editing ? "Änderung gespeichert." : "Notiz zum Band gespeichert.");
    setSaving(false);
  } catch (error) { setSaving(false, true); toast(error.message, true); }
}

function renderWorkStats() {
  const stat = $("work-stats").querySelectorAll("strong")[2];
  if (stat) stat.textContent = number(state.notes.filter((note) => !resolved(note)).length);
}

async function updateNoteStatus(note) {
  if (state.saving) return;
  setSaving(true);
  try {
    const result = await api(`/notes/${encodeURIComponent(note.id)}`, { method: "PUT", body: JSON.stringify({ ...note, status: resolved(note) ? "open" : "resolved" }) });
    state.notes = state.notes.map((existing) => String(existing.id) === String(note.id) ? result.note || result : existing);
    renderNotes(); renderWorkStats(); setSaving(false);
    toast(resolved(note) ? "Notiz wieder geöffnet." : "Notiz als erledigt markiert.");
  } catch (error) { setSaving(false, true); toast(error.message, true); }
}

async function deleteNote(note) {
  if (state.saving) return;
  setSaving(true);
  try {
    await api(`/notes/${encodeURIComponent(note.id)}`, { method: "DELETE" });
    state.notes = state.notes.filter((existing) => String(existing.id) !== String(note.id));
    if (String(state.editingId) === String(note.id)) resetComposer();
    renderNotes(); renderWorkStats(); setSaving(false); toast("Notiz gelöscht.");
  } catch (error) { setSaving(false, true); toast(error.message, true); }
}

async function saveReview() {
  if (!state.work) return;
  const status = $("review-status").value;
  const prior = reviewFor(state.work);
  $("review-status").disabled = true;
  setSaving(true);
  try {
    await api(`/reviews/${encodeURIComponent(state.work.id)}`, { method: "PUT", body: JSON.stringify({ status }) });
    state.reviews.set(String(state.work.id), status);
    renderCatalog(); setSaving(false); toast(`Prüfstand gespeichert: ${labels[status]}.`);
  } catch (error) { $("review-status").value = prior; setSaving(false, true); toast(error.message, true); }
  finally { $("review-status").disabled = false; }
}

function toggleNotes(open) {
  if (!window.matchMedia("(max-width: 1000px)").matches) return;
  $("notes-panel").classList.toggle("drawer-open", open);
  $("mobile-notes").setAttribute("aria-expanded", String(open));
  $("note-backdrop").hidden = !open;
  document.body.classList.toggle("notes-drawer-open", open);
  if (open) { $("notes-panel").setAttribute("role", "dialog"); $("notes-panel").setAttribute("aria-modal", "true"); $("note-body").focus(); }
  else { $("notes-panel").removeAttribute("role"); $("notes-panel").removeAttribute("aria-modal"); $("mobile-notes").focus(); }
}

$("mobile-notes").addEventListener("click", () => toggleNotes(true));
$("close-notes").addEventListener("click", () => toggleNotes(false));
$("note-backdrop").addEventListener("click", () => toggleNotes(false));
document.addEventListener("keydown", (event) => {
  if (!$("notes-panel").classList.contains("drawer-open")) return;
  if (event.key === "Escape") { event.preventDefault(); toggleNotes(false); }
  if (event.key === "Tab") {
    const controls = Array.from($("notes-panel").querySelectorAll('button, input, select, textarea, a[href]')).filter((control) => !control.disabled && control.offsetParent !== null);
    const first = controls[0], last = controls.at(-1);
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
  }
});
window.matchMedia("(max-width: 1000px)").addEventListener("change", (event) => {
  if (!event.matches) { $("notes-panel").classList.remove("drawer-open"); $("notes-panel").removeAttribute("role"); $("notes-panel").removeAttribute("aria-modal"); $("note-backdrop").hidden = true; document.body.classList.remove("notes-drawer-open"); $("mobile-notes").setAttribute("aria-expanded", "false"); }
});
window.matchMedia("(max-width: 700px)").addEventListener("change", renderCatalog);

$("work-search").addEventListener("input", renderCatalog);
$("work-filter").addEventListener("change", renderCatalog);
$("passage-select").addEventListener("change", (event) => {
  const [index, offset] = event.target.value.split(":");
  selectPassage(Number(index), false, offset === undefined ? null : Number(offset));
});
$("previous-passage").addEventListener("click", () => selectPassage(state.passageIndex - 1));
$("next-passage").addEventListener("click", () => selectPassage(state.passageIndex + 1));
$("next-passage-bottom").addEventListener("click", () => selectPassage(state.passageIndex + 1));
$("font-size").addEventListener("input", (event) => { document.documentElement.style.setProperty("--reading-size", `${event.target.value}px`); $("font-size-value").textContent = event.target.value; try { localStorage.setItem("ga-proofreading-font-size", event.target.value); } catch {} });
$("review-status").addEventListener("change", saveReview);
$("note-form").addEventListener("submit", saveNote);
$("note-body").addEventListener("input", saveDraft);
$("note-resolved").addEventListener("change", saveDraft);
$("cancel-edit").addEventListener("click", resetComposer);
$("clear-quote").addEventListener("click", () => { state.anchor = null; renderAnchor(); saveDraft(); });
$("notes-filter").addEventListener("change", renderNotes);
document.addEventListener("mouseup", captureSelection);
document.addEventListener("keyup", captureSelection);
document.addEventListener("touchend", () => window.setTimeout(captureSelection, 150));
for (const tab of document.querySelectorAll(".tab")) {
  tab.addEventListener("click", () => setTab(tab.dataset.tab));
  tab.addEventListener("keydown", (event) => {
    const names = ["read", "changes", "checks"];
    const current = names.indexOf(state.tab);
    let target;
    if (event.key === "ArrowRight") target = names[(current + 1) % names.length];
    if (event.key === "ArrowLeft") target = names[(current + names.length - 1) % names.length];
    if (event.key === "Home") target = names[0];
    if (event.key === "End") target = names.at(-1);
    if (target) { event.preventDefault(); setTab(target, true); }
  });
}
let savedFontSize;
try { savedFontSize = Number(localStorage.getItem("ga-proofreading-font-size")); } catch {}
if (savedFontSize >= 17 && savedFontSize <= 27) { $("font-size").value = savedFontSize; $("font-size-value").textContent = savedFontSize; document.documentElement.style.setProperty("--reading-size", `${savedFontSize}px`); }
initialize();
