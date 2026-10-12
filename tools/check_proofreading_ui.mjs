#!/usr/bin/env node
// Development QA for the local proofreading view. Browser runs in its own
// temporary profile. Writes are opt-in and should use a disposable notes DB.
import assert from "node:assert/strict";
import { existsSync, mkdirSync, readFileSync } from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";
import { gunzipSync } from "node:zlib";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");
const args = process.argv.slice(2);
const option = (name, fallback) => args.includes(name) ? args[args.indexOf(name) + 1] : fallback;
const base = option("--url", "http://127.0.0.1:4173").replace(/\/$/, "");
const screenshots = option("--screenshots", "/tmp/ga-proofreading-ui");
const writes = args.includes("--allow-test-writes");
const contentFile = option("--content", null);
const staged = contentFile ? JSON.parse((contentFile.endsWith(".gz") ? gunzipSync(readFileSync(contentFile)) : readFileSync(contentFile)).toString("utf8")) : null;
if (staged && writes) throw new Error("Staged content QA requires a read-only run; notes must match the server's canonical text.");
const chromeCandidates = [
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  "/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/google-chrome",
];
const executablePath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || chromeCandidates.find(existsSync);
const browser = await chromium.launch({ headless: true, ...(executablePath ? { executablePath } : {}) });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
const errors = [];
page.on("pageerror", (error) => errors.push(error.message));
mkdirSync(screenshots, { recursive: true });
let testNoteId;
let priorReview;
const marker = `UI-Prüfung ${Date.now()}`;
const stagedDetail = (detail) => staged ? { ...detail, passages: staged.passages, work: { ...detail.work, passage_count: staged.passages.length, character_count: staged.passages.reduce((sum, passage) => sum + passage.text.length, 0) } } : detail;
if (staged) await page.route("**/api/proofreading/works/ga-040", async (route) => {
  const response = await route.fetch();
  await route.fulfill({ response, json: stagedDetail(await response.json()) });
});
const json = async (suffix) => {
  const response = await page.request.get(`${base}/api/proofreading${suffix}`);
  assert(response.ok(), `API ${suffix}: ${response.status()}`);
  const payload = await response.json();
  return suffix === "/works/ga-040" ? stagedDetail(payload) : payload;
};
const selectText = async (start, end) => page.evaluate(({ start, end }) => {
  const root = document.querySelector("#passage-text");
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  let offset = 0, first, last;
  while (walker.nextNode()) {
    const node = walker.currentNode;
    if (!first && start <= offset + node.length) first = [node, start - offset];
    if (end <= offset + node.length) { last = [node, end - offset]; break; }
    offset += node.length;
  }
  const range = document.createRange(); range.setStart(...first); range.setEnd(...last);
  const selection = window.getSelection(); selection.removeAllRanges(); selection.addRange(range);
  document.dispatchEvent(new MouseEvent("mouseup", { bubbles: true }));
}, { start, end });

