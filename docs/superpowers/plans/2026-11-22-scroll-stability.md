# Stable review workspace scrolling

**Goal:** Keep the upload, running and stopped states at the same horizontal position while keeping the right edge visually continuous.

**Diagnosis:** On 6cf324d, the real ThesisUploadPanel changes the local fixture from a short page to an overflowing page. A classic scrollbar consumes 10.95 CSS pixels in the measured scaled viewport; the card center moves left 5.48 pixels. Removing stable reservation fixed an unpainted gutter but reintroduced this transition regression.

**Approach:** Keep the workspace at the dynamic viewport height, with the header outside the scrolling app-content region. Reserve the stable gutter inside that content region, whose background already matches it. The root no longer needs a gutter or a synthetic header background. Retain native scrollIntoView, focus behavior and real scrollbars; use overflow-y: scroll as the unsupported-browser fallback. The initial root-background prototype still left a visible top-right patch and was discarded before commit.

**Sources:** https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/scrollbar-gutter ; https://www.w3.org/TR/css-overflow-3/#scrollbar-gutter-property ; https://github.com/radix-ui/primitives/discussions/1586

**Verification:** Drive the real upload panel with local-only state, never create an online detection. Compare card/header coordinates across start/stop and rule expansion, settings/feedback/account popups, light/dark, English/Chinese and narrow/desktop widths. Check the painted header/gutter edge visually. Run relevant component suites and production build, obtain independent review, then use the standard external publisher with data/config preservation.
