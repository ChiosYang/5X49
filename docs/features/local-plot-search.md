# Local synopsis search in Explore

Status: Done

Default Explore accepts a remembered plot in English or Chinese. A result displays
a quoted passage from the current library synopsis. The library needs no API key,
model download or separate indexing job.

- Literal titles, people, keyword matches and complete factual searches retain priority.
- Interpretation identifies a plot request. The separate local read reparses the
  original question and applies supported hard filters in SQLite before retrieval.
  An unresolved constraint cannot become a broader list of films.
- BM25 ranks current synopses. Admission requires a matching phrase or multiple
  supporting terms together in a passage. A small colloquial vocabulary supports
  some paraphrases. Up to five cards show the source text, including on reload.
- Empty or unsupported synopses yield no cards. Results are lexical and depend on
  the wording and language available in the library. Each read processes the
  eligible synopses in memory. The optional model evaluation uses its own settings.

Verified against 64 public film synopses and isolated SQLite route tests, including
strict year and duration boundaries and a synopsis update between reads. Eight
English and Chinese real-API browser cases passed, covering quotes, empty results,
reload, history and existing search fallbacks. Frontend unit tests, lint, type
checking and the production build passed. Large private libraries have not been
benchmarked.
