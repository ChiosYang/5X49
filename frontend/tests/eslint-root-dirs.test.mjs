import "../tooling/next-eslint-glob-compat.mjs";
import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import { isAbsolute, join, resolve } from "node:path";
import test from "node:test";

const require = createRequire(import.meta.url);
const { Linter } = require("eslint");
const nextPlugin = require("@next/eslint-plugin-next");
const { getRootDirs } = require(
  "@next/eslint-plugin-next/dist/utils/get-root-dirs.js",
);

function fixture(t) {
  const root = mkdtempSync(join(tmpdir(), "5x49-eslint-roots-"));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  for (const name of ["web", "admin", "other"]) {
    mkdirSync(join(root, "apps", name), { recursive: true });
  }
  writeFileSync(join(root, "apps", "file.txt"), "not a directory");
  return root;
}

function matchedRoots(root, rootDir) {
  return getRootDirs({ cwd: root, settings: { next: { rootDir } } })
    .map((directory) => resolve(directory))
    .sort();
}

test("Next ESLint root matching selects directories for wildcard and brace globs", (t) => {
  const root = fixture(t);
  assert.deepEqual(matchedRoots(root, join(root, "apps", "*")),
    ["admin", "other", "web"].map((name) => join(root, "apps", name)));
  assert.deepEqual(matchedRoots(root, join(root, "apps", "{web,admin}")),
    ["admin", "web"].map((name) => join(root, "apps", name)));
});

test("Next ESLint root matching supports arrays and normalizes path separators", (t) => {
  const root = fixture(t);
  const web = join(root, "apps", "web");
  const admin = join(root, "apps", "admin");
  assert.deepEqual(matchedRoots(root, [web.replaceAll("/", "\\"), admin, null]),
    [admin, web]);
  assert.deepEqual(matchedRoots(root, join(root, "apps", "missing-*")), []);
});

test("Next ESLint root matching keeps the default working directory", (t) => {
  const root = fixture(t);
  assert.deepEqual(getRootDirs({ cwd: root, settings: {} }), [root]);
});

test("Next internal-link rule still reports pages found through a root glob", (t) => {
  const root = fixture(t);
  const pages = join(root, "apps", "web", "pages");
  mkdirSync(pages);
  writeFileSync(join(pages, "about.jsx"), "export default function About() {}");
  const linter = new Linter({ cwd: root });
  const messages = linter.verify(
    'export default function Page() { return <a href="/about">About</a>; }',
    [{
      files: ["**/*.jsx"],
      languageOptions: {
        parserOptions: { ecmaFeatures: { jsx: true } },
      },
      settings: { next: { rootDir: join(root, "apps", "{web,admin}") } },
      plugins: { "@next/next": nextPlugin },
      rules: { "@next/next/no-html-link-for-pages": "error" },
    }],
    { filename: join(root, "page.jsx") },
  );
  assert.equal(messages.length, 1);
  assert.equal(messages[0].ruleId, "@next/next/no-html-link-for-pages");
  assert.equal(messages[0].severity, 2);
});

test("Next root glob directories remain absolute outside the working directory", (t) => {
  // On Windows CI/local acceptance the temp root may be on a different drive.
  // Inspect the returned paths before resolve() can hide a malformed location.
  const root = fixture(t);
  const directories = getRootDirs({
    cwd: root,
    settings: { next: { rootDir: join(root, "apps", "{web,admin}") } },
  });
  assert.equal(directories.length, 2);
  assert.ok(directories.every((directory) => isAbsolute(directory)));
  assert.deepEqual(directories.map((directory) => resolve(directory)).sort(),
    ["admin", "web"].map((name) => join(root, "apps", name)));
});

test("Next glob adaptation keeps relative patterns and directory-only filtering", (t) => {
  const root = fixture(t);
  const requireNext = createRequire(require.resolve("@next/eslint-plugin-next"));
  const { globSync } = requireNext("fast-glob");
  const directories = globSync("apps/*", { cwd: root, onlyDirectories: true });
  assert.deepEqual(directories.map((directory) => resolve(directory)).sort(),
    ["admin", "other", "web"].map((name) => join(root, "apps", name)));
});
