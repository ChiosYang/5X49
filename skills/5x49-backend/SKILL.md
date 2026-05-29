---
name: 5x49-backend
description: 电影族谱 API (FastAPI) 的接口调用指南
---

# 5x49 Backend API - 电影族谱 API

这是 FastAPI 后端服务的调用指南。

## 基础信息

- **Base URL**: `http://127.0.0.1:11548`
- **Content-Type**: `application/json`
- **事件契约**: 资料库事件的 v1 payload、分类、投影状态和兼容策略见 `docs/event-contracts.md`。新增或修改事件 payload 时必须同步更新该文档、`docs/api.md` 和本 skill。

## 接口列表

### 健康检查

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 检查 API 是否运行 |
| GET | `/` | 获取 API 基础信息 |

### 电影库管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/library` | 获取所有电影 |
| GET | `/library/user-states` | 获取已保存的个人观影状态 |
| GET | `/watch-history` | 获取手动标记已看的观影历史 |
| GET | `/library/events` | 订阅资料库变更 SSE |
| GET | `/library/audit-events` | 查询持久化资料库审计事件 |
| GET | `/jobs` | 列出后台 Actor/Job Runtime 任务 |
| GET | `/jobs/{job_id}` | 获取单个后台任务状态、结果和错误 |
| POST | `/jobs/{job_id}/cancel` | 取消排队任务或请求运行中任务取消 |
| POST | `/jobs/{job_id}/retry` | 重试 failed/cancelled 任务 |
| DELETE | `/jobs/{job_id}` | 删除已结束任务 |
| GET | `/library/{movie_id}` | 获取指定电影详情 |
| GET | `/library/{movie_id}/user-state` | 获取单部电影的个人观影状态 |
| PUT | `/library/{movie_id}/user-state` | 更新单部电影的已看、评分、收藏和笔记 |
| GET | `/library/{movie_id}/audit-events` | 查询单部电影的持久化审计事件 |
| POST | `/library/events/backfill/movie-discovered?dry_run=true` | 检查或补齐现有电影的 MovieDiscovered 初始化事件 |
| POST | `/library/events/backfill/movie-replay?dry_run=true` | 检查或追加 Movie replay backfill 迁移事件 |
| POST | `/library/events/dry-run/nfo-signatures` | 只读检查扫描发现的 NFO 签名变化 |
| POST | `/library/projections/movie/rebuild?dry_run=true&base=current\|empty` | 检查或受控执行单电影 Movie 投影重建 |
| GET | `/library/operations/dry-run?correlation_id=...` | 只读检查一次操作的恢复/追踪可行性 |
| POST | `/library/operations/restore` | 执行受支持的一次操作文件级补偿恢复 |
| POST | `/library/seed` | 填充测试数据 |
| POST | `/library/scan?media_dir=/path` | 排队扫描并校准目录，新增/更新电影并标记缺失 |
| POST | `/library/reconcile?media_dir=/path` | 排队全量校准资料库 |
| POST | `/library/scan-folder?folder_path=/path` | 排队扫描单个电影文件夹 |
| POST | `/library/{movie_id}/refresh` | 排队按已知本地文件夹刷新单部电影 |
| POST | `/library/{movie_id}/external-scores/refresh` | 排队刷新单部电影的外部评分/榜单信号 |
| POST | `/library/external-scores/refresh` | 排队批量刷新外部评分/榜单信号 |
| GET | `/library/external-scores/status` | 获取外部评分刷新状态 |
| GET | `/library/{movie_id}/artwork` | 获取可选择的 TMDB 海报/背景图 |
| PUT | `/library/{movie_id}/artwork` | 应用用户选择的 TMDB 海报/背景图 |
| GET | `/metadata/search?query=xxx&year=1999` | 使用 TMDB 搜索候选元数据 |
| POST | `/library/{movie_id}/scrape` | 使用 TMDB 刮削单部电影，写入图片和 NFO |
| POST | `/library/{movie_id}/scrape/confirm?tmdb_id=123` | 使用人工确认的 TMDB ID 刮削 |
| POST | `/library/scrape` | 排队批量刮削未匹配/缺图片/指定电影 |
| GET | `/library/scrape/status` | 获取批量刮削状态 |
| POST | `/library/organize-root` | 排队整理媒体根目录直属视频并刮削 |
| POST | `/library/organize-root/confirm` | 排队使用人工确认的 TMDB ID 整理根目录直属视频 |
| GET/PUT | `/settings/scrape-confirmation` | 获取/设置自动刮削前是否必须人工确认 |
| GET/PUT | `/settings/artwork-language` | 获取/设置 TMDB 图片语言，独立于元数据语言 |
| GET | `/library/organize/status` | 获取根目录整理状态 |
| GET | `/library/root-videos` | 列出待整理的媒体根目录直属视频 |
| GET | `/library/sync/status` | 获取校准与自动监听状态 |
| POST | `/library/{movie_id}/ignore` | 忽略一条误扫描记录 |
| DELETE | `/library/missing` | 删除已标记为 missing 的记录 |
| DELETE | `/library` | 清空电影库 |
| GET | `/metadata/movie/{tmdb_id}` | 按 TMDB ID 获取候选信息，用于确认前预览 |

