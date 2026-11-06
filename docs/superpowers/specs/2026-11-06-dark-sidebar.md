# Dark academic navigation

The user asks to make the pictured shared sidebar dark, keep the whole interface
polished, push main and deploy externally. Use the established blue identity:
navy surface, soft white primary text, muted blue secondary text, a blue active
item with a fine light-blue indicator. Preserve the red/white crest asset.

Scope is the sidebar brand, navigation, dividers, account trigger and rail on
desktop and in the mobile Sheet. Keep main content, report cards, navigation
destinations, spacing, widths, auth and detection behavior unchanged.

Set sidebar-specific tokens on the actual sidebar surface so mobile portals
receive the same colors without enabling global dark mode. Remove hard-coded
light-theme brand and group text colors. Preserve visible keyboard focus and
readable normal, selected and hover states. Avoid extra decorative elements.

The user delegated the design and explicitly authorized main/deployment; this
is a bounded visual change, not an options/approval exercise. No new assets,
dependencies, backend changes or new style-mirroring unit tests are needed.
Validate existing shell/navigation tests, typecheck, production build and the
actual interface before merging and deploying with the guarded release CLI.
