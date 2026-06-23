# `apps/web` test suite

```
tests/
  setup.ts           global Vitest setup (jest-dom matchers, cleanup, matchMedia stub)
  unit/              pure functions/components in isolation (lib, simple components)
  integration/       hooks + stores + multi-component flows (renderHook / render)
  regression/        pins for specific previously-fixed bugs
  e2e/               Playwright specs (run separately via `npm run test:e2e`)
```

Runner: **Vitest** + **@testing-library/react** in a **jsdom** environment.
Config: `vitest.config.ts` (only `tests/{unit,integration,regression}` are
collected — `tests/e2e` is excluded and belongs to Playwright).

## Running

```bash
npm test               # vitest run (unit + integration + regression)
npm run test:watch     # watch mode
npm run test:coverage  # v8 coverage over src/{lib,store,hooks}
npm run test:e2e       # Playwright e2e (separate runner)
```

## Conventions

- Use the `@/…` path alias (wired in `vitest.config.ts`) exactly like app code.
- **unit** — pure utilities and presentational components; no providers.
- **integration** — drive stores/hooks via `renderHook` and components via
  `render`, asserting user-visible behaviour and store/query wiring (never
  implementation details).
- **regression** — name the test after the bug; open the description with
  `REGRESSION:`. Where a fixture is encoding-sensitive (e.g. mojibake), drive the
  cases off the source-of-truth export rather than re-typing fragile bytes.
- Mock network (`axios`) and Firebase at the module boundary with `vi.mock`.