### 分析功能

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/analyze/{movie_name}` | 同步分析电影族谱 |
| POST | `/library/analyze/{movie_id}` | 排队后台分析 |

### 设置

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/settings` | 获取所有设置 |
| GET | `/settings/model` | 获取当前模型 |
| PUT | `/settings/model?model_name=xxx` | 更新模型 |
| GET | `/settings/media-dir` | 获取媒体目录配置 |
| PUT | `/settings/media-dir?media_dir=xxx` | 更新媒体目录 |
| GET | `/settings/language` | 获取系统语言配置 |
| PUT | `/settings/language?language=xxx` | 更新系统语言 |
| GET | `/settings/artwork-language` | 获取 TMDB 图片语言配置 |
| PUT | `/settings/artwork-language?language=en` | 更新 TMDB 图片语言 |
| GET | `/settings/library-watch` | 获取自动监听配置和状态 |
| PUT | `/settings/library-watch?enabled=true` | 开启或关闭自动监听 |
| GET | `/settings/auto-organize-root` | 获取根目录自动整理设置 |
| PUT | `/settings/auto-organize-root?enabled=true` | 开启或关闭根目录自动整理 |
| GET | `/settings/tmdb` | 获取 TMDB API Key 配置状态，不返回明文 |
| PUT | `/settings/tmdb` | 保存或清除 settings 中的 TMDB API Key |
| POST | `/settings/tmdb/test` | 测试当前 TMDB API Key 连通性 |
| POST | `/settings/models/refresh` | 刷新可用模型缓存 |

### 系统与智能体 (Agents)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/sys/list-dirs?path=/` | 列出指定路径的子目录 |
| POST | `/sys/scan-library` | 排队后台库扫描 |
| GET | `/api/agents/clean-inbox` | 召唤 Librarian Agent 执行任务 (SSE返回) |

## 调用示例

### 后台任务运行时
扫描、校准、批量刮削、根目录整理、分析、刷新外部评分等长任务会立即返回 queued job，而不是同步返回最终结果。典型响应：

```json
{
  "status": "queued",
  "message": "Library reconcile queued",
  "job_id": "job_abc",
  "job": {
    "id": "job_abc",
    "type": "library.reconcile",
    "status": "queued"
  }
}
```

查看任务：

```bash
curl -s http://127.0.0.1:11548/jobs
curl -s http://127.0.0.1:11548/jobs/job_abc
curl -s -X POST http://127.0.0.1:11548/jobs/job_abc/cancel
curl -s -X POST http://127.0.0.1:11548/jobs/job_abc/retry
```

`GET /library/events` 除 `library_changed` 外，还会推送 `job_queued`、`job_started`、`job_progress`、`job_succeeded`、`job_failed`、`job_cancelled`、`job_retried`。任务完成后的最终结果位于 job 的 `result` 字段，UI 文案位于 `result_summary`，失败原因位于 `error` 字段。批量刮削、根目录整理、批量外部评分会写入 `progress.current` / `progress.total`；重复提交同一 active job 会通过 `dedupe_key` 复用已有任务。

