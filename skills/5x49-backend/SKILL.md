---
name: 5x49-backend
description: 5X49 Fresh Canonical FastAPI 的 Film、LibraryItem、Factual Explore、Ask、Viewing、Analysis 与运维接口调用指南
---

# 5X49 Backend API

## Unified Explore search

- `POST /explore/search/interpret`: `{question,locale,allow_ai:false}`; text 1–600,
  strict boolean. Keyword/local rules are model-free. Only explicit submission may
  set allow_ai true; at most one existing transport call, no retry, no library input.
- `POST /explore/search/query`: `{question,plan,person_id:null,edited:false,offset:0}`;
  always local, 40/page. Ask v1 remains compatible; exact roles and strict missing/conflict
  handling. Edited conditions reflect explicit user corrections, never partial AI.
- Envelope: discovery.v1, status, source, reason, plan, person_id, constraints,
  issues, results. Status keyword/ready/needs_clarification/clarify/unsupported/
  unavailable/needs_ai. Partial/duplicate identity needs a choice; unsupported/low-confidence/
  ungrounded/malformed interpretations never run a partial query. Safe errors only.
- Preserve literal Person names before filler/facet parsing. Unsupported roles
  (producer/writer/etc.) and language requests must not become director/country
  filters. Produced in France is a country clause; in French is a language clause.
  Absolute, home-relative, dot-relative and unprefixed relative media/sidecar
  paths are rejected before transport; slash-containing titles remain usable.
  Keyword lookup removes only an explicit leading find/找 command, retaining raw
  input for display/history and preserving inner title words.
- Refresh/Back/page/mutations must never infer. Keep global Library search and old
  exact Explore URL meanings. Ask UI redirects to Explore; old APIs stay compatible.
  PR28 and live-budget/review gates remain separate. No Jev dependency is added.


### Imported metadata search coverage

Complete local keyword/condition requests run before optional semantic runtime
configuration is loaded. Invalid evaluation configuration cannot block them;
explicit evaluation/edit/reference submissions retain their existing guards.

Local keyword lookup includes the effective synopsis as literal text, in addition
to existing titles and credited names. It does not infer themes, preferences or
hard metadata from synopsis words. Exact title/alias priority remains available
through `rank_exact=true`; strict role/country/year/runtime SQL is unchanged.
Search projection `film-search.v3` rebuilds from canonical data on normal startup
and refreshes transactionally after source edits; no provider request is needed.

Structured NFO/TMDB import retains the supplied cast beyond preview limits;
existing small actor previews remain unchanged. Kodi typed `uniqueid` tags can
supplement missing legacy TMDB/IMDb fields; ambiguous or unknown types are never
guessed. Existing explicit legacy IDs retain precedence.

Future explicit TMDB detail requests append alternative titles to that same
request. Source-backed alternatives use unknown language (`und`), never a
country-to-language guess. A valid complete alternative-title list replaces that
source's alternative snapshot; absent/malformed blocks preserve previous names,
and an explicit empty list retracts them. Other localized titles keep their
existing per-language lifecycle. No translation, name-based person merge, bulk
scrape, AI call, semantic-index rebuild or egress permission is introduced.

Older truncated source imports cannot be reconstructed from projections: the
missing cast/titles become available only on an ordinary explicit source refresh.

### Enhanced search phase one

- Exact known Film/Person names take precedence over request words. Shared Film
  search includes active source-backed FilmTitle names and credited Person aliases;
  NFKC/case/whitespace normalization, stable IDs, no translation or fuzzy merge.
  `GET /library/films/page?rank_exact=true` gives exact title/alias priority;
  default Library sorting is preserved. Schema v11 and film-search.v3 rebuild locally.
- New plans require `version:"search-plan.v2"`: genre/country include and exclude
  arrays (<=10 each), people clauses (<=8, literal name + any/actor/director +
  exclude), inclusive year_min/max 1870..2100, duration_min/max integer minutes
  1..10000 plus strict duration_min/max_exclusive booleans; existing view/sort/dir.
- Include facets are OR within a dimension; each person/role and every other
  condition is AND. SQL filters precede counts/sorting/page; duration keeps exact
  primary seconds then metadata fallback. Missing/conflicted facts fail positive
  and negative requirements. Do not infer exclusions from absent metadata.
- Discovery.v2 adds people_ids keyed by clause index; send that map on local
  query, not v1 person_id. Only exact aliases/canonical names auto-resolve; partial
  or duplicate names need a local candidate. Full original request grounding is
  mandatory unless explicit chip/view/sort corrections are marked edited.
- Existing TMDB name/original_name may populate aliases only through stable
  active external identities and existing metadata requests. No bulk enrichment,
  guessed aliases, AI identity rewriting or new credential dependency.
- Person alias supersession is scoped to the response locale (case-insensitive);
  another language's names survive. Removed/changed source identities retract all
  their locales. Original names use und. Year clauses intersect, never overwrite
  each other; contradictory years clarify without partial execution.
- Localized/alternative Film titles retain other response languages on refresh;
  same-language withdrawals retract their old search names. Canonical/original
  display-title selection is unchanged.
- Expanded provider schema is offline/mock only until a separately authorized
  real-model quality gate. Production v2 is local rules; existing guarded v1 AI
  fallback remains. No real model call, download or quality claim is authorized.
  No Ask workspace/manual form is reintroduced. See docs/api.md for full limits.

### Native semantic evaluation

