const nextCoreWebVitals = require("eslint-config-next/core-web-vitals");

module.exports = [
  ...nextCoreWebVitals,
  {
    // Playwright fixtures/specs aren't React code: fixture callbacks named
    // `use` (Playwright's convention) trip react-hooks' `use*` naming
    // heuristic, and this tree was never covered by `next lint`'s default
    // scope either.
    ignores: ["tests/**", ".next/**", "node_modules/**"],
  },
  {
    // eslint-plugin-react-hooks v7 (pulled in by eslint-config-next 16)
    // added `set-state-in-effect`, which flags syncing local state from
    // external sources (e.g. a router query param) inside an effect. That's
    // a legitimate, existing pattern in a couple of pages here; fixing it
    // properly (tracking "already synced" instead of re-deriving state)
    // is a real behavioral change that deserves its own reviewed PR with
    // test coverage, so we keep it visible as a warning instead of failing
    // the build on it.
    rules: {
      "react-hooks/set-state-in-effect": "warn",
    },
  },
];