### 获取所有电影
```bash
curl -s http://127.0.0.1:11548/library
```
返回 `Movie[]`，电影对象包含标题、年份、图片路径、简介、导演、类型，以及可选的 `runtime`、`countries`、`audio_tracks`、`video_width`、`video_height`、`video_codec`、`video_bitrate`、`video_duration`、`video_fps`、`video_dynamic_range`、`video_bit_depth`、`added_at`、`external_scores` 等本地媒体与外部榜单信息。

### 个人观影状态
```bash
curl -s http://127.0.0.1:11548/library/96721_2013/user-state
curl -s -X PUT http://127.0.0.1:11548/library/96721_2013/user-state \
  -H "Content-Type: application/json" \
  -d '{"watched":true,"watched_at":"2026-05-27","rating":5,"favorite":true,"notes":"影院重看"}'
curl -s http://127.0.0.1:11548/library/user-states
curl -s http://127.0.0.1:11548/watch-history
curl -s -X DELETE http://127.0.0.1:11548/library/data
```
`MovieUserState` 是每部电影一条的手动个人状态，字段包括 `movie_id`、`watched`、`watched_at`、`rating`、`favorite`、`notes`、`updated_at`。`rating` 只允许 `1-5` 或 `null`。`GET /library/{movie_id}/user-state` 在尚未保存状态时返回默认未看状态；`GET /watch-history` 只返回 `watched=true` 的电影，按 `watched_at` 和 `updated_at` 倒序排列，元素形如 `{"movie": Movie, "user_state": MovieUserState}`。这些接口不记录播放进度、播放会话或播放器事件。
`DELETE /library/data` 会清空数据库中的资料库影片、个人观看状态、后台任务和持久化审计事件，返回 `{"status":"success","message":"Library data cleared","deleted":{"user_states":0,"movies":0,"jobs":0,"events":0}}` 形状的计数结果；它不会删除媒体文件、生成的 NFO/图片文件、保存设置或环境变量配置。

### 获取单部电影详情
```bash
curl -s http://127.0.0.1:11548/library/96721_2013
```
返回单个 `Movie` 对象；`audio_tracks` 中的音轨项在可用时包含 `codec`、`language`、`channels`。视频技术字段来自扫描/刷新时调用的 `ffprobe`，`ffprobe` 不可用或文件无法解析时这些字段为 `null`/缺省，不阻断扫描。
NFO 签名字段在可用时包含 `nfo_file`、`nfo_path`、`nfo_size`、`nfo_mtime`、`nfo_fingerprint`，用于判断重复扫描时 NFO 是否真的变化。

