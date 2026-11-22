# Reference type advisory wording

User supplied exact Chinese message and suggestion for rule31. Apply the invalid-code message globally to future detector results, and the advisory suggestion to both invalid/missing-type findings. Keep the distinction between invalid code and absent code, the existing code tables, severity, IDs, counts and source positions. Synchronize deterministic English and repair-generation guidance.

For saved reports, project only the two exact legacy defaults to the new copy during repository reads. Never rewrite database JSON or replace custom suggestions. The linked saved report is 96c6609d-6544-4d29-80d7-d777b9b7a7dd (six findings, five invalid codes and one missing code).

1. Add failing native detector, English copy, and stored-report projection tests.
2. Update the two detector strings, narrowly scoped saved-response projection, English dictionary and repair prompt.
3. Run relevant native/backend/frontend tests and a real-PDF before/after comparison allowing only the requested prose changes. Preserve saved data.
4. Obtain independent review, push main and deploy external through the unchanged Publisher; verify stored rows, private settings, static resources and requested copy.
