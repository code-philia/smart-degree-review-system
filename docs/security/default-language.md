# Default interface language

jAccount sign-in continues to request `essential`; this change does not silently request broader scopes. The provider's documented `identities[].gjm` is optional in practice. If the authorized response omits it, no nationality is inferred from a name, ID, account, email, institution or browser.

Only recognized codes are used, using the pinned ISO alpha-2/alpha-3/M49 code table from [UN Statistics Division](https://unstats.un.org/unsd/methodology/m49/overview/) retrieved 2026-11-12. `CN`, `CHN`, `156` select Chinese; other recognized codes select English. Region-only HK/MO/TW aliases do not by themselves establish nationality and leave the language unchanged. Empty, invalid, unrecognized or conflicting identity data does not select a language. A single explicitly default identity is authoritative; otherwise known identities must agree on the resulting language.

The application stores only nullable `auth_users.default_locale` (`zh` or `en`), not nationality codes or full provider profiles. The additive migration is idempotent and does not backfill historical users by guessing. A later valid provider response can update the default; a missing value preserves a previously established default.

Language priority is:

1. An explicit existing report/email `?lang=zh|en` link for that navigation.
2. A language the user explicitly selected in this browser, including existing saved choices.
3. The authenticated jAccount default, applied before authenticated content renders.
4. The browser language for visitors with no existing choice; Chinese locales select Chinese, other locales select English, unavailable browser metadata falls back to Chinese.

Automatic defaults never write the existing manual-language storage key. Switching between accounts therefore cannot turn an automatic default into a permanent manual choice. Manual settings retain their existing browser-local persistence; this change does not introduce cross-device preference synchronization. Unknown nationality retains the current language. Local trial accounts have no nationality and retain their existing language flow.

The interface continues to use the selected language for report explanations, exports and notification submission language. Detection inputs, prompts, rules and original source quotations are unchanged. No translation model is used to select an interface language.

Provider-field availability must be distinguished from application tests: protocol integration fixtures verify authenticated country metadata handling, while a live user's actual default changes only after their authorized jAccount login returns usable metadata. Missing metadata never prevents sign-in.