### 查询审计事件
```bash
curl -s "http://127.0.0.1:11548/library/audit-events?aggregate_type=movie&limit=50"
curl -s http://127.0.0.1:11548/library/96721_2013/audit-events
curl -s "http://127.0.0.1:11548/library/96721_2013/timeline/state?before_event_id=evt_xxx"
curl -s "http://127.0.0.1:11548/library/96721_2013/timeline/restore-preview?at=2026-05-22T00:00:00%2B00:00"
curl -s -X POST http://127.0.0.1:11548/library/96721_2013/timeline/restore -H 'Content-Type: application/json' -d '{"before_event_id":"evt_xxx","restore_fields":["title"],"restore_files":[],"allow_partial":false}'
curl -s -X POST "http://127.0.0.1:11548/library/projections/movie/rebuild?dry_run=true&movie_id=96721_2013"
curl -s -X POST "http://127.0.0.1:11548/library/projections/movie/rebuild?dry_run=true&base=empty&movie_id=96721_2013"
curl -s -X POST "http://127.0.0.1:11548/library/projections/movie/rebuild?dry_run=false&base=empty&movie_id=96721_2013&confirmation_token=sha256_from_dry_run"
curl -s -X POST "http://127.0.0.1:11548/library/events/backfill/movie-discovered?dry_run=true"
curl -s -X POST "http://127.0.0.1:11548/library/events/backfill/movie-replay?dry_run=true&movie_id=96721_2013"
curl -s -X POST "http://127.0.0.1:11548/library/events/dry-run/nfo-signatures?media_dir=/path/to/media"
```
返回持久化 `EventRecord[]`，按时间倒序排列。`/library/events` 是实时 SSE；`/library/audit-events` 和 `/library/{movie_id}/audit-events` 是历史审计日志。`/library/audit-events` 可用 `aggregate_type`、`aggregate_id`、`type`、`command_id`、`correlation_id` 过滤，便于按一次操作追踪事件链。当前为混合模式：多数复杂流程仍旁路记录审计事件，不是完整事件溯源；`MovieIgnored`、`MovieMarkedMissing`、`MovieRestored`、`MovieStateBackfilled`、`MovieStateRestored`、`MetadataRestored`、`ArtworkSelectionRestored`、`RootVideoOrganizationReverted`、`AnalysisStarted`、`AnalysisCompleted`、`AnalysisFailed` 等低风险状态变更会由事件同步投影到 `Movie` 当前状态表。扫描事件会去重：新记录写 `MovieDiscovered`，本地文件关键字段变化才写 `MovieFileObserved`，NFO 签名变化才写 `MovieMetadataParsedFromNfo`，missing 记录重新出现写 `MovieRestored`；成功文件夹扫描不再默认追加 `MovieFolderScanned`，但仍会通过 `/library/events` 发布实时刷新通知。`MovieDiscovered` 和 `MovieFileObserved` 会在可用时记录 ffprobe 获取到的视频详情，包括分辨率、编码、码率、时长、帧率、动态范围、位深和音轨摘要。事件类型和 v1 payload 契约见 `docs/event-contracts.md`，当前包括 `MovieDiscovered`、`MovieFileObserved`、`MovieMetadataParsedFromNfo`、`MovieFolderScanned`、`MovieMarkedMissing`、`MovieRestored`、`MovieIgnored`、`MovieStateBackfilled`、`MetadataMatchSuggested`、`MetadataMatched`、`MovieStateRestored`、`MetadataRestored`、`MetadataScrapeFailed`、`ArtworkDownloaded`、`ArtworkSelected`、`ArtworkSelectionRestored`、`ArtworkRestored`、`MovieFileSnapshotBackfilled`、`NfoWritten`、`NfoRestored`、`RootVideoOrganizationNeedsReview`、`RootVideoMoved`、`RootVideoMoveReversed`、`RootVideoOrganized`、`RootVideoOrganizationReverted`、`MovieProjectionRebuilt`、`AnalysisStarted`、`AnalysisCompleted`、`AnalysisFailed`、`ExternalScoresRefreshed`、`ExternalScoresRefreshFailed`、`LibraryReconciled`、`LibraryCleared`、`MissingMoviesCleaned`、`LibrarySeeded` 等。
`/library/projections/movie/rebuild` 默认 `dry_run=true`，不会修改数据库；dry-run 返回 `confirmation_token`、`event_stream_truncated`、`last_event`，指定 `movie_id` 时还返回 `projected_state`。`dry_run=false` 是阶段 G 的受控执行，只支持单个 `movie_id` 且必须 `base=empty`、不能传 `since`、必须携带同一 dry-run 返回的 `confirmation_token`；执行前会重新计算报告，token 不匹配、事件流被 `limit` 截断、无法投影该电影或存在 skipped projectable events 时返回 409 且不修改 Movie。成功时只替换核心可投影字段并追加 audit-only `MovieProjectionRebuilt`，不修改历史事件、不写媒体文件。当前可投影事件包括 `MovieDiscovered`、`MovieFileObserved`、`MovieMetadataParsedFromNfo`、`MovieIgnored`、`MovieMarkedMissing`、`MovieRestored`、`MovieStateBackfilled`、`MetadataMatched`、`ArtworkSelected`、`MovieStateRestored`、`MetadataRestored`、`ArtworkSelectionRestored`、`RootVideoOrganizationReverted`、`AnalysisStarted`、`AnalysisCompleted`、`AnalysisFailed`、`ExternalScoresRefreshed`。两种模式都会返回 `differences`、`unsupported_event_types`、`skipped_projectable_events` 和 `skipped_events`，用于检查事件和当前状态是否一致，以及识别下一步需要补齐的事件 payload；旧 `ExternalScoresRefreshed` 若缺少 `current` score 字段会被记录为 skipped，不会伪造投影。`MetadataMatched`、`ArtworkSelected` 和成功的 `ExternalScoresRefreshed` 命令已改为 append-first 更新 Movie 状态，接口响应结构不变；文件副作用仍在结果事件中审计，不做盲目 replay。
`/library/events/backfill/movie-discovered` 默认 `dry_run=true`，用于检查哪些现有电影缺少初始化事件；`dry_run=false` 只向 `events` 表追加缺失的 `MovieDiscovered`，不修改 `Movie` 表。补齐事件会尽量排在该电影已有事件之前，便于后续 `base=empty` 按时间顺序 replay。
`/library/events/backfill/movie-replay` 默认 `dry_run=true`，统一检查 replay 迁移缺口；`dry_run=false` 只追加 backfill 事件，不修改旧事件、不投影写 Movie、不改动媒体文件。它会为缺初始化的电影追加 `MovieDiscovered`，为旧 `MetadataMatched`/`ArtworkSelected` 缺 `current` payload 的电影追加 projectable `MovieStateBackfilled` 当前快照，并为当前存在的 poster/backdrop/NFO 追加 audit-only `MovieFileSnapshotBackfilled`；文件 snapshot 只记录当前事实，`restore_available=false`，不会创建 backup。
`/library/events/dry-run/nfo-signatures` 不写数据库、不追加事件，只扫描 NFO 文件签名并和当前 `Movie` 表中的 NFO 签名比对，返回 `new_signature`、`changed`、`unchanged`、`unmatched_movie` 等状态，为后续 `MovieMetadataParsedFromNfo` 去重做准备。
`/library/{movie_id}/timeline/state` 是单电影历史状态 dry-run，必须传 `before_event_id` 或 `at` 其中一个；`before_event_id` 表示重放该事件之前的事件且不包含该事件，`at` 表示重放 `occurred_at <= at` 的事件。返回 `current_state`、从空状态 replay 得到的 `target_state`、`field_diff`、`unsupported_event_types`、`skipped_events` 和 `missing_payload`；缺少可用 `MovieDiscovered` 或旧事件 payload 不足时不会伪造状态。`/library/{movie_id}/timeline/restore-preview` 在同一状态报告上增加 `field_restore`、`file_restore`、`restorable_files`、`missing_file_backups` 和 `status`，只检查 poster/backdrop/NFO backup 与 root video 反向移动的当前文件系统条件，不写数据库、不移动文件、不追加补偿事件。
`/library/{movie_id}/timeline/restore` 会重新计算 preview 后执行历史恢复补偿。字段恢复写入并投影 `MovieStateRestored`；poster/backdrop/NFO 文件只在 preview 找到可用 `backup_path` 时复制备份并追加 `ArtworkRestored` 或 `NfoRestored`。`restore_fields=null` 表示恢复所有 preview 可恢复字段，`restore_files=null` 表示恢复所有 preview 可恢复 poster/backdrop/NFO 文件，空数组表示不恢复该类；`allow_partial=false` 时任一请求项不安全会返回 409 且不修改数据库或文件。
`/library/operations/dry-run` 不写数据库、不移动文件，只按 `correlation_id` 或 `command_id` 分析一次操作的事件链，返回 `can_restore_poster`、`can_restore_backdrop`、`can_trace_nfo_writer`、`can_reverse_root_move`、`side_effects`、`recoverable_fields`、`missing_payload`、`unsafe_actions` 等字段，用于判断撤销/恢复前置条件是否满足。
`/library/operations/restore` 会先复用 dry-run 检查，再执行受支持的补偿动作：`restore_metadata`、`restore_artwork_selection`、`restore_poster`、`restore_backdrop`、`restore_nfo`、`reverse_root_move`。它会追加 `MetadataRestored`、`ArtworkSelectionRestored`、`ArtworkRestored`、`NfoRestored` 或 `RootVideoMoveReversed` 补偿事件，不删除原事件；`ArtworkRestored` 可恢复 poster 或 backdrop 文件内容。字段级恢复只会写回当前值仍等于原事件 `current` 的字段，冲突字段会跳过并写入补偿事件 payload。若一次 root video organization 创建了新电影记录，反向移动成功后还会追加并投影 `RootVideoOrganizationReverted`，将该记录置为 `library_status=reverted`，避免后续扫描把它显示成普通 missing。
阶段 4 相关副作用事件已开始补强 payload：`MetadataMatched`、`ArtworkSelected` 会包含 `changed_fields`、`previous`、`current`；`ExternalScoresRefreshed` 会包含外部评分字段的 `changed_fields`、`previous`、`current`，其中 `current` 至少包含 `external_scores`、`external_scores_updated_at`、`external_scores_error`；`ArtworkDownloaded` 会记录 poster/backdrop 文件写入，并在覆盖已有文件前写入 `.5x49-backups/{command_id}` 后记录 `backup_path`；`NfoWritten` 会记录 NFO 创建或图像引用更新，并在覆盖已有 NFO 前记录 `backup_path`；`RootVideoMoved` 会记录 root video 被移动后的源/目标文件快照；`RootVideoOrganized` 会包含 source/target 文件快照和候选 TMDB 信息。刮削、换图、root video 整理链路会写入 `command_id` / `correlation_id`，便于在全局 Activity 中按同一次操作追踪事件。

