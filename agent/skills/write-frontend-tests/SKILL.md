---
name: write-frontend-tests
description: Writing or updating Vitest tests for frontend targets (frontend/src).
---

# Write frontend tests

Tests sit next to the code they test: `components/TodoItem.tsx` is tested in `components/TodoItem.test.tsx`. Write the whole file with `write_test_file`; for an update, keep every existing test and add yours.

## Conventions in this repo

- Vitest with explicit imports (`import { expect, it, vi } from 'vitest'`), top-level `it(...)` blocks named as a sentence about behaviour; `describe` only to group cases of one function.
- Global setup (`src/test/setup.ts`) already loads jest-dom matchers and runs `cleanup`; use `toBeVisible`, `toHaveTextContent`, `toBeChecked`.
- Shared data: `todoFixture` from `src/test/todoFixture.ts`; spread it to vary fields (`{ ...todoFixture, completed: true }`).
- Components: `render` from Testing Library, query by role and accessible name (`getByRole('button', { name: ... })`), drive interactions with `const user = userEvent.setup()` and `await user.click(...)`.
- Design system: mock it with `vi.mock('<relative>/design-system', () => import('<relative>/design-system/mocks'))`, using the target's relative path.
- Collaborators: mock hooks and child components with `vi.mock` plus `vi.mocked(fn).mockReturnValue(...)`, casting partial return values `as unknown as ReturnType<typeof hook>`.
- HTTP: API modules mock `lib/http`'s `request` (`vi.mock('<relative>/lib/http', () => ({ request: vi.fn() }))`); tests of `lib/http` itself stub `fetch` with `vi.stubGlobal('fetch', vi.fn())` and restore with `vi.unstubAllGlobals()`.
- Hooks that use react-query render inside a fresh `QueryClientProvider` per test, with `retry: false`.
- Time-dependent code uses `vi.useFakeTimers()` and `vi.setSystemTime(...)`, restored with `vi.useRealTimers()`.

## Checks the runtime adds

Every write is formatted with the repo's Prettier config. Every run also type-checks the file with `tsc`, and a type error counts as a failure: test data must satisfy the source's types (for example, a `TodoInput` needs every required field).

## Before running

Check every import path resolves relative to the test file, and every prop and export you use exists in the source you read.