- Literal requests may return `keyword_query` separately from the original input.
  Preserve full known title punctuation before consuming complete wrappers.
  Optional v2 `film_ids`/`exclude_film_ids` bind exact local identities, at most
  eight unique IDs each; unknown IDs stop execution. Restore must re-ground the
  original unedited plan. Reference IDs are excluded before ranking and again
  during restoration; leftover hard conditions cannot be silently discarded.
- Opt-in only: host `SEARCH_INTERNAL_EVALUATION=1` plus an absolute reviewed
  `SEARCH_EVALUATION_MANIFEST`. Free NVIDIA adapters are evaluation-only, with
  explicit approved public inputs/logging consent; never production/private
  fallback. Default startup, local keywords and complete SQL rules make no call.
- Native APIs: Mammoth SystemOne (`baseten/mammoth-1:free`, only `baseten`),
  NVIDIA query/passage embeddings and native rerank (the fixed Nemotron 3.5
  `:free` IDs, only `nvidia/bf16`). Preflight active/zero-price/privacy; no paid
  or provider fallback. One expiring, durable 320-POST grant across all three.
  Keep response evidence before billing validation; uncertainty stops dispatch.
- `discovery.v3` adds an opaque question/model/policy/corpus-bound snapshot and
  honest semantic/evaluation/fallback metadata. Query POST adds
  `semantic_snapshot`, `semantic_order` relevance/title/year. Restore, sorting,
  mutation, Back/Return and chip edits are entirely local. Unresolved identity
  choices require an explicit interpret POST with people_ids/reference_id;
  GET restoration never infers. No Ask/manual filter form.
- Content removal is an explicit `semantic_removed:true,edited:true` query with
  the original opaque snapshot retained as proof. Validate its question/model/
  policy/corpus binding before executing retained conditions in strict SQL.
  Missing proof cannot bypass original grounding. Bound-title chip/sort edits
  revalidate the complete original literal request, then validate corrected IDs.
- SQL eligibility precedes candidate counts/rerank/display. Reference-Film
  similarity resolves exact identity and uses indexed content, never title-only
  vectors. Unknown/missing hard facts are not assumed to match.
- `POST /explore/search/index`: explicit begin/status/step/resume/cancel with
  idx_ ID, at most four chunks per step. Separate cache only, cancellation and
  exact provider/mode/text reuse; no source metadata write. Historical scalar
  provenance needs reviewed public-field hashes, not a blanket TMDB flag.
- Missing/expired/stale index or provider failures preserve ordinary search.
  Internal-evaluation real contract checks are not independent semantic quality
  or production acceptance; PR28 and earlier Qwen accounting stay separate.
  Full limits and response shapes are in docs/api.md.

## Addressable local collections

- `GET /explore/catalog`: optional `category=all|director|country|decade`, literal
  bilingual `q` (200 max), `featured` (false), `limit` (1–24), `offset` (>=0).
  Returns `items,total,limit,offset,next_offset,total_films,categories,strict`.
  Directory entries require two eligible local Films. Featured entries balance
  categories, suppress >=85% membership overlap and never repeat preview Films.
- `GET /explore/collections/{kind}/{key}`: kind is `director|person|country|decade`;
  key is canonical Person ID, ISO country code or release-year decade. Returns
  `{collection,results}`; unknown/empty definitions are 404, invalid IDs are 422.
  Collection fields: `id,kind,key,label,count,unwatched_count,previews` (up to four
  existing Library Film summaries). Identity and count use All, independent of
  temporary `view,sort,dir,limit,offset`. Results retain the strict Film page contract.
  Director membership requires an accepted director role; Person means actor OR
  director for the same canonical identity. Conflicted/missing facts never match.
- Old `/explore/collections`, `/explore/films` and Person All/Any contracts remain
  unchanged. No inferred series, external catalog, AI or new persistence is involved.

## Multiple media roots

- Preference PUTs write only their owned Setting rows transactionally. Root writes
  update `media_dirs` plus legacy `media_dir` together; URL/model/TMDB/language and
  toggle writes preserve other rows. Clearing TMDB removes only its key. Ordinary
  preference reads/writes do not refresh models or test credentials. Model-list
  reads/explicit refresh and connection testing remain separate operations.

- GET/PUT `/settings/media-dirs`: ordered `{media_dirs: string[]}`; GET also
  reports `roots: [{id,path,state}]`. Save absolute backend-host paths (maximum
  32), canonicalize/deduplicate, reject overlapping parent/child roots. Offline
  roots are allowed; `[]` disables access. Saving never scans or moves files.
- Legacy `/settings/media-dir` reads/replaces only the first root and retains
  its existing readable-directory requirement. An absent list falls back to
  legacy settings/MEDIA_DIR; settings read failures fail closed. Removing a root
  stops its access and queued work, preserving all identities and personal data.
- `/library/scan` and `/library/reconcile` recurse across all roots, including
  direct-root videos; optional `media_dir` must be an exact configured root.
  `/library/scan-folder` targets must remain within configured roots. Watchers
  cover the same nested tree. Hidden directories, links and junctions are skipped.
- `/library/sync/status` adds `complete,incomplete_roots,roots` to sync.last_result;
  each root has `id,state,scanned,added,errors,skipped_links`. States distinguish
  complete/partial/offline/permission_denied/unavailable/not_scanned/interrupted.
  Receipts survive restart. Accessibility is separate from saved configuration
  and from historical coverage. A partial result is not a successful full scan.
