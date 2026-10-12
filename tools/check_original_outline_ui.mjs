#!/usr/bin/env node
// Read-only integration QA for all reviewed GA 001–026 source outlines.
import assert from "node:assert/strict";
import { existsSync, mkdirSync, readFileSync } from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";
const require = createRequire(import.meta.url);
const { chromium } = require("playwright");
const base = process.argv[2] || "http://127.0.0.1:4173";
const screenshots = process.argv[3] || "/tmp/ga-original-outline";
const recipe = JSON.parse(readFileSync(new URL("ga001_026_structure.json", import.meta.url), "utf8"));
const executablePath = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "/usr/bin/chromium"].find(existsSync);
const browser = await chromium.launch({ headless: true, ...(executablePath ? { executablePath } : {}) });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
const errors = [];
page.on("pageerror", (error) => errors.push(error.message));
mkdirSync(screenshots, { recursive: true });
const summaries = [];
try {
  for (const id of Object.keys(recipe.works)) {
    const response = await page.request.get(`${base}/api/proofreading/works/${id}`);
    assert(response.ok(), `${id} API`);
    const detail = await response.json();
    await page.goto(`${base}/proofreading/?ga=${id}`);
    await page.waitForFunction((workId) => state.work?.id === workId && !state.pendingWorkId, id);
    const checked = await page.evaluate((detail) => {
      const norm = (value) => String(value || "").replace(/\s+/gu, " ").trim();
      const entries = new Map(detail.table_of_contents.map((entry) => [entry.id, entry]));
      const select = document.getElementById("passage-select");
      const options = [...select.options];
      let checked = 0, datelines = 0, continuations = 0;
      for (const option of options) {
        const entry = entries.get(option.dataset.contentsId);
        if (!entry || option.textContent.trim() !== entry.title.trim()) throw Error(`Synthetic or mismatched title: ${option.textContent}`);
        const index = detail.passages.findIndex((passage) => passage.id === entry.passage_id);
        const value = entry.start_offset === 0 ? String(index) : `${index}:${entry.start_offset}`;
        if (option.value !== value) throw Error(`Wrong contents anchor: ${entry.id}`);
        select.value = value;
        select.dispatchEvent(new Event("change", { bubbles: true }));
        if (document.getElementById("passage-text").textContent !== detail.passages[index].text) throw Error(`Changed selectable text: ${entry.id}`);
        if (state.passageIndex !== index) throw Error(`Wrong passage: ${entry.id}`);
        if (entry.start_offset > 0 && state.contentsOffset !== entry.start_offset) throw Error(`Wrong internal heading target: ${entry.id}`);
        const first = (detail.passages[index].metadata?.reading_blocks || [])[0];
        if (first?.kind === "heading" && first.start_offset === 0 && norm(detail.passages[index].text.slice(first.start_offset, first.end_offset)) === norm(detail.passages[index].title)
          && !document.getElementById("passage-title").hidden) throw Error(`Duplicated first source heading: ${entry.id}`);
        checked++;
      }
      const sourceLabels = new Set(detail.table_of_contents.map((entry) => norm(entry.title)));
      for (const group of select.querySelectorAll("optgroup")) if (!sourceLabels.has(norm(group.label))) throw Error(`Synthetic group: ${group.label}`);
      for (let index = 0; index < detail.passages.length; index++) {
        const passage = detail.passages[index];
        selectPassage(index, false);
        if (document.getElementById("passage-text").textContent !== passage.text) throw Error(`Changed continuation text: ${passage.id}`);
        if (passage.metadata?.source_dateline) {
          if (document.getElementById("passage-dateline").textContent !== passage.metadata.source_dateline || document.getElementById("passage-dateline").hidden) throw Error(`Missing source date: ${passage.id}`);
          datelines++;
        }
        if (passage.metadata?.continuation_of) {
          if (!document.getElementById("passage-title").hidden) throw Error(`Invented continuation heading: ${passage.id}`);
          continuations++;
        }
      }
      return { options: checked, source_entries: entries.size, passages: detail.passages.length, datelines, continuations };
    }, detail);
    const internal = detail.table_of_contents.find((entry) => entry.start_offset > 0);
    if (internal) {
      const targetIndex = detail.passages.findIndex((passage) => passage.id === internal.passage_id);
      await page.locator("#passage-select").selectOption(`${targetIndex}:${internal.start_offset}`);
      await page.reload();
      await page.waitForFunction((value) => document.getElementById("passage-select")?.value === value, `${targetIndex}:${internal.start_offset}`);
      assert.equal(await page.locator("#passage-text").textContent(), detail.passages[targetIndex].text, `${id} Reload preserves canonical text`);
    }
    if (id === "ga-012") {
      await page.locator("#passage-select").selectOption("0");
      assert.equal(await page.locator("#passage-title").isVisible(), false, "GA012 multiline source preface heading appears once");
    }
    if (id === "ga-009") {
      const chapter = detail.passages.findIndex((passage) => passage.metadata?.group_title === "III. Die drei Welten");
      assert(chapter >= 0, "Theosophie original III. Die drei Welten group exists");
      await page.locator("#passage-select").selectOption(String(chapter));
      assert.equal(await page.locator("#passage-group").textContent(), "III. Die drei Welten");
      assert.equal(await page.locator("#passage-group").isVisible(), true);
      await page.evaluate(() => window.scrollTo({ top: 0, behavior: "instant" }));
      await page.screenshot({ path: path.join(screenshots, "original-outline-ga009.png") });
    }
    if (id === "ga-026") {
      assert.equal(checked.datelines, 71, "GA026 all 71 original datelines remain visible");
      assert.equal(checked.continuations, 2, "GA026 retained continuation containers add no chapter titles");
      const date = detail.passages.findIndex((passage) => passage.metadata?.source_dateline && !/^Leitsätze Nr\./u.test(passage.title));
      await page.locator("#passage-select").selectOption(String(date));
      await page.evaluate(() => window.scrollTo({ top: 0, behavior: "instant" }));
      await page.screenshot({ path: path.join(screenshots, "original-outline-ga026.png") });
    }
    summaries.push({ work: id, ...checked });
  }
  assert.deepEqual(errors, [], "No browser errors");
  console.log(JSON.stringify({ passed: true, works: summaries.length, source_entries: summaries.reduce((sum, row) => sum + row.source_entries, 0), options: summaries.reduce((sum, row) => sum + row.options, 0), summaries, screenshots }, null, 2));
} finally { await browser.close(); }