### 刷新外部评分/榜单
```bash
curl -s -X POST http://127.0.0.1:11548/library/238_1972/external-scores/refresh
curl -s -X POST http://127.0.0.1:11548/library/external-scores/refresh
curl -s http://127.0.0.1:11548/library/external-scores/status
```
刷新接口返回 queued job。当前实现从 `dataset/TSPDT - 1,000 Greatest Films (Table).csv` 导入 TSPDT 榜单，只会自动写入高置信度的标题/年份/导演匹配。写入后的 `external_scores` 条目包含 `source=tspdt`、`kind=rank`、`rank`、`previous_rank`、`list_name`、`edition`、`matched_by` 和 `confidence`。

### 触发电影分析
```bash
curl -s -X POST http://127.0.0.1:11548/library/analyze/96721_2013
```
返回 queued job；分析结果写回电影详情的 `analysis_status` 和 `analysis_data`。

### 刷新单部电影
```bash
curl -s -X POST http://127.0.0.1:11548/library/96721_2013/refresh
```
返回 queued job；最终刷新结果见 job `result`。

### 选择电影海报/背景图
```bash
curl -s http://127.0.0.1:11548/library/96721_2013/artwork
```

返回已匹配 TMDB 电影的 `posters` 和 `backdrops` 候选列表。每个候选包含 `file_path`、原图 `url`、缩略图 `thumbnail_url`、尺寸、语言和投票信息。电影必须已有 `tmdb_id`，且需要配置 TMDB API Key。