- Any failed root/cancellation suppresses missing reconciliation for the run;
  positive discoveries may persist. Only complete coverage and explicit absence
  under a still accessible root can mark an edition missing. Removed/offline
  roots never authorize deletion or cross-Film merging. Same-Film reconnection
  and the cross-Film manual-metadata block remain mandatory.
- Artwork uses `/media/_roots/{root_id}/{full-relative-path}`; legacy `/media/*`
  uses the first root. Removed roots are immediately revoked. Queued manifests,
  scraping, organizer writes and identity decisions revalidate current bounds.
  Root organizer UI uses the first root; each watcher uses its own root.
- Database backups still exclude all Setting rows, including root configuration
  and scan receipts; restoring requires explicit media reconfiguration.

## Maintenance database backups

- GET `/maintenance/backups` reads separate `last_attempt` / `last_success` state.
  POST the same route with a fresh 32-lowercase-hex `request_id` to generate;
  replay the same ID after uncertain delivery. GET `/{id}` polls that receipt.
- GET `/{id}/download` returns a verified SQLite+v1 manifest+RESTORE.txt ZIP.
  POST `/{id}/download-triggered` only records a browser-reported trigger; never
  call it proof of disk saving. These are not the portable JSON export endpoints.
- The user-approved package excludes the entire Setting table, credentials,
  external configuration, artwork/media/NFO files and external operation manifests.
  Personal metadata, edit history, Film reviews and Viewing reviews are preserved.
  Diagnostic content is sanitized, derived projections rebuild on startup, and
  unsafe personal-content redaction causes refusal. File-organization undo is
  expired; recovery requires configuring directories/API keys again.
- Active jobs/workflows/analysis in the snapshot refuse packaging. Wait for them
  to finish; never use a real reset to make a backup possible. Restore uses the
  existing offline CLI after a fresh isolated rehearsal, with watchers disabled.
- Only the latest success is downloadable for 24 hours. Failed/interrupted/new
  attempts do not erase the old success. OS locks and durable request receipts
  cover concurrency and restart; expiry, missing and corrupt artifacts are distinct
  from historical generation success. No live restore or source mutation occurs.
- Codes, fields and retention/cleanup semantics are documented in `docs/api.md`.

## Deterministic Library filters

- `/library/films/page` intersects `q`, legacy `filter`, independent `favorite=true`,
  `duration_min/max` (integer minutes 1–10000), `year_min/max` (1870–2100),
  `rating_min/max` (integer personal overall stars 1–5), and
  metadata status before count/sort/pagination. The response shape is unchanged.
- Bounds include endpoints; an omitted bound is unlimited. Active ranges exclude
  unknown values. Invalid/out-of-domain/reversed ranges return 422.
- Duration uses positive primary-edition measured seconds, then positive Film
  runtime minutes. Compare exact seconds to minute bounds; use the same duration
  for sorting and keep unknowns last in both directions.
- Year uses the current effective metadata, including manual overrides/nulls.
  Reads never modify protection, Film data, NFO files or provider state.
- Rating uses only FilmProfileState.rating. Never use external scores or per-
  Viewing reviews as substitutes. Active rating ranges exclude unrated Films.
- Existing filter=favorite links remain valid. For watched favorites, use
  `filter=watched&favorite=true`. Sort ties and pagination remain deterministic.

## Per-viewing reviews

- Schema v9 adds nullable Viewing `rating` (integer 1–5) and `notes` (up to
  10,000 characters, without NUL), returned by both Viewing list APIs.
- Migration does not attribute or copy historical FilmProfileState reviews.
  Viewing and Film reviews are independent; neither direction synchronizes.
- POST requires `watched_at`, with optional `rating`/`notes`. PATCH accepts a
  nonempty subset; omission preserves and null clears. Whitespace notes clear.
- Retain the GET `revision` when opening a form. PATCH requires it in JSON;
  DELETE requires it in the query. Missing/stale revisions return 409: reload
  before editing. This deliberately rejects old unversioned edits/deletes.
- Send a fresh 16–64 character ASCII `idempotency_key` per POST/PATCH operation;
  review writes require it. Retry an uncertain write with identical body/key.
  Receipts persist across restart. Reused keys with different payloads or with
  subsequently changed/deleted results return 409; they never overwrite data.
- Manual watched off/on restores the same record including unknown date and
  review. Quick diary creation leaves review fields empty unless supplied.
- `library-export.v1` exports the fields and validates both new rows and old
  rows that omit them. Retry receipts are private operational state, not exports.

## Database-only basic metadata editing

- GET `/films/{film_id}/metadata` before editing; retain its opaque `revision`.
  Fields `title`, `original_title`, `year`, `overview` expose current/automatic
  values, per-field `manual` protection and safe automatic source summaries.
- PATCH the same path with `revision`, a 16..64 ASCII alphanumeric/underscore/
  hyphen `idempotency_key`, and only changed fields under `changes`. Each change
  is `{action:"set",value:...}` or `{action:"reset"}` without value.
- Trimmed title is required and at most 300 characters; original title allows
  300, synopsis 10000. Blank optional text normalizes to protected null. Year
  accepts strict integers 1870–2100 or protected null. Reset removes protection
  and uses the latest automatic source, not the source from the first edit.
- Never edit TMDB/IMDb IDs or personal fields through this API. No NFO/media
  writes occur. Source data and each edit's automatic snapshot are retained.
