# Local-first portability contract

`library-export.v1` is a deterministic, read-only export boundary for 5X49.
It is a portable snapshot, not a database backup, event log, import format or
multi-device synchronization protocol.

## Commands

Run from `backend/`:

```powershell
python -m app.portability export --output data/exports/library-export.zip
python -m app.portability validate --input data/exports/library-export.zip
```

Export refuses to overwrite an existing file. Validation never extracts the
archive and rejects unexpected, duplicate, oversized or path-traversing ZIP
members, duplicate JSON keys, unsupported epochs/contracts and digest drift.

## Package shape

The ZIP contains exactly:

- `manifest.json`: contract and schema versions, database epoch, content
  digest, export time and explicitly empty future-sync version fields.
- `library.json`: canonical Film knowledge and portable personal state.

The content digest is the SHA-256 of the canonical UTF-8 `library.json` bytes.
It is stable for equal database state; export time and ZIP metadata do not
participate in that digest. ZIP member timestamps are fixed for reproducible
packaging behavior.

Included data:

- active Canonical Films, portable titles and exact external identities;
- FilmProfileState and Viewing facts for the local profile;
- user-curated title, country and Credit metadata;
- user accepted/rejected Assertion decisions and the bounded Person/Concept
  records needed to identify their targets.

Excluded data:

- media files, LibraryItem locators, source item keys and absolute paths;
- NFO/XML documents, artwork caches and provider payloads;
- Settings, API keys and other credentials;
- Job, Workflow, EventRecord, OperationSnapshot and Read Model rows;
- model prompts/responses, hidden reasoning, web page bodies and operational
  provenance references.

## Safety and future boundary

Export opens a normal database session but issues only SELECT statements. It
does not update migrations, projections, timestamps or media. Automated tests
compare the SQLite file hash before and after repeated export.

The manifest reserves `device_identity_version`,
`incremental_cursor_version`, `conflict_policy_version` and `logical_clock` as
explicit null values. Version 1 does not implement import, device identity,
incremental cursors, CRDTs, logical clocks or conflict merging. Any import or
sync feature requires a separate threat model and versioned contract.