```bash
curl -s -X PUT http://127.0.0.1:11548/library/96721_2013/artwork \
  -H "Content-Type: application/json" \
  -d '{"poster_path":"/poster.jpg","backdrop_path":"/backdrop.jpg"}'
```

应用选择时会校验图片路径来自该电影的 TMDB 候选，覆盖本地 `<video-stem>-poster.jpg` / `<video-stem>-fanart.jpg`，在存在 NFO 时更新图片引用，生成本地 `poster_thumb_local` / `backdrop_thumb_local` 缩略图，然后重扫电影文件夹并返回更新后的 `Movie`。

### 搜索 TMDB 元数据
```bash
curl -s "http://127.0.0.1:11548/metadata/search?query=Inception&year=2010"
```

返回带 `score` 的候选列表。后端使用用户配置的 `TMDB_API_KEY`。

### 按 TMDB ID 预览候选
```bash
curl -s http://127.0.0.1:11548/metadata/movie/603
```

返回单个候选对象，用于用户输入 TMDB ID 或链接后先预览电影，再点击确认执行刮削/整理。

### 刮削单部电影
```bash
curl -s -X POST http://127.0.0.1:11548/library/local_xxx/scrape \
  -H "Content-Type: application/json" \
  -d '{"mode":"auto","language":"zh-CN","artwork_language":"en","overwrite":false,"write_nfo":true,"download_artwork":true}'
```

