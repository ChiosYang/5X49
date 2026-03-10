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
| GET | `/library/{movie_id}` | 获取指定电影详情 |
| POST | `/library/seed` | 填充测试数据 |
| POST | `/library/scan?media_dir=/path` | 扫描目录添加电影 |
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

## 调用示例

### 获取所有电影
```bash
curl -s http://127.0.0.1:11548/library
```

### 获取单部电影详情
```bash
curl -s http://127.0.0.1:11548/library/96721_2013
```

### 触发电影分析
```bash
curl -s -X POST http://127.0.0.1:11548/library/analyze/96721_2013
```

### 更新模型设置
```bash
curl -s -X PUT "http://127.0.0.1:11548/settings/model?model_name=moonshotai/kimi-k2.5"
```

## 注意事项

1. **路径参数** - 如 `{movie_id}` 直接拼接到 URL 中
2. **查询参数** - 使用 `?key=value` 格式
3. **电影 ID 格式** - 通常是 `tmdb_id_year` 如 `96721_2013`，或中文标题如 `季_1_2019`
4. **推荐使用 http_request 插件** - 如果有安装的话，比 curl 更安全