try {
  await page.goto(`${base}/proofreading/?ga=ga-040`);
  await page.waitForFunction(() => document.querySelector("#passage-text")?.textContent.length > 0);
  const catalog = await json("/catalog");
  const detail = await json("/works/ga-040");
  assert.equal(await page.locator(".work-item").count(), catalog.works.length);
  assert.equal(await page.locator("#work-number").textContent(), "GA 040");
  assert.equal(await page.locator("#work-title").textContent(), detail.work.title);
  assert.equal(await page.locator("#passage-text").textContent(), detail.passages[0].text);
  const calendar = detail.passages[0];
  const calendarHeadings = (calendar.metadata?.reading_blocks || []).filter((block) => block.kind === "heading");
  const calendarSections = calendar.metadata?.reading_sections || [];
  if (calendarSections.length) {
    assert.equal(calendarSections.length, 6, "Two prefaces and four seasons are sibling reading sections");
    const options = page.locator('#passage-select option[data-section][value="0"], #passage-select option[data-section][value^="0:"]');
    assert.equal(await options.count(), 6);
    const firstStyle = await page.locator("#passage-title").evaluate((node) => { const style = getComputedStyle(node); return [style.fontSize, style.fontWeight, style.lineHeight]; });
    for (const section of calendarSections.slice(1)) {
      const node = page.locator(`#reading-heading-${section.start_offset}`);
      assert.equal(await node.evaluate((node) => node.tagName), "H3", "All prefaces and seasons have the same heading rank");
      assert.deepEqual(await node.evaluate((node) => { const style = getComputedStyle(node); return [style.fontSize, style.fontWeight, style.lineHeight]; }), firstStyle, "Same-rank calendar headings use the same typography");
      assert.equal(await page.locator(`#passage-select option[value="0:${section.start_offset}"]`).count(), 1, "Source heading is not duplicated as a child of itself");
    }
  }
  if (calendarHeadings.length) {
    const seasons = calendarHeadings.filter((block) => ["FRÜHLING", "SOMMER", "HERBST", "WINTER"].includes(calendar.text.slice(block.start_offset, block.end_offset)));
    const weeks = calendarHeadings.filter((block) => /^\d+$/.test(calendar.text.slice(block.start_offset, block.end_offset)));
    assert.equal(seasons.length, 4);
    assert.equal(weeks.length, 52);
    assert.deepEqual(await page.locator('#passage-select option[data-heading="calendar-number"]').allTextContents().then((labels) => labels.map((label) => Number(label.match(/Spruch (\d+)/)[1]))), Array.from({ length: 52 }, (_, index) => index + 1));
    for (const block of [...seasons, ...weeks]) {
      const value = `0:${block.start_offset}`;
      const option = page.locator(`#passage-select option[value="${value}"]`);
      assert.equal(await option.count(), 1, "Every season and poem is in contents");
      await page.locator("#passage-select").selectOption(value);
      assert.equal(await page.locator("#passage-select").inputValue(), value);
      assert.equal(new URL(page.url()).searchParams.get("offset"), String(block.start_offset));
      const target = page.locator(`#reading-heading-${block.start_offset}`);
      assert.equal(await target.textContent(), calendar.text.slice(block.start_offset, block.end_offset));
      assert(await target.evaluate((node) => { const box = node.getBoundingClientRect(); return box.top >= 0 && box.top < innerHeight; }), "Contents jumps to its heading");
      assert.equal(await page.locator("#passage-text").textContent(), calendar.text);
    }
    await page.reload();
    const last = weeks.at(-1);
    await page.waitForFunction((offset) => document.querySelector("#passage-select")?.value === `0:${offset}`, last.start_offset);
    assert.equal(await page.locator(`#reading-heading-${last.start_offset}`).textContent(), "52");
    const firstDate = calendarHeadings.find((block) => block.level === 2);
    const dateURL = new URL(page.url()); dateURL.searchParams.set("offset", firstDate.start_offset);
    await page.goto(dateURL.href);
    await page.waitForFunction((offset) => document.querySelector("#passage-select")?.value === `0:${offset}`, weeks[0].start_offset);
    assert.equal(await page.locator(`#reading-heading-${firstDate.start_offset}`).textContent(), calendar.text.slice(firstDate.start_offset, firstDate.end_offset));
    await page.locator("#passage-select").selectOption("0");
    assert.equal(new URL(page.url()).searchParams.has("offset"), false);
  }
  for (let index = 0; index < detail.passages.length; index++) {
    await page.locator("#passage-select").selectOption(String(index));
    assert.equal(await page.locator("#passage-text").textContent(), detail.passages[index].text, `Exact selectable text for section ${index + 1}`);
    const blocks = detail.passages[index].metadata?.reading_blocks || [];
    if (blocks.length) {
      assert.equal(await page.locator("#passage-text .reading-heading").count(), blocks.filter((block) => block.kind === "heading").length);
      assert.equal(await page.locator('#passage-text .reading-verse[data-poem-start="true"]').count(), blocks.filter((block) => block.kind === "verse" && block.poem_start === true).length, `Only explicit independent poem starts in section ${index + 1}`);
    }
  }
  const worksIndex = detail.passages.findIndex((passage) => passage.id === "ga-040-doc-heading-9" && passage.metadata?.reading_sections?.length);
  if (worksIndex >= 0) {
    const passage = detail.passages[worksIndex];
    const sections = passage.metadata.reading_sections;
    const options = page.locator(`#passage-select option[data-section][value="${worksIndex}"], #passage-select option[data-section][value^="${worksIndex}:"]`);
    assert.equal(await options.count(), sections.length, "Independent works are sibling contents entries");
    for (const [index, section] of sections.entries()) {
      const value = index ? `${worksIndex}:${section.start_offset}` : String(worksIndex);
      const entry = page.locator(`#passage-select option[value="${value}"]`);
      assert.equal(await entry.count(), 1, "No duplicate title/heading for one work");
      assert((await entry.textContent()).endsWith(section.title));
      await page.locator("#passage-select").selectOption(value);
      assert.equal(await page.locator("#passage-text").textContent(), passage.text);
      if (index) {
        const target = page.locator(`[data-section-start-offset="${section.start_offset}"]`);
        assert(await target.evaluate((node) => { const box = node.getBoundingClientRect(); return box.top >= 0 && box.top < innerHeight; }));
        if (section.label_kind === "incipit") {
          const incipit = target.locator(".reading-incipit");
          assert.equal(await incipit.textContent(), section.title);
          assert.equal(await incipit.getAttribute("role"), null, "An incipit is an ordinary source verse, not a heading");
          assert.deepEqual(await incipit.evaluate((node) => { const style = getComputedStyle(node); const body = getComputedStyle(node.closest(".reading-verse")); return [style.fontSize === body.fontSize, style.fontWeight === body.fontWeight, style.lineHeight === body.lineHeight]; }), [true, true, true], "Contents labels never change the first verse's typography");
        }
        else assert.equal(await target.evaluate((node) => node.tagName), "H3", "Tischgebet has the same heading rank as Säulenweisheit");
        await page.reload();
        await page.waitForFunction((targetValue) => document.querySelector("#passage-select")?.value === targetValue, value);
      }
    }
    await selectText(0, passage.text.length);
    const selected = await page.evaluate(() => state.anchor);
    assert.equal(selected.quote, passage.text, "Navigational incipits never duplicate or invent book text");
    assert.equal(selected.start_offset, 0); assert.equal(selected.end_offset, passage.text.length);
    await page.locator("#passage-select").selectOption(`${worksIndex}:${sections[2].start_offset}`);
    await page.screenshot({ path: path.join(screenshots, "desktop-independent-works.png") });
  }
  assert(!(await page.locator("#passage-select option").allTextContents()).some((title) => /^\s*\d+\.\s/u.test(title)), "The import order never adds numbering to contents labels");
  await page.locator("#passage-select").selectOption("0");
  const structure = await page.evaluate(() => {
    const previous = { detail: state.detail, index: state.passageIndex };
    const text = "📖 Frühling\n\nOster-Stimmung\n\n1\n\nWenn aus den Weltenweiten *\nDie Sonne spricht *";
    const block = (content, kind, level) => ({ kind, start_offset: text.indexOf(content), end_offset: text.indexOf(content) + content.length, ...(level ? { level } : {}) });
    const marker = text.indexOf("*");
    const fixture = { id: "structure-check", title: "Seelenkalender", text, metadata: {
      group_title: "Anthroposophischer Seelenkalender",
      reading_blocks: [block("📖 Frühling", "heading", 1), block("Oster-Stimmung", "heading", 2), block("1", "heading", 3), { ...block("Wenn aus den Weltenweiten *\nDie Sonne spricht *", "verse"), poem_start: true }],
      annotations: [{ id: "EPUB/chapter.xhtml#note-1&ä %?", marker: "*", text: "Zweite Ausgabe 1918/19", start_offset: marker, end_offset: marker + 1 }]
    } };
    state.detail = { ...previous.detail, passages: [fixture] }; state.passageIndex = 0; renderPassage();
    const root = document.querySelector("#passage-text");
    const headings = Array.from(root.querySelectorAll(".reading-heading")).map((node) => node.textContent);
    const references = root.querySelectorAll(".source-note-reference");
    references[0].click();
    const result = { text: root.textContent, headings, references: references.length, notesOpen: document.querySelector("#source-annotations").open,
      poemStart: root.querySelector(".reading-verse").dataset.poemStart,
      note: document.querySelector("#source-annotation-1 .source-note-text").textContent,
      backlink: document.querySelector(".source-note-back").getAttribute("href"), referenceId: references[0].id };
    const range = document.createRange(); range.selectNodeContents(root);
    const selection = window.getSelection(); selection.removeAllRanges(); selection.addRange(range);
    captureSelection(); result.anchor = state.anchor;
    fixture.metadata.reading_blocks[0].end_offset = 1; renderReadingText(fixture);
    result.fallbackText = root.textContent; result.fallbackHeadings = root.querySelectorAll(".reading-heading").length;
    selection.removeAllRanges(); state.detail = previous.detail; state.passageIndex = previous.index; renderPassage(); updateURL();
    return result;
  });
  assert.equal(structure.text, "📖 Frühling\n\nOster-Stimmung\n\n1\n\nWenn aus den Weltenweiten *\nDie Sonne spricht *");
  assert.deepEqual(structure.headings, ["📖 Frühling", "Oster-Stimmung", "1"]);
  assert.equal(structure.references, 1); assert.equal(structure.notesOpen, true);
  assert.equal(structure.poemStart, "true");
  assert.equal(structure.note, "Zweite Ausgabe 1918/19"); assert.equal(structure.backlink, `#${structure.referenceId}`);
  assert.equal(structure.anchor.quote, structure.text); assert.equal(structure.anchor.start_offset, 0); assert.equal(structure.anchor.end_offset, structure.text.length);
  assert.equal(structure.fallbackText, structure.text); assert.equal(structure.fallbackHeadings, 0);
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: "instant" }));
  await page.screenshot({ path: path.join(screenshots, "desktop-reading.png") });
  const spring = page.locator(".reading-heading").filter({ hasText: /^FRÜHLING$/ }).first();
  if (await spring.count()) {
    await spring.scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(screenshots, "desktop-calendar.png") });
    await page.evaluate(() => window.scrollTo({ top: 0, behavior: "instant" }));
  }

  await page.locator("#tab-changes").click();
  assert.equal(await page.locator(".sample-card").count(), (detail.work.samples || []).length);
  assert.equal(await page.locator(".comparison-card").count(), Math.min(24, detail.changes.length));
  for (const sample of await page.locator(".sample-excerpt").allTextContents()) assert(sample.trim().length > 0);
  await page.screenshot({ path: path.join(screenshots, "desktop-changes.png") });
  await page.locator("#tab-checks").click();
  assert.equal(await page.locator(".flag-card").count(), Math.min(24, detail.flags.length));
  await page.locator("#tab-read").click();

  await selectText(0, Math.min(40, detail.passages[0].text.length));
  const quote = detail.passages[0].text.slice(0, 40);
  assert.equal(await page.locator("#quote-text").textContent(), quote);

  if (writes) {
    await page.locator("#note-body").fill(marker);
    await page.locator("#save-note").click();
    await page.locator(".note-card").filter({ hasText: marker }).waitFor();
    let notes = (await json("/notes?work_id=ga-040")).notes;
    let note = notes.find((item) => item.body === marker);
    assert(note, "Anchored note persisted via API"); testNoteId = note.id;
    assert.equal(note.quote, quote); assert.equal(note.start_offset, 0); assert.equal(note.end_offset, 40);
    assert.equal(note.checksum, detail.passages[0].checksum);
    const card = page.locator(".note-card").filter({ hasText: marker });
    await card.getByRole("button", { name: "Bearbeiten", exact: true }).click();
    await page.locator("#note-body").fill(`${marker} bearbeitet`);
    await page.locator("#save-note").click();
    await page.waitForFunction((value) => Array.from(document.querySelectorAll(".note-body")).some((node) => node.textContent === value), `${marker} bearbeitet`);
    await card.getByRole("button", { name: "Als erledigt markieren", exact: true }).click();
    await card.waitFor({ state: "hidden" });
    await page.locator("#notes-filter").selectOption("resolved");
    await card.waitFor();
    notes = (await json("/notes?work_id=ga-040")).notes;
    note = notes.find((item) => item.id === testNoteId);
    assert.equal(note.body, `${marker} bearbeitet`); assert.equal(note.status, "resolved");
    priorReview = await page.locator("#review-status").inputValue();
    await page.locator("#review-status").selectOption("in_progress");
    await page.waitForFunction(() => !document.querySelector("#review-status").disabled);
    const reviews = (await json("/notes?work_id=ga-040")).reviews;
    assert(Array.isArray(reviews) ? reviews.some((item) => item.work_id === "ga-040" && item.status === "in_progress") : (reviews["ga-040"]?.status || reviews["ga-040"]) === "in_progress");
  }

  await page.locator("#note-body").fill(`${marker} Entwurf`);
  await page.locator("#next-passage").click();
  assert.equal(await page.locator("#note-body").inputValue(), `${marker} Entwurf`);
  await page.locator("#work-search").fill("wahrspruch");
  assert.equal(await page.locator(".work-item").count(), 1);
  for (const search of ["GA 40", "GA040", "0040"]) {
    await page.locator("#work-search").fill(search);
    assert.equal(await page.locator(".work-item").count(), 1);
    assert.equal(await page.locator(".work-item").getAttribute("data-id"), "ga-040");
  }
  await page.locator("#work-search").fill("");
  await page.locator('.work-item[data-id="ga-001"]').click();
  await page.waitForFunction(() => document.querySelector("#work-number").textContent === "GA 001");
  await page.locator('.work-item[data-id="ga-040"]').click();
  await page.waitForFunction(() => document.querySelector("#work-number").textContent === "GA 040");
  assert.equal(await page.locator("#note-body").inputValue(), `${marker} Entwurf`);

  await page.setViewportSize({ width: 390, height: 844 });
  const mobileLast = calendarHeadings.filter((block) => /^\d+$/.test(calendar.text.slice(block.start_offset, block.end_offset))).at(-1);
  if (mobileLast) {
    await page.locator("#passage-select").selectOption(`0:${mobileLast.start_offset}`);
    assert.equal(await page.locator(`#reading-heading-${mobileLast.start_offset}`).textContent(), "52");
    await page.locator("#passage-select").selectOption("0");
  }
  if (worksIndex >= 0) {
    const passage = detail.passages[worksIndex];
    for (const section of passage.metadata.reading_sections.slice(2, 4)) {
      await page.locator("#passage-select").selectOption(`${worksIndex}:${section.start_offset}`);
      assert.equal(await page.locator("#passage-text").textContent(), passage.text);
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), "Independent work headings fit on mobile");
    }
    await page.screenshot({ path: path.join(screenshots, "mobile-independent-works.png") });
    await page.locator("#passage-select").selectOption("0");
  }
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: "instant" }));
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), "Mobile page has no horizontal overflow");
  assert((await page.locator(".work-item-title").first().evaluate((node) => parseFloat(getComputedStyle(node).fontSize))) >= 14);
  await page.screenshot({ path: path.join(screenshots, "mobile-reading.png") });
  await page.locator("#mobile-notes").click();
  assert.equal(await page.locator("#mobile-notes").getAttribute("aria-expanded"), "true");
  assert.equal(await page.locator("#notes-panel").getAttribute("role"), "dialog");
  await page.screenshot({ path: path.join(screenshots, "mobile-notes.png") });
  await page.keyboard.press("Escape");
  assert.equal(await page.locator("#mobile-notes").getAttribute("aria-expanded"), "false");
  assert.deepEqual(errors, [], "No page JavaScript errors");
  console.log(JSON.stringify({ passed: true, works: catalog.works.length, passages: detail.passages.length, checks: ["catalog/search", "four seasons and all 52 calendar poems in contents", "exact heading jumps and reload targets", "all complete selectable passages", "semantic internal headings", "independent works, actual incipits and sibling contents", "anchored source notes and backlinks", "UTF-16 selection across styled blocks", "malformed structure fallback", "sample excerpts", "change and flag reports", "selection anchor", ...(writes ? ["durable note create/edit/resolve", "review status"] : []), "draft recovery", "mobile layout/drawer", "no JavaScript errors"], screenshots }, null, 2));
} finally {
  if (testNoteId) await page.request.delete(`${base}/api/proofreading/notes/${encodeURIComponent(testNoteId)}`);
  if (priorReview) await page.request.put(`${base}/api/proofreading/reviews/ga-040`, { data: { status: priorReview } });
  await browser.close();
}
