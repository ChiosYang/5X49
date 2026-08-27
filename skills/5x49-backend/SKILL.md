---
name: 5x49-backend
description: 5X49 Fresh Canonical FastAPI 的 Film、LibraryItem、Viewing、Analysis 与运维接口调用指南
---

# 5X49 Backend API

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
curl -s http://127.0.0.1:8000/films/film_0123456789abcdef0123456789abcdef/graph
curl -s -X POST http://127.0.0.1:8000/library/reconcile
curl -s -X POST http://127.0.0.1:8000/library/items/lib_0123456789abcdef0123456789abcdef/refresh
curl -s -X POST http://127.0.0.1:8000/library/items/lib_0123456789abcdef0123456789abcdef/ignore
```

- `GET /library/films` 一部 Film 一项，直接包含 profile state 和 primary edition。
- `GET /library/films/{film_id}` 返回全部非 retired editions。
- `GET /films/{film_id}/graph` 只从同步 Read Model 返回一跳、定长的
  accepted factual 图谱；Gate B 前不会暴露 inferred/proposed 关系。
- `POST /library/scan` 与 `/library/reconcile` 返回 queued Job。
- `POST /library/scan-folder?folder_path=...` 只允许媒体根内目标。
- `DELETE /library/missing` 退休 missing editions。
- `DELETE /library` 退休收藏但保留 Film 级数据。
- `DELETE /library/data` 彻底删除领域数据，但保留设置、迁移 journal 和固定词表。

不要从 Event/Job 中查找绝对路径；路径只存在于受控、Git ignored 的私有 manifest。

## Profile State 与观看历史

```bash
curl -s http://127.0.0.1:8000/films/<film_id>/profile-state
curl -s -X PUT http://127.0.0.1:8000/films/<film_id>/profile-state \
  -H "Content-Type: application/json" \
  -d '{"watched":true,"rating":5,"favorite":true,"notes":"..."}'
curl -s http://127.0.0.1:8000/profile/watch-history
```

`watched=true` 创建或恢复 manual confirmed Viewing；`watched=false` 只撤销
manual Viewing，不删除 Diary 等其他来源。最终 watched 由任意 active confirmed
Viewing 推导。

## TMDB、Artwork 与外部评分

```bash
curl -s "http://127.0.0.1:8000/metadata/search?query=Inception&year=2010"
curl -s http://127.0.0.1:8000/metadata/movie/27205
curl -s -X POST http://127.0.0.1:8000/films/<film_id>/scrape \
  -H "Content-Type: application/json" -d '{}'
curl -s http://127.0.0.1:8000/films/<film_id>/artwork
curl -s -X PUT http://127.0.0.1:8000/films/<film_id>/artwork \
  -H "Content-Type: application/json" \
  -d '{"poster_path":"/poster.jpg","backdrop_path":"/backdrop.jpg"}'
curl -s -X POST http://127.0.0.1:8000/films/<film_id>/external-scores/refresh
```

TMDB 功能需要 `TMDB_API_KEY` 环境变量或托管设置；读取设置只返回配置状态，
不会返回明文密钥。低置信度或启用确认策略时，通过
`POST /films/{film_id}/scrape/confirm?tmdb_id=...` 明确确认。

## Analysis V2

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
- Job 仅为内部单步骤执行队列，没有公开 HTTP/SSE DTO。

## 设置与维护

- `/settings/*` 管理语言、媒体目录、watcher、刮削确认、TMDB 和模型。
- `/library/root-videos`、`/library/organize-root`、
  `/library/organize-root/confirm` 与 `/library/organize/status` 管理根目录散片。
- `/library/scrape`、`/library/scrape/status` 管理批量刮削。
- `/library/external-scores/refresh`、`/library/external-scores/status` 管理全库评分。

所有长任务应保存返回的 `workflow_id`，再通过 `/workflows/{workflow_id}` 或 SSE 跟踪。

## 已删除接口

不得调用：

- `/library/{movie_id}`、`/library/user-states`、`/watch-history`；
- `/library/analyze/{movie_id}`、`/analyze/{movie_name}`；
- Movie audit/timeline、projection rebuild、event backfill；
- 任何基于 Legacy ID、alias 或可选 read source 的接口。

修改后端路径或响应时，必须同时更新 `docs/api.md` 和本 Skill。
