# Header polish follow-up

**Goal:** Remove the unused right scrollbar gutter, align topbar actions, and use the same gear in the Settings dialog.

**Evidence:** A short page has no vertical overflow but its header ends 15.33px before the viewport edge because root scrollbar-gutter is forced to stable. Remove both the forced reservation and its custom Radix compensation override so native overflow and the existing dialog scroll lock manage real scrollbars together.

**Scope:** Match Feedback to the existing 36px icon targets, 18px / 1.8-stroke icons and shared center line. Reuse all settings and feedback behavior. Verify short/long pages, dialogs, account menus, themes, locales and narrow screens before the external-only release. Preserve reports, detector, private config, and the local original preview.