成功时会按主视频文件名前缀下载 `<video-stem>-poster.jpg` / `<video-stem>-fanart.jpg`、写入 `<video-stem>.nfo`，然后重新扫描电影文件夹并更新数据库。`language` 控制标题/简介等元数据语言；`artwork_language` 可选，支持 `metadata`、`zh`、`en`、`none`，用于单独选择海报/背景图语言，省略时使用 `/settings/artwork-language`。低置信度匹配会返回 `status=needs_review` 和最多 20 个候选；如果 `/settings/scrape-confirmation` 已开启，高置信度匹配也会先返回 `needs_review`，确认后才写入。

### 确认候选并刮削
```bash
curl -s -X POST "http://127.0.0.1:11548/library/local_xxx/scrape/confirm?tmdb_id=27205" \
  -H "Content-Type: application/json" \
  -d '{"overwrite":false,"write_nfo":true,"download_artwork":true}'
```

### 批量刮削未匹配电影
```bash
curl -s -X POST http://127.0.0.1:11548/library/scrape \
  -H "Content-Type: application/json" \
  -d '{"scope":"unscraped","overwrite":false,"write_nfo":true,"download_artwork":true}'
```
`unscraped` 只处理 `metadata_source=filename` 且 `scrape_status=pending/failed` 的可用电影；`ignored` 和 `missing` 会跳过。
如果已开启 `/settings/scrape-confirmation`，批量刮削会把自动匹配项计入 `needs_review`，不会直接写图片、NFO 或匹配元数据。
返回 queued job；批量统计见 job `result` 或 `/library/scrape/status`。

### 整理媒体根目录直属视频
```bash
curl -s -X POST http://127.0.0.1:11548/library/organize-root \
  -H "Content-Type: application/json" \
  -d '{"min_confidence":85,"rename_style":"preserve_stem","overwrite":false,"write_nfo":true,"download_artwork":true}'
```

只处理直接放在媒体根目录下的视频文件。高置信度 TMDB 匹配后会创建电影目录、移动视频、扫描入库并刮削；低置信度会跳过并在状态中返回 `needs_review`。如果已开启 `/settings/scrape-confirmation`，匹配项会在移动文件前返回 `needs_review`。
返回 queued job；整理统计见 job `result` 或 `/library/organize/status`。

### 确认根目录视频并整理
```bash
curl -s -X POST http://127.0.0.1:11548/library/organize-root/confirm \
  -H "Content-Type: application/json" \
  -d '{"path":"/media/The.Matrix.1999.1080p.mkv","tmdb_id":603,"options":{"rename_style":"preserve_stem","overwrite":false,"write_nfo":true,"download_artwork":true}}'
```

用于 `scrape_require_confirmation` 开启后的根目录视频确认流程。确认前不会移动文件；确认后才创建电影目录、移动视频、扫描入库并用该 TMDB ID 刮削。

### 查看待整理根目录视频
```bash
curl -s http://127.0.0.1:11548/library/root-videos
```

这是只读接口，不会写数据库；用于让 UI 提示根目录下有视频等待整理。

### 忽略误扫描记录
```bash
curl -s -X POST http://127.0.0.1:11548/library/local_xxx/ignore
```

### 清理缺失记录
```bash
curl -s -X DELETE http://127.0.0.1:11548/library/missing
```

