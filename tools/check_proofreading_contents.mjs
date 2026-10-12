#!/usr/bin/env node
// Read-only browser regression for original source numbering and TOC anchors.
import assert from "node:assert/strict";
import { existsSync } from "node:fs";
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
const { chromium } = require("playwright");
const base = process.argv[2] || "http://127.0.0.1:4173";
const executablePath = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "/usr/bin/chromium"].find(existsSync);
const browser = await chromium.launch({ headless: true, ...(executablePath ? { executablePath } : {}) });
const page = await browser.newPage();
const errors = [];
page.on("pageerror", (error) => errors.push(error.message));
const chapterText = "I.\nDas Originalkapitel\n\nÄußere Welt 🌍.\n\nZusatz zur Neuauflage (1918).\n\nWeiterer Text.";
const headingEnd = chapterText.indexOf("\n\n");
const additionStart = chapterText.indexOf("Zusatz zur Neuauflage");
const additionEnd = chapterText.indexOf("\n\n", additionStart);
const passages = [
  { id: "preface", title: "Vorrede", text: "Unnummerierte Vorrede.", metadata: {} },
  { id: "first", title: "I. Das Originalkapitel", text: chapterText, metadata: { group_title: "III. Die drei Welten", reading_blocks: [
    { kind: "heading", level: 2, start_offset: 0, end_offset: headingEnd },
    { kind: "prose", start_offset: headingEnd + 2, end_offset: additionStart - 2 },
    { kind: "heading", level: 3, start_offset: additionStart, end_offset: additionEnd },
    { kind: "prose", start_offset: additionEnd + 2, end_offset: chapterText.length },
  ] } },
  { id: "continuation", title: "I. Das Originalkapitel", text: "Fortgesetzter Text ohne neue Originalüberschrift.", metadata: { continuation_of: "first" } },
  { id: "insertion", title: "Einfügung", text: "Einfügung zwischen den Kapiteln.", metadata: { source_dateline: "(23. November 1924)" } },
  { id: "second", title: "II. Das folgende Kapitel", text: "Das zweite Kapitel.", metadata: {} },
];
const contents = [
  { id: "preface", title: "Vorrede", level: 1, passage_id: "preface", start_offset: 0, parent_id: null },
  { id: "part", title: "I. Teil: Wissenschaft der Freiheit", level: 1, passage_id: "first", start_offset: 0, parent_id: null },
  { id: "first", title: "I. Das Originalkapitel", level: 2, passage_id: "first", start_offset: 0, parent_id: "part" },
  { id: "addition", title: "Zusatz zur Neuauflage (1918).", level: 3, passage_id: "first", start_offset: additionStart, parent_id: "first" },
  { id: "insertion", title: "Einfügung", level: 1, passage_id: "insertion", start_offset: 0, parent_id: null },
  { id: "second", title: "II. Das folgende Kapitel", level: 1, passage_id: "second", start_offset: 0, parent_id: null },
];
let sourceContents = contents;
await page.route("**/api/proofreading/works/ga-001", async (route) => {
  const response = await route.fetch();
  const detail = await response.json();
  await route.fulfill({ response, json: { ...detail, passages, table_of_contents: sourceContents,
    work: { ...detail.work, passage_count: passages.length, character_count: passages.reduce((sum, p) => sum + p.text.length, 0) } } });
});
try {
  await page.goto(`${base}/proofreading/?ga=ga-001`);
  await page.waitForFunction(() => document.querySelector("#passage-text")?.textContent === "Unnummerierte Vorrede.");
  assert.deepEqual((await page.locator("#passage-select option").allTextContents()).map((text) => text.trim()), contents.filter((entry) => entry.id !== "part").map((entry) => entry.title));
  assert.equal(await page.locator("#passage-select optgroup").getAttribute("label"), "I. Teil: Wissenschaft der Freiheit");
  await page.locator("#passage-select").selectOption("1");
  assert.equal(await page.locator("#passage-text").textContent(), chapterText);
  assert.equal(await page.locator("#passage-title").isVisible(), false, "The first original heading is rendered only once");
  assert.equal(await page.locator("#reading-heading-0").textContent(), "I.\nDas Originalkapitel");
  assert.equal(await page.locator("#passage-group").textContent(), "III. Die drei Welten");
  assert.equal(await page.locator("#passage-group").isVisible(), true, "Original main divisions remain visible above child headings");
  await page.locator("#passage-select").selectOption(`1:${additionStart}`);
  assert.equal(new URL(page.url()).searchParams.get("offset"), String(additionStart));
  await page.reload();
  await page.waitForFunction((value) => document.querySelector("#passage-select")?.value === value, `1:${additionStart}`);
  assert.equal(await page.locator("#passage-text").textContent(), chapterText, "Offset navigation keeps all selectable UTF-16 text intact");
  await page.locator("#next-passage").click();
  assert.equal(await page.locator("#passage-text").textContent(), passages[2].text);
  assert.equal(await page.locator("#passage-select").inputValue(), `1:${additionStart}`, "Continuation containers display the preceding source entry without navigating away");
  assert.equal(await page.locator("#passage-title").isVisible(), false, "Continuation containers have no invented chapter heading");
  await page.locator("#passage-select").selectOption("3");
  assert.equal(await page.locator("#passage-title").isVisible(), true, "A later external source title is still shown");
  assert.equal(await page.locator("#passage-text").textContent(), passages[3].text);
  assert.equal(await page.locator("#passage-dateline").textContent(), "(23. November 1924)");
  assert.equal(await page.locator("#passage-dateline").isVisible(), true, "Original dates remain separate from source essay titles");
  sourceContents = [{ ...contents[0], start_offset: 999 }];
  await page.goto(`${base}/proofreading/?ga=ga-001`);
  await page.waitForFunction(() => document.querySelector("#passage-text")?.textContent === "Unnummerierte Vorrede.");
  assert.equal((await page.locator('#passage-select option[value="0"]').textContent()).trim(), "Vorrede", "Malformed source outline uses unnumbered passage fallback");
  assert.equal(await page.locator('#passage-select option[value="1:0"]').count(), 0, "A first body heading is not duplicated as its own child");
  assert.deepEqual(errors, []);
  console.log("Original contents browser checks passed: Roman numerals, unnumbered preface and insertion, source parts, exact UTF-16 anchors, continuation containers, duplicate-heading suppression and malformed-outline fallback.");
} finally { await browser.close(); }
