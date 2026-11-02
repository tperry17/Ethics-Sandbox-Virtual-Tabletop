// Renders the social-preview images in static/og/ (1200x630): the Center's
// seal, the page's title and a line saying what it is, on the site's white.
// Colours and fonts come from static/css/tokens.css. Run after changing an
// exercise's title or short description:  node scripts/make-og-images.mjs
import { createRequire } from "node:module";
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");
const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");

function rows(path) {
  // The site CSVs are simple enough to read with a small quoted-field parser.
  const text = readFileSync(resolve(root, path), "utf8");
  const out = [];
  let row = [], field = "", quoted = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (quoted) {
      if (c === '"' && text[i + 1] === '"') { field += '"'; i++; }
      else if (c === '"') quoted = false;
      else field += c;
    } else if (c === '"') quoted = true;
    else if (c === ",") { row.push(field); field = ""; }
    else if (c === "\n") { row.push(field); out.push(row); row = []; field = ""; }
    else if (c !== "\r") field += c;
  }
  if (field || row.length) { row.push(field); out.push(row); }
  const [head, ...body] = out;
  return body.filter((r) => r.length > 1).map((r) => Object.fromEntries(head.map((h, i) => [h, r[i]])));
}

const pages = [
  { file: "default", title: "Ethics Sandbox", line: "A shared table for exercises in ethics and civil discourse." },
  ...rows("content/site/exercises.csv").map((r) => ({
    file: r.slug, title: r.title, line: r.short_description,
  })),
];

const seal = pathToFileURL(resolve(root, "static/icons/seal-512.png")).href;
const tokens = pathToFileURL(resolve(root, "static/css/tokens.css")).href;
const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;");

mkdirSync(resolve(root, "static/og"), { recursive: true });
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1200, height: 630 } });
for (const p of pages) {
  const html = resolve(mkdtempSync(resolve(tmpdir(), "og-")), "page.html");
  writeFileSync(html, `<!doctype html><link rel="stylesheet" href="${tokens}">
<style>
  body { margin: 0; width: 1200px; height: 630px; background: var(--surface-page); display: flex;
    align-items: center; gap: 64px; padding: 0 88px; box-sizing: border-box;
    border-top: 12px solid var(--accent-rubric); font-family: var(--font-reading); }
  img { width: 220px; height: 220px; flex: none; }
  p.eyebrow { margin: 0 0 16px; font: 500 24px var(--font-ui); letter-spacing: .08em;
    text-transform: uppercase; color: var(--accent-rubric); }
  h1 { margin: 0 0 20px; font-size: 76px; line-height: 1.05; font-weight: 700; color: var(--text-primary); }
  p.line { margin: 0; font-size: 32px; line-height: 1.35; color: var(--text-secondary); }
</style>
<img src="${seal}" alt="">
<div><p class="eyebrow">Ethics Sandbox</p><h1>${esc(p.title)}</h1><p class="line">${esc(p.line)}</p></div>`);
  await page.goto(pathToFileURL(html).href);
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({ path: resolve(root, `static/og/${p.file}.png`) });
  console.log(`static/og/${p.file}.png`);
}
await browser.close();
