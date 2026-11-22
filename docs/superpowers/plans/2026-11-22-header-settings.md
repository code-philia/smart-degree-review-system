# Header settings implementation plan

**Goal:** Move Settings out of the account menu into an icon button between Notifications and Feedback, then publish the reviewed change to the external deployment.

**Scope:** Reuse the language and appearance dialog. Match the notification button's 36px target, 18px icon, rounded corners, muted color and hover/focus treatment. Keep one settings entry, localized accessible labels and keyboard focus restoration. No backend, report data, detector or intranet changes. PR #17 includes unrelated reference guidance, so do not merge it wholesale.

**Steps:**
1. Update the AppShell interaction test for the new entry and add an English keyboard/focus flow. Observe failure on the existing implementation.
2. Move the trigger, use the Lucide Settings gear, and retain the existing dialog and safe focus return. Verify shell, settings, notification, feedback and localization tests.
3. Inspect desktop/narrow layouts and dark appearance, obtain an independent branch review, then commit and fast-forward main.
4. Preserve deployment state and private configuration, run the standard publisher checks/build/backup/activation, verify the external site, and leave the original local report preview running.