- Reuse the same body/key after uncertain delivery. Successful retries return
  current state with `replayed:true` without applying the edit again. Stale
  versions and conflicting retries return 409 with `detail.code`; refresh and
  explicitly review before making a new request. Invalid input is 422, missing
  Film 404, contention 503, persistence failure 500. Writes are transactional.
- Any manual field prevents moving an edition from its Film to another Film;
  reset every manual field before retrying identity matching. No implicit
  correction transfer/merge occurs. Historical year/synopsis source is honestly
  labelled `library` when more precise provenance was never recorded.
- `library-export.v1` optionally includes `curated_metadata.manual_overrides`;
  existing exports without it remain valid. See `docs/api.md` for the contract.

## Identity review and conservative decisions

- `GET /library/identity-reviews?status=open&limit=40&offset=0` returns
  `items,total,limit,offset`; status also accepts resolved, dismissed and all.
- `GET /library/identity-reviews/irev_<32 lowercase hex>` returns conflict reason,
  Film/edition previews, saved candidate comparisons and personal-data flags/counts.
- Invalid IDs/queries return 422; absent IDs return 404. Unknown reasons map to
  `unknown`. `evidence_available=false` means a historical review lacks candidates;
  `candidates_truncated=true` means the retained 50-candidate preview is incomplete.
- Candidate `evidence_status` compares database records, not current files.
  No paths or notes content appear. Reads do not invoke providers or mutate data.
- `actions` lists `keep_separate` and/or `reconnect` when eligible; `blocked_code`
  explains why historical, changed, incomplete or identity-conflict evidence is
  inspection-only. This queue is distinct from TMDB scrape candidates.
- POST `.../{review_id}/preview` with `action` and (only for reconnect)
  `target_item_id`; retain its `confirmation_token`. Preview reads source files
  under the configured root and writes nothing.
- POST `.../{review_id}/confirm` with the same request, token and a 16..64 character
  ASCII alphanumeric/underscore/hyphen `idempotency_key`. Reuse the exact payload
  and key after a lost response. A conflicting replay or stale evidence is 409
  with `detail.code`; invalid body is 422, absent review 404.
- Keep separate dismisses only this review. Reconnect keeps an existing edition
  ID in the same Film/profile, requires its old file to be absent and complete
  hashes to match, and retains the new discovery/assets as retired history.
  A preferred-edition pointer to the discovery follows the preserved target.
  Preview lists `effects.expiring_snapshot_ids`; prior undo actions for the two
  editions expire on reconnect, retaining their audit/history and manifests.
  Ratings, notes, favorites and Viewing ownership never change. No file moves,
  deletion, provider reassignment or cross-Film merge/split is available.
- Confirmation, decision record and `IdentityReviewDecided` audit event are
  atomic. Reads and writes retain historical candidate evidence; unchanged scans
  neither reopen nor recreate the decided review. See `docs/api.md` and
  `docs/features/identity-review.md` for the complete contract.

## 基础契约

- 后端默认地址：`http://127.0.0.1:8000`。
- 前端开发地址：`http://127.0.0.1:5549`，代理 `/api/*` 与 `/media/*`。
- Film ID：`film_<32 lowercase hex>`。
- LibraryItem ID：`lib_<32 lowercase hex>`。
- OperationSnapshot ID：`snap_<32 lowercase hex>`。
- 一部 Film 可以有多个 LibraryItem；Film 级状态、元数据、评分和分析只保存一份。
- 当前为 `fresh-canonical-v1`，不存在 Movie ID、Legacy alias、双读/双写或 Shadow 回退。

具体请求模型以 `/docs` OpenAPI 为准；稳定架构说明见 `docs/api.md`、
`docs/domain-model.md` 与 `docs/event-contracts.md`。

## 资料库

```bash
curl -s http://127.0.0.1:8000/library/films
curl -s http://127.0.0.1:8000/library/films/film_0123456789abcdef0123456789abcdef
curl -s http://127.0.0.1:8000/library/missing
curl -s http://127.0.0.1:8000/films/film_0123456789abcdef0123456789abcdef/graph
curl -s -X POST http://127.0.0.1:8000/library/reconcile
curl -s -X POST http://127.0.0.1:8000/library/items/lib_0123456789abcdef0123456789abcdef/refresh
curl -s -X POST http://127.0.0.1:8000/library/items/lib_0123456789abcdef0123456789abcdef/ignore
```

- `GET /library/films` 一部 Film 一项，直接包含 profile state 和 primary edition。
- `GET /library/films/{film_id}` 返回全部非 retired editions。
- `GET /library/films/page` 是有界片库／搜索读取：`q`、
  `filter=all|watched|unwatched|favorite`、`sort=title|added|duration`、
  `direction=asc|desc`、`metadata_status`、`limit`（默认 40，最大 100）、
  `offset`（最大 1000000）。返回 `items,total,library_total,metadata_reviews,limit,offset`；
  过滤在分页前执行，越界 offset 归到最后有效页。旧数组接口保留。
- `PUT /films/{film_id}/primary-edition` 接受 `library_item_id`，只选择属于该 Film
  且可用的版本；跨 Film／缺失为 `404`，不可用为 `409`。默认版本偏好持久化，
  扫描时间不影响选择；不可用时回退，新增偏好保存在 Schema v6。
- 同目录独立视频按版本导入，匹配同名 NFO 后再用 `movie.nfo`；多视频目录不借用
  另一个视频的 NFO。常见附属视频后缀不导入；从 1 开始的连续 CD／Disc／Disk／Part
  分段视为一个版本，各段都有独立 NFO 时分开。`video.part_files` 只包含文件名。
