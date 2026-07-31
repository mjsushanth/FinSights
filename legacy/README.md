# legacy/

Archived clutter moved out of the FinSights repo root. Kept for history only —
nothing here is active.

## Duplicate root ignore files (archived 2026-07-27)

macOS created ` 2`-suffixed duplicate copies of the root ignore files at some
point. The live, maintained versions remain at the repo root
(`.gitignore`, `.dvcignore`). These archived copies were verified redundant
before moving and are **inert** here (git only honors an ignore file named
exactly `.gitignore` / `.dvcignore`):

- `gitignore.old` — was `.gitignore 2` (2026-06-28, 4,773 B). The live root
  `.gitignore` (2026-07-27, 6,747 B) is a strict superset — this old copy
  contained no unique rules.
- `dvcignore.old` — was `.dvcignore 2` (2026-06-28). Byte-identical to the
  live root `.dvcignore` (the default DVC template).