### 全量校准资料库
```bash
curl -s -X POST http://127.0.0.1:11548/library/reconcile
```
返回 queued job；校准统计见 job `result` 或 `/library/sync/status`。

### 开启自动监听
```bash
curl -s -X PUT "http://127.0.0.1:11548/settings/library-watch?enabled=true"
```

### 更新模型设置
```bash
curl -s -X PUT "http://127.0.0.1:11548/settings/model?model_name=moonshotai/kimi-k2.5"
```

## 注意事项

1. **路径参数** - 如 `{movie_id}` 直接拼接到 URL 中
2. **查询参数** - 使用 `?key=value` 格式
3. **电影 ID 格式** - 使用 URL-safe ASCII；通常是 `tmdb_id_year` 如 `96721_2013`、`imdb_id_year`，没有外部 ID 时是 `local_<hash>`
4. **缺失策略** - 资料库校准和监听删除事件默认将电影标记为 `library_status=missing`，不会直接删除数据库记录
5. **忽略策略** - `library_status=ignored` 的记录会从正常资料库隐藏，并跳过校准缺失标记和批量刮削
6. **自动监听** - 当前监听器默认使用 `watchfiles` 原生文件事件和去抖，避免频繁全目录轮询；如遇 Docker volume、NAS、SMB 事件不可靠，可设置 `watch_mode=polling` 或 `WATCH_MODE=polling` 回退；新增视频会等待 `media_file_stable_seconds` 后再扫描；最终一致性由 `/library/reconcile` 保底
7. **TMDB 刮削** - 需要用户自己的 TMDB API Key；优先读取环境变量 `TMDB_API_KEY`，否则读取 `/settings/tmdb` 保存的设置。`GET /settings/tmdb` 只返回配置状态，不返回明文。默认不覆盖已有文件，优先用于 `metadata_source=filename` 且 `scrape_status=pending/failed` 的电影。`/settings/scrape-confirmation` 开启后，自动 TMDB 匹配都会先进入 `needs_review`，必须调用 `/library/{movie_id}/scrape/confirm` 后才写入文件和 matched 元数据
8. **图片语言** - `artwork_language` 独立控制 TMDB 海报/背景图语言，支持 `metadata`（跟随元数据语言）、`zh`、`en`、`none`（无文字）；请求体省略时读取 `/settings/artwork-language`
9. **图片选择** - `/library/{movie_id}/artwork` 只适用于已有 `tmdb_id` 的电影；`PUT` 会验证用户选择的 `poster_path` / `backdrop_path` 属于该 TMDB 电影，再下载覆盖本地图片并更新数据库
10. **发现记录** - 无 NFO 视频会作为发现记录入库，通常是 `metadata_source=filename`、`scrape_status=pending`；它不是已确认电影身份，需刮削或人工确认后变为 `matched`。发现记录和 TMDB 匹配都以主视频文件名解析标题/年份，目录名只作为物理容器
11. **根目录整理** - `auto_organize_root_videos` 开启后，watcher 会整理媒体根目录直属稳定视频；默认保留原视频文件名，只移动到匹配电影目录并刮削。`/library/root-videos` 会列出待整理文件，避免用户看不见根目录散片。`scrape_require_confirmation` 开启时会在移动文件前停在 `needs_review`，需通过 `/library/organize-root/confirm` 传入确认的 `path` 和 `tmdb_id`
12. **外部评分** - `external_scores` 是可选字段，当前 TSPDT 数据来自仓库 `dataset/` 下的 CSV 离线数据集。由于数据集没有 TMDB/IMDb ID，后端只自动保存高置信度匹配，低置信度或未命中电影会跳过，不改变已有评分
13. **后台任务** - 扫描、校准、批量刮削、根目录整理、分析、刷新外部评分等长任务由内置 Actor/Job Runtime 执行。调用方应保存 `job_id`，通过 `/jobs/{job_id}` 或 SSE job 事件追踪最终结果
14. **推荐使用 http_request 插件** - 如果有安装的话，比 curl 更安全
