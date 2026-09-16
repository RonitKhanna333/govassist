import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import test from "node:test";

const here = dirname(fileURLToPath(import.meta.url));
const messagesDir = join(here, "..", "messages");

const load = (code) =>
  JSON.parse(readFileSync(join(messagesDir, `${code}.json`), "utf8"));

const CODES = ["en", "hi", "pa", "ta"];
const catalogs = Object.fromEntries(CODES.map((code) => [code, load(code)]));

test("every catalog carries every key the English one does", () => {
  const base = Object.keys(catalogs.en).sort();
  for (const code of CODES) {
    const keys = Object.keys(catalogs[code]).sort();
    assert.deepEqual(
      keys,
      base,
      `${code}.json differs from en.json -- a missing key is a runtime English leak`,
    );
  }
});

test("no catalog leaves a value empty", () => {
  for (const code of CODES) {
    for (const [key, value] of Object.entries(catalogs[code])) {
      assert.ok(String(value).trim().length > 0, `${code}.json has an empty value for ${key}`);
    }
  }
});

test("the three Indic catalogs are actually translated, not copied English", () => {
  // Catches the "ship it with en.json copied over" failure, which passes
  // every structural check while showing English to a Tamil reader.
  for (const code of ["hi", "pa", "ta"]) {
    const identical = Object.keys(catalogs.en).filter(
      (key) => catalogs[code][key] === catalogs.en[key],
    );
    assert.ok(
      identical.length < 3,
      `${code}.json has ${identical.length} values identical to English: ${identical.join(", ")}`,
    );
  }
});

test("placeholders survive translation in every catalog", () => {
  const placeholderOf = (value) => (String(value).match(/\{(\w+)\}/g) ?? []).sort();
  for (const [key, english] of Object.entries(catalogs.en)) {
    const expected = placeholderOf(english);
    if (expected.length === 0) continue;
    for (const code of CODES) {
      assert.deepEqual(
        placeholderOf(catalogs[code][key]),
        expected,
        `${code}.json "${key}" lost or altered a {placeholder}`,
      );
    }
  }
});