- `GET /films/{film_id}/graph` 只从同步 Read Model 返回一跳、定长的
  accepted factual 图谱；Gate B 前不会暴露 inferred/proposed 关系。
- `POST /library/scan` 与 `/library/reconcile` 返回 queued Job。
- `POST /library/scan-folder?folder_path=...` 只允许媒体根内目标。
- `GET /library/missing` 返回缺失 LibraryItem 的安全摘要与准确数量，不暴露路径。
- `DELETE /library/missing` 退休 missing editions。
- `DELETE /library` 退休收藏但保留 Film 级数据。
- `DELETE /library/data` 彻底删除领域数据，但保留设置、迁移 journal 和固定词表。

不要从 Event/Job 中查找绝对路径；路径只存在于受控、Git ignored 的私有 manifest。

## Factual Explore

```bash
curl -s http://127.0.0.1:8000/explore
curl -s "http://127.0.0.1:8000/explore/context?genre=con_0123456789abcdef0123456789abcdef&view=all&limit=6"
curl -s "http://127.0.0.1:8000/explore/facets/person?q=kurosawa&limit=30&offset=0"
curl -s "http://127.0.0.1:8000/explore/films?genre=con_0123456789abcdef0123456789abcdef&country=JP&decade=1950&view=unwatched&sort=year"
```

- `GET /explore` 返回四维覆盖率与每维前 12 个事实。
- `GET /explore/context` 复用四类重复事实参数和 `view`，并接受每维
  `limit=1..12`（默认 6）。目标维度为空时以 AND 计算 `result_count`；已有值时
  以 OR 计算精确 `additional_count`。已选和 conflicted 事实不会作为线索返回。
  `preview_film` 必须来自该线索的实际贡献集合，OR 优先新增影片；只含公开 Film
  身份与安全 artwork 字段。实现是固定批量读取，不得按 facet 发起 N+1 查询。
- `GET /explore/facets/{dimension}` 分页查询 `genre|person|country|decade`；
  Person 的导演/演员统一返回，并在 `roles` 中标识。
- `GET /explore/films` 支持每维最多 20 个重复参数；同维 OR、跨维 AND，再与
  `view=all|watched|unwatched` 做 AND。默认每页 40、最大 100。
- URL 中 Genre 使用 Canonical `con_` ID（`concept_` 输入会归一化），Person
  使用 `person_` ID，Country 使用 ISO alpha-2，
  Decade 使用四位且以 0 结尾的 key。畸形输入返回 `422`。
- 格式合法但缺失、删除、冲突或不可用的事实保留在 `unresolved_filters`；若该维
  全部 unresolved，结果严格为零，不会静默放宽。
- 响应只来自 Schema v4 同步 Read Model，visibility policy 为
  `factual-explore.v1`。投影缺失或版本不符返回 `503 projection_unavailable`，
  不回退到 Canonical live join，也不会调用模型或网络。
- `matched_facts` 只包含安全来源种类/策略或
  `release-year-decade.v1` 派生说明，不包含 source ref、路径、provider payload
  或凭据。

### Browse and People combination contract (2026-10-21)

- `GET /explore/collections?view=all&limit=6` returns deterministic nonempty local
  entries (`dimension`, `key`, `label`, `view`, exact `count`, safe `preview_film`),
  `total_films`, and the existing projection/policy metadata. Limits are 1..12.
  Country entries use Unwatched from All; other entries preserve the view.
  Identical Film sets are deduplicated. Empty/sparse Libraries may return no entries.
  No model, external catalogue, inferred facts or automatic relaxation is involved.
- Films and Context accept `person_match=any|all` (API default Any for old links).
  All requires each selected canonical Person, as Actor or Director, on the Film.
  One unavailable Person makes All empty. Genre/Country/Decade remain OR within
  their dimension; dimensions and watched state remain AND. Filters are deduplicated.
- Context uses `operator=and` and exact intersection `result_count` for People All;
  existing Any context expansion remains compatible. Film `active_filters` echoes mode.
- Facet `q` searches literal labels and bundled bilingual Genre/Country aliases;
  Decades accept `1990s`/`1990年代`. Wildcards are literal. It is not semantic search.
  The UI searches all four categories with debounce and separate facet pagination.
- Collections use at most six bulk SQL statements; filtered pages skip suggestions.
  Coverage remains in the existing API but is absent from the primary Explore UI.


## Profile State 与 Diary

```bash
curl -s http://127.0.0.1:8000/films/<film_id>/profile-state
curl -s -X PUT http://127.0.0.1:8000/films/<film_id>/profile-state \
  -H "Content-Type: application/json" \
  -d '{"watched":true,"rating":5,"favorite":true,"notes":"..."}'
curl -s "http://127.0.0.1:8000/profile/viewings?limit=100&offset=0"
curl -s "http://127.0.0.1:8000/profile/viewings?view=recent&limit=100&offset=0"
curl -s http://127.0.0.1:8000/films/<film_id>/viewings
curl -s -X POST http://127.0.0.1:8000/films/<film_id>/viewings \
  -H "Content-Type: application/json" -d '{"watched_at":"2026-08-31"}'
curl -s -X PATCH http://127.0.0.1:8000/viewings/<viewing_id> \
  -H "Content-Type: application/json" -d '{"watched_at":"2026","revision":"<revision from GET>","idempotency_key":"viewing-edit-0001"}'
curl -s -X DELETE "http://127.0.0.1:8000/viewings/<viewing_id>?revision=<revision from GET>"
```

