---
name: 5x49-backend
description: 电影族谱 API (FastAPI) 的接口调用指南
---

# 5x49 Backend API - 电影族谱 API

这是 FastAPI 后端服务的调用指南。

## 基础信息

- **Base URL**: `http://127.0.0.1:11548`
- **Content-Type**: `application/json`

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
| GET | `/library/events` | 订阅资料库变更 SSE |
| GET | `/library/{movie_id}` | 获取指定电影详情 |
| POST | `/library/seed` | 填充测试数据 |
| POST | `/library/scan?media_dir=/path` | 扫描并校准目录，新增/更新电影并标记缺失 |
| POST | `/library/reconcile?media_dir=/path` | 全量校准资料库 |
| POST | `/library/scan-folder?folder_path=/path` | 扫描单个电影文件夹 |
| POST | `/library/{movie_id}/refresh` | 按已知本地文件夹刷新单部电影 |
| GET | `/metadata/search?query=xxx&year=1999` | 使用 TMDB 搜索候选元数据 |
| POST | `/library/{movie_id}/scrape` | 使用 TMDB 刮削单部电影，写入图片和 NFO |
| POST | `/library/{movie_id}/scrape/confirm?tmdb_id=123` | 使用人工确认的 TMDB ID 刮削 |
| POST | `/library/scrape` | 后台批量刮削未匹配/缺图片/指定电影 |
| GET | `/library/scrape/status` | 获取批量刮削状态 |
| GET | `/library/sync/status` | 获取校准与自动监听状态 |
| POST | `/library/{movie_id}/ignore` | 忽略一条误扫描记录 |
| DELETE | `/library/missing` | 删除已标记为 missing 的记录 |
| DELETE | `/library` | 清空电影库 |

### 分析功能

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/analyze/{movie_name}` | 同步分析电影族谱 |
| POST | `/library/analyze/{movie_id}` | 后台触发分析 |

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
| GET | `/settings/library-watch` | 获取自动监听配置和状态 |
| PUT | `/settings/library-watch?enabled=true` | 开启或关闭自动监听 |
| POST | `/settings/models/refresh` | 刷新可用模型缓存 |

### 系统与智能体 (Agents)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/sys/list-dirs?path=/` | 列出指定路径的子目录 |
| POST | `/sys/scan-library` | 异步触发后台库扫描 |
| GET | `/api/agents/clean-inbox` | 召唤 Librarian Agent 执行任务 (SSE返回) |

## 调用示例

### 获取所有电影
```bash
curl -s http://127.0.0.1:11548/library
```
返回 `Movie[]`，电影对象包含标题、年份、图片路径、简介、导演、类型，以及可选的 `runtime`、`countries`、`audio_tracks` 等本地 NFO 媒体信息。

### 获取单部电影详情
```bash
curl -s http://127.0.0.1:11548/library/96721_2013
```
返回单个 `Movie` 对象；`audio_tracks` 中的音轨项在可用时包含 `codec`、`language`、`channels`。

### 触发电影分析
```bash
curl -s -X POST http://127.0.0.1:11548/library/analyze/96721_2013
```

### 刷新单部电影
```bash
curl -s -X POST http://127.0.0.1:11548/library/96721_2013/refresh
```

### 搜索 TMDB 元数据
```bash
curl -s "http://127.0.0.1:11548/metadata/search?query=Inception&year=2010"
```

返回带 `score` 的候选列表。后端使用用户配置的 `TMDB_API_KEY`。

### 刮削单部电影
```bash
curl -s -X POST http://127.0.0.1:11548/library/local_xxx/scrape \
  -H "Content-Type: application/json" \
  -d '{"mode":"auto","overwrite":false,"write_nfo":true,"download_artwork":true}'
```

成功时会按主视频文件名前缀下载 `<video-stem>-poster.jpg` / `<video-stem>-fanart.jpg`、写入 `<video-stem>.nfo`，然后重新扫描电影文件夹并更新数据库。低置信度匹配会返回 `status=needs_review` 和候选列表。

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
7. **TMDB 刮削** - 需要用户自己的 `TMDB_API_KEY`。默认不覆盖已有文件，优先用于 `metadata_source=filename` 且 `scrape_status=pending/failed` 的电影
8. **发现记录** - 无 NFO 视频会作为发现记录入库，通常是 `metadata_source=filename`、`scrape_status=pending`；它不是已确认电影身份，需刮削或人工确认后变为 `matched`。发现记录和 TMDB 匹配都以主视频文件名解析标题/年份，目录名只作为物理容器
9. **推荐使用 http_request 插件** - 如果有安装的话，比 curl 更安全
