# Delivery-ready login alternatives

User requirement: continue development now; a leader will later select either login page; either selection must be deliverable without reverting business features. The earlier instruction not to change main remains binding.

Use one application source and the existing auth implementation, with a build-time `VITE_LOGIN_VARIANT=campus|split` selection. Default to campus, matching main. Preserve the approved campus artwork/card/water and the approved formal illustration/card/language placement. Do not change product wording. The existing preview remains split on port 443; main and port 3000 remain untouched.

Alternatives considered: keeping two divergent application copies makes later business parity fragile; selecting a login through a runtime API adds an unnecessary request and can disagree with early image preload. Build selection keeps business source identical, uses the normal backend for final delivery, and requires no new runtime service for the selected official site.

The build must record its selected login in `login-variant.json`. The backend must read that same manifest when choosing the HTTP preload, reject malformed/unknown manifests, and preserve the previous campus behavior for legacy builds without a manifest. Both variants must share jAccount entry, error recovery, report return validation, trial entry and session flow.

Delivery checks: build and test both variants from one commit; check that only the chosen page/image is mounted, inspect Chinese/English layouts at representative breakpoints, verify image preload matches the build, and preserve static cache/404/API/security boundaries. Record repeatable selection, synchronization and deployment instructions. Current preview jAccount callback and shared trial rate-limit limitations are documented; final delivery uses the ordinary backend and registered official callback, not the preview proxy. A real credentialed jAccount round trip still requires a real authorized account for acceptance testing.