`watched=true` 创建或恢复 manual confirmed Viewing；`watched=false` 只撤销
manual Viewing，不删除 Diary 等其他来源。最终 watched 由任意 active confirmed
Viewing 推导；`manual_watched` 只表示快捷开关对应的 manual Viewing 是否存在。

Diary 的 POST 每次都创建一条独立 `source=diary` 记录，同日记录也不合并。
日期接受 `YYYY-MM-DD`、`YYYY`、带时区的 RFC 3339 timestamp 或 `null`。manual
与 diary 来源可 PATCH/DELETE；外部来源返回 `409 viewing_read_only`。DELETE 是
幂等软删除。`/profile/viewings?view=timeline` 返回完整时间线，`view=recent` 在分页
前为每部 Film 选择最新一条；逐片管理也可使用 `/films/{film_id}/viewings`。

## TMDB、Artwork 与外部评分

```bash
curl -s "http://127.0.0.1:8000/metadata/search?query=Inception&year=2010"
curl -s http://127.0.0.1:8000/metadata/movie/27205
curl -s -X POST http://127.0.0.1:8000/films/<film_id>/scrape \
  -H "Content-Type: application/json" -d '{}'
curl -s http://127.0.0.1:8000/films/<film_id>/scrape/candidates
curl -s http://127.0.0.1:8000/films/<film_id>/artwork
curl -s -X PUT http://127.0.0.1:8000/films/<film_id>/artwork \
  -H "Content-Type: application/json" \
  -d '{"poster_path":"/poster.jpg","backdrop_path":"/backdrop.jpg"}'
curl -s -X POST http://127.0.0.1:8000/films/<film_id>/external-scores/refresh
```

TMDB 功能需要 `TMDB_API_KEY` 环境变量或托管设置；读取设置只返回配置状态，
不会返回明文密钥。低置信度或启用确认策略时，通过
`POST /films/{film_id}/scrape/confirm?tmdb_id=...` 明确确认。先扫描的不同版本在确认
相同 TMDB/IMDb 身份后归于同一 Film；响应 `film_id`/`film.id` 是规范身份，旧 Film
详情 ID 保留为别名，版本 ID 保持稳定。重复扫描保留刮削时间、置信度及失败／待确认
状态。普通待确认不设置 `scrape_error`；无结果刮削返回 HTTP 409、
`detail.message = "No TMDB matches found"`，并记录 `failed`。
`GET /films/{film_id}/scrape/candidates` 只读取可用 Film 版本并返回有界候选，
不会修改刮削状态、写 Event/NFO、下载图片或自动确认。

## Ask 只读查片

- `GET /ask/status` 只报告模型 Key 是否存在；不能据此认定模型可用。
- `POST /ask/interpret` 接受 `question`（1–600 字符）与 `locale: zh|en`。
  只发送问题和固定 schema；不附带片库、笔记、路径或查询结果。
- `POST /ask/resolve` 接受 `plan` 与可选 `person_id`，在本地解析和预览条件。
- `plan` 支持一个 `genre`、一个 `person`、`person_role: any|director|actor`、
  一个 `country`、一个 `decade`、`view: all|watched|unwatched`、
  `sort: title|year` 与 `direction: asc|desc`；不同维度之间为 AND。
- 同名/部分匹配人物必须从返回的候选中明确选择；未知条件不能忽略。
- `POST /ask/query` 使用相同参数，加 `confirmed: true` 和可选 `offset`。
  只有用户确认条件后执行；每页 20 条，分页无模型调用。
- `status` 为 `ready|needs_clarification|clarify|unsupported`。未解决的条件
  返回 `results: null`，零结果不会自动放宽。命中原因来自 `matched_facts`。
- 无 Key 时直接使用 resolve/query；不支持评分、精确年份、否定、OR、多值维度、
  推荐或写操作。Ask 不保存提问/模型输出，也不产生含这些内容的 Activity 事件。
- `ask_private_input`、`ask_invalid_response` 等错误不得通过删减约束重试。
  完整请求、错误码和提供商限制见 `docs/api.md` 的 Ask MVP。

## Analysis V2

### 本地审核与纠错

- `GET /films/{film_id}/analysis-review?offset=0&limit=50` 返回跨分析运行的
  `relations`、`reviews` 和 `next_offset`，包含拒绝记录与用户修正关系；最大页长 100。
- 每条记录包含 `revision`；写入前读取当前记录，过期版本返回 `409 stale_review`。
- `PUT /films/{film_id}/assertions/{assertion_id}/review` 接受
  `revision`、`decision: accepted|rejected`。纠错使用 `rejected` 并附带
  `correction: {predicate, target_entity_id, direction}`，原关系拒绝与新关系接受原子提交。
- `GET /films/{film_id}/analysis-review/targets?predicate=...&q=...` 查询最多 30 个
  已有对象；引用匹配可附带 `entity_type=film|person|concept`。
- `PUT /films/{film_id}/analysis-reviews/{review_id}` 使用 `revision` 与
  `action: resolve|dismiss|reopen`。仅 `resolve` 需要 `correction`；
  assertion 复核创建用户策展关系，entity_reference 复核只记录对象匹配。
