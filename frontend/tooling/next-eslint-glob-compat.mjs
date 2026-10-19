import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const requireNext = createRequire(require.resolve("@next/eslint-plugin-next"));
// Resolve the alias from Next, keeping this adaptation scoped to its override.
const glob = requireNext("fast-glob");
const { globSync } = glob;

// Next joins these directories with "pages" and "src/pages". tinyglobby's
// relative output can contain ../C:/... when the cwd is on another Windows
// drive. Absolute output preserves the matched filesystem location on every OS.
glob.globSync = (patterns, options) => globSync(patterns, {
  ...options,
  absolute: true,
});