- 不允许创建新实体、绕过关系类型/方向约束、给修正关系复制旧证据，或在此将网络证据标记为有效。
  Evidence/output 复核只可忽略或重新打开。重新打开复核不会撤销已建立的关系。
- 已接受/拒绝决定及相同候选的已关闭复核会保留；Gate B 阻塞期间不改变事实图谱的展示边界。
- 搜索使用 `/library/films?q=...`；`%`、`_` 按普通字符匹配。
  评分/笔记仍使用 profile-state API，`null` 清空字段，Activity 不复制笔记正文。

完整错误码与请求边界见 `docs/api.md` 的 Local Analysis review。

```bash
curl -s -X POST http://127.0.0.1:8000/films/<film_id>/analysis-runs
curl -s http://127.0.0.1:8000/films/<film_id>/analysis
```

分析 Workflow 直接写入 AnalysisRun、Assertion、Evidence 与 resolution review。
读取接口返回结构化 `FilmAnalysisView`；不要寻找 raw response、hidden reasoning
或兼容分析 JSON。模型运行需要现有 OpenRouter/OpenAI-compatible 配置；TMDB Key
只用于验证尚未存在的精确电影身份。
模型候选必须先通过 `analysis-policy-critic.v1`；身份/标题/年份矛盾、类型或
方向错误、自引用、Concept alias 歧义、qualifier、语义重复及超出 8 条的候选
进入 review，不得绕过 Critic 直接持久化。

## Activity、恢复与 Workflows

```bash
curl -s "http://127.0.0.1:8000/activity/events?aggregate_type=film&limit=50"
curl -s http://127.0.0.1:8000/operations/<snapshot_id>/preview
curl -s -X POST http://127.0.0.1:8000/operations/<snapshot_id>/restore \
  -H "Content-Type: application/json" \
  -d '{"confirmation_token":"<64 lowercase hex>"}'
curl -s http://127.0.0.1:8000/workflows
curl -s http://127.0.0.1:8000/workflows/<workflow_id>
```

- Activity 可按 `aggregate_type`、`aggregate_id`、`type`、`command_id`、
  `correlation_id` 和 `limit` 过滤。
- `/library/events` 是实时 SSE，不是持久审计来源。
- Restore 必须先 preview；状态漂移、旧 token、重复恢复或文件冲突返回 `409`。
- Workflow/Step 的公开结果已脱敏，不暴露路径、标题、密钥、原始模型输出或完整 dedupe key。
- `GET /workflows?limit=8&include_active=true` 在最近记录之外保留全部 queued/running 任务；显式 status 过滤时仍按 limit 限制，type 过滤继续生效。
- Job 仅为内部单步骤执行队列，没有公开 HTTP/SSE DTO。

## 设置与维护

- `GET /diagnostics` 只读检查 SQLite、Schema、读取模型就绪状态、媒体权限及备份
  空间估算，不返回路径或凭据，不迁移／修复，也不等于完整投影一致性校验。
- `GET /diagnostics/providers` 主动测试固定 TMDB `5511` 的详情和小海报；只返回
  安全状态与 HTTP 状态码，区分凭据、访问策略、限流、代理、CA、超时故障。
  保留 TLS 校验和 Network secret 的既有注入方式，无重定向及隐式重试。
  后端通过不代表浏览器已信任代理 CA。

- `/settings/*` 管理语言、媒体目录、watcher、刮削确认、TMDB 和模型。
- `GET /settings/media-dir` 返回 `media_dir`、`exists` 和 `readable`，只报告
  当前根目录的可用性，不枚举目录内容。
- `PUT /settings/media-dir` 只接受存在且可读的目录；保存后 `/media/*`
  立即使用新根目录，无需重启后端。媒体路由不得接受绝对路径、路径穿越或
  逃逸到根目录外的符号链接。
- `/library/organization/candidates` 同时列出媒体根目录与旧 `inbox` 的待整理文件，
  只返回相对 `source_path`；手动操作必须依次调用
  `/library/organization/preview` 与 `/library/organization/confirm`。
- `/library/organize-root` 与 `/library/organize/status` 仅管理显式启用的根目录自动整理；
  `/library/root-videos` 是一个兼容期只读接口。
- `/library/scrape`、`/library/scrape/status` 管理批量刮削。
- `/library/external-scores/refresh`、`/library/external-scores/status` 管理全库评分。

所有长任务应保存返回的 `workflow_id`，再通过 `/workflows/{workflow_id}` 或 SSE 跟踪。

## Local-first 可移植导出

在 `backend/` 运行：

```powershell
python -m app.portability export --output data/exports/library-export.zip
python -m app.portability validate --input data/exports/library-export.zip
```

`library-export.v1` 只导出 Canonical Film 知识、FilmProfileState、Viewing、
用户策展元数据及 accepted/rejected Assertion 决定。它不包含媒体、locator、
Settings/密钥、Job/Workflow/Event、Read Model 或模型原始内容。v1 没有 import、
设备注册、逻辑时钟、CRDT 或冲突合并能力。

## 已删除接口

不得调用：

- `/library/{movie_id}`、`/library/user-states`、`/watch-history`、`/profile/watch-history`；
- `/library/analyze/{movie_id}`、`/analyze/{movie_name}`；
- Movie audit/timeline、projection rebuild、event backfill；
- 任何基于 Legacy ID、alias 或可选 read source 的接口。

修改后端路径或响应时，必须同时更新 `docs/api.md` 和本 Skill。

## Cinema DNA

- `GET /profile/cinema-dna` 返回完整观影历史的去重影片数、记录数、评分样本和四维覆盖率。
- `GET /profile/cinema-dna/facets/{dimension}` 接受 `genre|person|country|decade`、
  `metric=exposure|preference`、`limit`（默认 20，最大 100）、`offset`。
- `GET /profile/cinema-dna/contributors` 必填 `dimension` 与事实 `key`；相同 metric，
  默认每页 40、最大 100。事实 ID 校验沿用 Explore，畸形输入 `422`，合法但缺失则空结果。
- 契约为 `cinema-dna.v1`，读取 Schema v5 的 `cinema-dna-film.v1` 投影。只统计
  当前 profile、active Film、confirmed 且未删除的 Viewing，包含不再位于资料库的影片。
- 接触面为类别去重影片数 / 全部已看影片数；多标签占比之和可超过 100%。重看只增加记录数。
- 偏好只计算当前电影级个人 1–5 星算术平均；全局至少 10 部、类别至少 3 部已看且评分
  影片才展示，低样本值为 null 且不参与偏好排名。接触面仍可查看类别和评分明细。
- 响应含公式版本、样本门槛、分子分母及来源；贡献影片可通过 `/diary?film={film_id}`
  查看原始 Viewing。日期未知不影响全时间统计；收藏、外部评分、笔记和 AI 推断不参与。
- 这是只读统计，不触发模型、文件操作或领域写入；投影缺失/失败/过期返回
  `503 projection_unavailable`。不得将其称为统计显著性或用户价值验证结果。

## Video health

- `/maintenance/video-health` is a durable, per-MediaAsset/stat-version queue,
  separate from scan ffprobe metadata. GET reports counts/config/UTC budget,
  schedule reason, observed host load and unread abnormal-version notifications.
- PUT `/config` accepts strict enabled/paused booleans, UTC start/end minutes
  0..1439 and daily budget minutes 1..1440. POST `/queue` requests a small-batch
  sweep; it skips unchanged passes and never synchronously scans all disks.
- GET `/files` provides bounded pages by state; GET `/files/{vh_id}` revalidates
  live version/access. POST that ID with retry/cancel/acknowledge controls only
  that receipt. Queue cancel is POST `/cancel`; it does not disable future auto
  discoveries. Old unavailable versions are never certified by a retained pass.
- Container status and full audio/video decoding status are separate. Only a
  continuous all-stream EOF decode of an unchanged accessible version is passed.
  Unknown/offline/permission/tool/cancel/write failures are not media damage.
  Exact error time is unknown; decoded progress is not a corruption timestamp.
- Worker is globally single-file, resource-limited, observes sustained idle and
  yields to jobs. Host counters cannot establish all NAS clients or disk sleep;
  missing counters need a narrowed allowed window. Budget stops new launches;
  already-running long files may complete beyond it while idle. Pauses retain
  the decoder; restart marks interrupted incomplete with explicit full retry.
- No media writes, repairs/deletion, saved transcode, external notifications or
  provider access. Health operational rows are omitted from downloadable backups
  and portable export, and cascade on deep reset. See docs/api.md and
  docs/features/video-health.md for limitations and full API contracts.


### Source-backed language search

Extended `search-plan.v2` optionally accepts `languages`, at most eight objects
`{kind:"original"|"spoken",code:<ISO639-1 or yue>,exclude:<strict bool>}`.
Different clauses combine with AND. Repeated/contradictory clauses fail validation.
Old plans continue to omit the empty field. Local EN/ZH examples: `films in Japanese`,
`original language English`, `原始语言为英语的电影`, `不要日语电影`.
Bare nationality clauses retain country semantics. Unknown or conflicting facts
are excluded from positive and negative filters. Query `results.language_coverage`
reports unknown/conflicted counts per requested kind after other hard filters.
Language chips survive URL restoration and remove only their own clause.

Film detail/library projections add `original_language`, `spoken_languages`,
`language_coverage` and `language_sources`. These are film metadata, independent
of edition audio/dubbing. Schema v12 and library/detail projection v3 build locally;
missing historical language data stays unknown, without automatic provider fetch.

The existing Film metadata endpoint also supports `original_language` (code/null)
and `spoken_languages` (unique code list/null, max30). Set/clear/reset retain
revision, idempotency and source ownership; automatic updates never override manual
values. See `docs/features/language-metadata-enrichment.md` for cast completeness,
source-specific aliases and the explicit ID-bound enrichment helper.


### Bounded semantic clauses and score contracts

Content segmentation preserves soft contrast/preferences while consuming only
complete v2 hard clauses. Supported language clauses around content are strict
original/spoken-language conditions, independently of country; unknown facts
do not satisfy either inclusion or exclusion. Unsupported leftovers clarify.
A parenthesized reference year qualifies the reference identity, not the
recommendations. Explicit uncertain alternatives use exact local identity
choices; no choice or a third ID cannot execute a partial recommendation.

Semantic result metadata optionally includes `result_cap` (default 5),
`rerank_model` and `admission_profile`. SQL and reference exclusions precede the
cap. Absolute thresholds belong to the existing fixed native model only.
`search_rerank_uncalibrated` is an unavailable state, not a correct empty answer;
unknown score scales stop before provider dispatch. No paid provider is enabled.
Snapshot policy v4 binds model/cap; older snapshots require explicit resubmit,
while restore/navigation remain local. See
`docs/features/search-content-boundaries.md` for offline proposal limitations.
