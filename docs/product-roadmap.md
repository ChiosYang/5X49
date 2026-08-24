# 5X49 12 周产品化开发计划

> 状态：提案（Proposed）  
> 制定日期：2026-08-14  
> 适用范围：5X49 从当前工程原型进入 Public Beta 的产品化周期

## 1. 执行摘要

5X49 接下来 12 周的目标不是继续扩充媒体管理能力，而是验证一个明确的产品命题：

> 用户是否愿意安装一个自托管应用，并持续使用“可信、可探索的个人电影知识图谱”理解自己的收藏、记录观影并获得推荐。

产品定位暂定为：

> **5X49 是面向本地电影收藏用户的自托管个人电影知识与观影日记系统。**

“Personal Cinema OS”可以作为品牌表达，但不作为功能承诺，避免用户误解为播放器、媒体服务器或媒体自动化平台。

产品主链路为：

```text
Import → Understand → Explore → Remember → Ask
```

12 周结束时，陌生用户应能够：

1. 使用 Docker 安装并打开 5X49。
2. 导入 Local Folder / NFO 电影库。
3. 将本地条目解析为规范电影作品。
4. 为部分电影生成带来源和可信度标识的知识关系。
5. 浏览单部电影关系图与收藏探索页。
6. 记录多次观看、评分和笔记。
7. 查看可解释的个人 Cinema DNA。
8. 使用自然语言在自己的收藏中筛选和询问电影。
9. 导出诊断信息、备份数据库并从备份恢复。

W12 发布 Public Beta，W13–W14 继续观察第二周留存。12 周内不以商业化、GitHub Stars 或功能数量作为主要成功标准。

## 2. 计划假设

本计划基于以下假设制定：

- 主要由一名全职开发者推进；如果实际投入不同，应重新调整并行任务数量。
- 延续 Next.js、FastAPI、SQLModel、SQLite 和现有 Docker 架构。
- 产品首先服务单用户、自托管、本地优先场景。
- 不强制用户注册云端账号。
- TMDB 和 AI Provider 都可以缺省；没有 API Key 时基础 Library 与 Diary 仍可使用。
- 已有 Library、Metadata、Job、Event、Watch History、Settings 和 Film Genealogy 能力应尽量复用。
- 当前公共 API 尽量保持兼容；发生响应结构变更时同步更新 API 文档和外部 Agent Skill。
- Graph 首先通过 SQLite 普通关系表、索引和递归查询实现，不引入 Neo4j。

## 3. 目标用户与核心任务

### 3.1 主要用户

首批目标用户是同时满足以下若干特征的人：

- 拥有本地电影文件或 NFO 电影库。
- 使用 TinyMediaManager、Jellyfin、Plex、Emby 等工具管理收藏。
- 关心导演、流派、电影运动、主题、影史影响和个人观影记录。
- 愿意部署 Docker 应用。
- 不满足于传统的海报墙和文件播放界面。

首个 Beta 不以普通流媒体用户为核心用户。

### 3.2 用户核心任务

用户使用 5X49 时，希望完成以下任务：

1. 快速了解自己的电影库包含哪些作品，以及元数据是否完整。
2. 理解一部电影从何而来、影响了什么、与其他作品为何相关。
3. 从电影运动、主题、人物、年代和国家角度重新浏览收藏。
4. 记录自己在什么时候看过什么、如何评价以及当时的想法。
5. 理解自己的长期偏好，而不是只得到一个黑盒推荐分数。
6. 用自然语言提出约束条件，从自己拥有的电影中获得可靠建议。

## 4. 产品边界

### 4.1 12 周内必须完成

- Local Folder / NFO 导入主链路。
- Film 与 LibraryItem 的规范身份分离。
- Person、Concept、Credit、Assertion、Evidence 等 Graph 基础模型。
- 版本化数据库迁移和可恢复备份。
- Analysis V2：结构化输出、来源、生成记录、去重和错误恢复。
- 单电影 Graph 和证据查看。
- Explore MVP，优先覆盖 2–3 个质量最可靠的维度。
- 多次 Viewing 的 Diary。
- Cinema DNA V1。
- 受约束的 Ask MVP。
- Setup Wizard、健康检查、日志导出和成本提示。
- Private Alpha、Public Beta 与本地指标导出。

### 4.2 条件性范围

以下功能只有通过对应的用户或质量门槛后才进入 12 周范围：

- Global Graph。
- A → B Path Finding。
- Jellyfin Read-only Sync。
- 大规模全库自动分析。

条件性功能不得挤占数据库安全、首次安装、Graph 可信度和 Diary 数据安全。

### 4.3 明确不做

- 播放器、转码、视频串流。
- 下载器和 BT/Usenet 管理。
- Radarr、Sonarr、Jellyfin、Plex 或 Emby 替代品。
- 通用 AI Chatbot。
- 多 Agent 编排扩张。
- 社交网络。
- 云同步。
- 多用户权限系统和账号中心。
- Stripe、订阅、License Server、Pricing Page。
- 为了 Graph 展示而迁移到 Neo4j。
- 训练推荐模型。
- 电视节目、剧集和音乐库。

## 5. 当前基线与约束

### 5.1 已有能力

- Next.js 16 + React 19 前端和多语言路由。
- FastAPI + SQLModel + SQLite 后端。
- NFO 扫描、TMDB 搜索、匹配、刮削和 artwork 管理。
- Library、Search、Watch History、Settings、Activity 和 Admin 页面。
- 后台 Job、取消、重试和状态查询。
- Library watcher 和增量同步基础。
- MovieUserState：watched、watched_at、rating、favorite、notes。
- Film Genealogy AI 分析。
- 事件记录、Movie 投影、时间线预览和部分补偿恢复。
- Docker Compose 和 AMD64/ARM64 镜像基础。
- 若干基于 `unittest` 的后端测试。

### 5.2 主要缺口

- 当前 Movie 同时承担电影作品、本地收藏条目和媒体文件职责。
- director、genres、actors 和 analysis_data 仍是字符串或 JSON，无法稳定构图。
- AI ancestors/descendants 是未解析的 title/year 文本引用。
- AI 关系没有可核查 Evidence、生成版本、审核状态或可靠的置信度语义。
- MovieUserState 每部电影只有一行，无法保存多次观看。
- 数据库迁移主要依赖 `create_all` 和手写 `ALTER TABLE ADD COLUMN`。
- `/health` 只验证进程响应，没有验证数据库、Job Runtime、媒体目录或依赖状态。
- README 与根 Compose 的默认访问端口存在不一致。
- 缺少从安装到首次价值的完整 Setup Wizard。
- 缺少 Graph 数据质量评测集和回归测试。
- 缺少可选、本地优先的产品漏斗指标。

### 5.3 本周期冻结项

除非直接阻塞本计划，不继续扩展：

- Librarian Agent 的自主能力。
- 更复杂的 Event Sourcing / Compensation 范围。
- 新的媒体整理和刮削来源。
- Admin 技术面板。
- 非电影媒体类型。

## 6. 核心产品与技术决策

### 6.1 Film 与 LibraryItem 分离

知识图谱中的节点代表电影作品，不代表用户硬盘中的文件。推荐模型如下：

```text
Film
  ├── FilmIdentity (TMDB / IMDb / future providers)
  ├── Credit → Person
  ├── FilmConcept → Concept
  ├── Assertion → Other Entity
  ├── LibraryItem
  │     └── MediaAsset
  └── Viewing
```

- `Film`：规范电影作品。
- `LibraryItem`：用户收藏中的一条来源记录，例如 Local/NFO 或 Jellyfin item。
- `MediaAsset`：本地文件、路径、时长、编码、大小和可用状态。
- `FilmIdentity`：外部系统 ID，至少包含 provider、external_id 和唯一约束。

非收藏电影可以作为 `Film` 出现在 Graph 中，但没有 `LibraryItem`。这样才能表达完整谱系，又不会假装用户拥有这部电影。

### 6.2 单用户采用 LocalProfile

12 周内不引入账号系统。需要归属字段时使用单个本地 `LocalProfile`，为未来多用户保留迁移空间。

不要一边声明不做 Account System，一边引入包含认证、权限和租户语义的 `User` 模型。

### 6.3 Person 与 Credit

导演、演员和摄影师使用统一 Person 实体，通过 Credit 表表达电影中的职责：

```text
Credit
- film_id
- person_id
- department
- job
- character
- billing_order
- source
```

Graph API 可以把 Credit 投影为 `DIRECTED_BY`、`ACTED_IN` 或 `SHOT_BY`，数据库不需要为每一种工作人员关系创建独立表。

### 6.4 Concept 统一受控概念

Genre、Theme、Movement 可以使用带 `kind` 的 Concept 表，但必须维护不同来源和审核策略：

```text
Concept.kind = genre | theme | movement | visual_style
```

Country 使用 ISO 代码，Studio 和 Collection 使用稳定外部 ID；不要仅依靠本地化名称去重。

### 6.5 Assertion、Evidence 与 Provenance 分离

Graph 中可争议或可推断的边使用 Assertion：

```text
Assertion
- id
- subject_entity_id
- predicate
- object_entity_id
- status: proposed | accepted | rejected
- confidence
- source_scope: factual | curated | inferred
- created_at
- updated_at
```

证据与生成记录分别保存：

```text
Evidence
- assertion_id
- evidence_type
- source_title
- source_uri
- publisher
- claim
- retrieved_at

AnalysisRun
- film_id
- provider
- model
- prompt_version
- schema_version
- input_hash
- status
- input_tokens
- output_tokens
- estimated_cost
- started_at
- finished_at
- error
```

规则：

- 结构化事实来自 NFO、TMDB 或其他明确数据源。
- `ADAPTED_FROM`、`REMAKE_OF`、`INFLUENCED_BY` 优先要求外部证据。
- `HAS_THEME`、`VISUALLY_SIMILAR_TO` 等主观关系可以由 AI 推断，但必须标记 `inferred`。
- “AI inferred”是 Provenance，不是 Evidence。
- LLM 自报置信度不能直接等同于事实置信度。
- 用户可以接受或拒绝 proposed Assertion，拒绝结果应在重新分析后继续生效。

### 6.6 Viewing 是事件，不是状态

Diary 使用一条记录代表一次观看：

```text
Viewing
- id
- profile_id
- film_id
- watched_at
- rating
- review
- tags
- mood
- favorite_scene
- source
- created_at
- updated_at
```

`rewatch` 由同一 Film 的 Viewing 数量推导。现有 MovieUserState 暂时保留为兼容投影，提供 watched、favorite、latest_rating 和 latest_watched_at。

### 6.7 Graph 是产品投影，不是数据库品牌

SQLite 中使用规范表、索引和递归 CTE 即可满足 MVP。只有出现经过测量的性能或运维瓶颈后，才评估专用图数据库。

### 6.8 LLM 只参与适合它的环节

Ask 和 Analysis 使用以下分工：

```text
Database / Graph
  → 事实过滤、实体解析、候选检索、约束校验

Ranking
  → 可解释的统计排序

LLM
  → 查询意图结构化、主观关系提议、结果解释
```

严格条件默认不得被 LLM 擅自放宽。需要放宽时，必须同时给出严格结果和明确说明的替代结果。

## 7. 目标数据流

```text
Local Folder / NFO
        ↓
LibraryItem + MediaAsset
        ↓
External Identity Resolution
        ↓
Canonical Film
        ↓
Metadata / Credit / Concept
        ↓
Analysis Job
        ↓
Proposed Assertions + Evidence + AnalysisRun
        ↓
Validation / Deduplication / Review
        ↓
Graph API / Explore / Cinema DNA / Ask
```

数据流应满足：

- 重复扫描是幂等的。
- 元数据刷新不会删除用户 Viewing。
- Graph 可以从规范数据和 AnalysisRun 重建。
- 用户拒绝的 AI Assertion 不会在重建后自动恢复。
- 外部来源断开不会删除 Film 或 Viewing。
- 每个自动写入操作都能定位到来源和执行记录。

## 8. 信息架构

推荐主导航：

```text
Home / Library / Explore / Diary / Ask
```

- `Graph` 首先作为电影详情页和 Explore 内的上下文能力。
- Global Graph 达到性能和价值门槛后，再成为独立主导航项。
- `Settings` 与 `Admin` 放入管理入口。
- `Activity` 放入 Admin 或 Library 辅助入口。
- 暂时移除不可用的 Television、Notes 等占位导航。

## 9. API 与兼容策略

具体路径在实施时通过 API RFC 确认，推荐资源划分如下：

```text
GET    /films/{film_id}
GET    /films/{film_id}/graph
GET    /graph/path

GET    /explore/concepts
GET    /explore/people
GET    /explore/decades

GET    /diary/viewings
POST   /diary/viewings
PUT    /diary/viewings/{viewing_id}
DELETE /diary/viewings/{viewing_id}

GET    /taste/profile
POST   /ask

GET    /setup/status
POST   /setup/provider/test
POST   /backup
POST   /restore/preview
```

兼容要求：

- 现有 `/library`、`/library/{movie_id}` 和 user-state API 在 Beta 前不得突然移除。
- `Movie` API 可以在内部映射到 Film + LibraryItem，并通过版本化方式逐步演进。
- Graph API 返回稳定 ID，不以本地化 title 作为标识。
- API 变更必须同步更新 `docs/api.md` 和 `skills/5x49-backend/SKILL.md`。
- 删除或破坏性恢复操作必须继续使用现有标识符验证和预览模式。

## 10. 12 周逐周计划

### W1｜产品定义、用户发现与基线

#### 目标

确定目标用户、产品边界、核心价值和验证方法，冻结与产品命题无关的工程扩张。

#### 任务

- 编写精简 Product Spec。
- 完成一句话定位、目标用户和核心 Jobs-to-be-Done。
- 确定主链路和信息架构。
- 明确本周期不做事项，并建立 backlog 隔离区。
- 招募至少 5 名潜在 Alpha 用户，优先选择已有 NFO/Jellyfin/Plex 收藏的人。
- 完成 5–8 次访谈或安装环境调查。
- 在一台干净环境中记录当前 Docker 安装全流程。
- 建立当前基线：启动时间、导入耗时、分析耗时、常见错误和需要手工配置的步骤。
- 定义本地产品事件和匿名导出格式，不默认上传用户电影清单。
- 冻结 Librarian Agent、Event Sourcing 扩展和新的媒体整理能力。

#### 交付物

- `docs/product-spec.md`。
- 用户访谈摘要与问题清单。
- 当前安装基线报告。
- Beta 候选用户名单。
- 决策记录：产品定位、导航、明确不做事项。

#### 验收标准

- 团队能在 30 秒内解释 5X49 是什么、服务谁、为什么不同。
- 每一项 W2–W12 功能能映射到至少一个核心用户任务。
- 无法映射的功能移入 post-beta backlog。
- 至少 3 名潜在用户同意尝试后续 Alpha。

### W2｜Schema RFC、迁移与备份基础

#### 目标

先解决领域边界和数据库安全，再开始构建 Graph。

#### 任务

- 编写 Film、LibraryItem、MediaAsset、ExternalIdentity、Person、Credit、Concept、Assertion、Evidence、AnalysisRun、Viewing 的 Schema RFC。
- 明确现有 Movie 字段到新模型的映射。
- 决定 Entity 全局 ID 和 Graph subject/object 引用方式。
- 定义稳定外部 ID、别名和去重约束。
- 引入版本化迁移机制，优先评估 Alembic。
- 制作包含旧 Movie、MovieUserState、Job 和 Event 数据的迁移 fixture。
- 实现升级前数据库备份和迁移失败恢复策略。
- 定义 Graph 数据哪些是 durable data，哪些是可重建 projection。
- 定义保留现有 API 的兼容层。

#### 交付物

- `docs/domain-model.md`。
- 数据库迁移策略和第一版 migration runner。
- 旧版本数据库测试 fixture。
- 备份文件格式、命名和保留策略。

#### 验收标准

- 旧数据库可升级且记录数量一致。
- 迁移重复执行不会产生重复数据。
- 迁移失败时原数据库仍可恢复。
- Schema RFC 覆盖作品与媒体、事实与推断、状态与事件三组边界。
- 未通过本周 Gate 不进入 Graph UI 开发。

### W3｜规范实体与旧数据迁移

#### 目标

让本地媒体条目稳定解析为规范 Film，并保持现有 Library 可用。

#### 任务

- 实现 Film、FilmIdentity、LibraryItem 和 MediaAsset。
- 将 NFO/TMDB ID 解析为 FilmIdentity。
- 实现 title/year/path fallback 匹配和人工 review 状态。
- 建立 Person、Credit、Concept 和基础映射。
- 从现有 director、actors、genres、countries 回填规范实体。
- 保留 Movie 或建立兼容查询层，避免现有 API 和前端一次性重写。
- 增加唯一约束、索引和重复扫描测试。
- 设计孤立 Film、缺失媒体和多 LibraryItem 指向同一 Film 的行为。

Gate A 只验收 Canonical Library、Media、Viewing 和旧 API 兼容层。Person、Credit、Concept
仍属于 W3 的后续实现，不阻塞 Slice 5 的本地工具完成，但它们完成前 W3 本身不算结束。

#### 交付物

- 新领域表与迁移。
- Entity resolution 服务。
- 兼容 API。
- 数据回填与一致性报告。

#### 验收标准

- 同一目录连续扫描两次不会产生重复 Film 或 LibraryItem。
- TMDB/IMDb 相同的多来源条目可以映射到同一 Film。
- 非收藏 Film 可以存在且不会出现在“Owned”列表中。
- 原有 Library、详情页、Watch History 基本行为保持可用。
- 人工抽查的实体解析准确率达到预设目标，建议不低于 95%。

### W4｜Analysis V2、Assertion 与质量评测

#### 目标

把 AI 文章升级为可以进入知识图谱、可以验证和可以重建的数据。

#### 任务

- 使用严格的 Pydantic/JSON Schema 定义 Analysis V2 输出。
- 移除对隐藏 thought chain 的依赖，只保留面向用户的 concise rationale。
- 将每个电影引用解析到 Film；解析失败的引用进入 review queue。
- 将结构化事实、外部证据和 AI 推断分开保存。
- 实现 Assertion 去重、status、来源和 AnalysisRun。
- 将 Assertion/Evidence/AnalysisRun 持久化、幂等去重和 rejected 状态保护作为 Gate B
  的实现证据，不回填到 Gate A。
- 保存 provider、model、prompt/schema version、token、成本和 input hash。
- 支持分析失败重试、幂等写入和版本变化后的选择性重算。
- 建立 30–50 部电影的固定评测集，覆盖中英文片名、重名、冷门电影和不同年代。
- 人工标注关系正确性、帮助程度、重复率和实体解析结果。

#### 交付物

- Analysis V2 schema。
- Assertion/Evidence/AnalysisRun 持久化。
- Graph quality evaluation 脚本和基线报告。
- 原有 analysis_data 到 V2 的迁移或重新分析策略。

#### 验收标准

- 任何 Graph 边都能说明来自结构化事实、外部证据还是 AI 推断。
- 未解析 title/year 不会直接成为无法追踪的正式节点。
- 同一模型、同一输入的重试不会无限创建重复 Assertion。
- 用户拒绝的 Assertion 在重分析后仍保持拒绝。
- 人工评测达到预设正确率和帮助度；建议正式展示边的可接受率不低于 85%。

### W5｜单电影 Graph 垂直切片

#### 目标

完成从导入、规范化、分析、关系存储到用户界面的第一条端到端产品链路。

#### 任务

- 实现单电影 Graph API。
- 在电影详情页加入 Cinema DNA 和 Genealogy Graph。
- 支持 Film、Person、Concept 节点点击和详情跳转。
- 区分 Owned、Unowned、Proposed、Accepted 和 Inferred。
- 提供证据/解释侧栏。
- 提供列表视图作为小屏幕和无障碍回退。
- 对节点数和深度设置上限，避免不可读的“毛线球”。
- 缓存 Graph 查询并在相关数据变化时失效。
- 邀请 3–5 名用户进行可用性测试。

#### 交付物

- 单电影 Graph API 和 UI。
- 证据面板。
- 移动端和列表回退视图。
- 第一轮用户测试记录。

#### 验收标准

- 用户能从一部收藏电影进入一个关系节点，再返回或继续探索。
- 用户能判断一条关系是事实、来源支持还是 AI 推断。
- 一般规模 Graph 的 API 目标响应时间低于 500ms，不含首次 AI 分析。
- 页面在手机和桌面端无明显文本溢出或操作阻塞。
- 至少 3 名 Alpha 用户中有 2 名能在不解释界面的情况下完成指定探索任务。

### W6｜Private Alpha 与首次启动流程

#### 目标

让外部用户在没有开发者现场操作的情况下完成安装、导入和首次价值体验。

#### 任务

- 实现 Setup Wizard：选择媒体目录、扫描、配置或跳过 Provider、分析前 10 部、进入应用。
- 明确没有 TMDB Key 和 AI Key 时的降级路径。
- 在分析前显示预计时间和成本。
- 支持取消、恢复和重试首次分析。
- 修复 README、Compose、访问端口和环境变量的不一致。
- 增强健康检查，覆盖数据库、Job Runtime、媒体目录和关键配置。
- 记录本地激活漏斗，并允许用户导出匿名摘要。
- 给 3–5 名用户发送 Private Alpha。
- 观察安装，不代替用户操作；记录每个阻塞点。

#### 交付物

- Setup Wizard。
- AI 可选路径。
- 增强健康检查。
- Alpha 安装包和反馈模板。
- 激活漏斗基线。

#### 验收标准

- 干净环境可通过文档和 Docker 完成安装。
- 用户不编辑前端 API URL 或 CORS 即可使用默认部署。
- 无 AI Key 时仍能进入 Library、Diary 和基础 Explore。
- 从打开 Setup 到看到第一个可信 Graph 的目标时间不超过 10–15 分钟。
- 至少 3 名 Alpha 用户成功导入 Library。

### W7｜Explore MVP

#### 目标

把 Graph 数据转化为收藏探索价值，而不是只展示关系图。

#### 任务

- 根据 W4 数据质量选择最可靠的 2–3 个维度，例如 People、Theme、Movement。
- 实现 Explore 首页、维度列表和详情页。
- 每个详情页显示 Owned、Watched、Unwatched 和数据覆盖率。
- 展示 Essential、Related 和收藏缺口，但明确评分规则。
- 允许从 Explore 回到 Film 与 Diary。
- 对概念别名、本地化名称和空数据提供回退。
- 继续收集 Alpha 用户的探索行为和访谈反馈。

#### 交付物

- Explore MVP。
- 2–3 类实体详情页。
- 数据覆盖率和空状态。
- 第二轮用户测试结果。

#### 验收标准

- Explore 不依赖未审核的大量 AI 边才能使用。
- 用户能回答“我的收藏中有哪些某运动/主题/人物作品”。
- 每个统计数字都能回溯到电影列表。
- 低覆盖率时显示数据不足，而不是生成看似精确的结论。

### W8｜Diary 与多次 Viewing

#### 目标

把现有 Watch History 演进为不会覆盖历史的个人观影日记。

#### 任务

- 实现 Viewing CRUD。
- 将现有 watched_at、rating 和 notes 迁移为第一条 Viewing。
- 保留 favorite 等电影级状态。
- 支持同一 Film 多次观看、日期、评分和 review。
- 增加 tags、mood、favorite_scene；允许字段为空。
- 设计 Viewing 的来源字段，为未来外部同步做准备。
- 更新 Diary 时间线、电影详情和 Watch History 兼容入口。
- 增加导出格式，确保用户能带走日记数据。

#### 交付物

- Viewing 表、服务和 API。
- Diary 页面。
- 旧数据迁移。
- Diary 导出。

#### 验收标准

- 同一电影可以有多次观看且旧记录不会被覆盖。
- 旧 MovieUserState 数据迁移后仍能在界面看到。
- 删除 LibraryItem 不会级联删除 Viewing 或 Film。
- 重看次数由 Viewing 推导，不依赖手填布尔值。
- Diary 数据能以稳定格式导出。

### W9｜Cinema DNA V1

#### 目标

以透明、可解释的统计方法展示个人偏好，不训练推荐模型。

#### 任务

- 定义偏好分数公式和最低样本量。
- 分离 exposure（看得多）与 preference（评分高）。
- 对同一电影多次观看设上限，避免单片无限放大权重。
- 计算 Person、Genre、Theme、Movement、Country 和 Decade 维度。
- 显示样本量、观看次数、平均评分和时间范围。
- 支持无评分用户的简化版本。
- 提供“为什么得到这个结果”的展开说明。
- 用固定小数据集验证计算结果。

#### 建议公式

第一版可使用可解释的加权统计，而不是一个不可见的总分：

```text
exposure_score = capped_view_count
preference_score = normalized_rating × confidence_by_sample_size
recency_adjustment = small bounded factor
```

不要直接使用未经归一化的 `watched × rating × frequency`。

#### 交付物

- Taste aggregation 服务。
- Cinema DNA 页面。
- 公式说明和测试数据。

#### 验收标准

- 任意结果都可以展开查看贡献它的 Film 和 Viewing。
- 少量数据不会显示过度确定的结论。
- 没有评分时仍能显示 Exposure，但不冒充 Preference。
- 固定输入产生稳定、可测试的输出。

### W10｜Ask Your Cinema MVP

#### 目标

让用户通过自然语言查询自己的收藏，同时保持事实约束和结果可解释。

#### 任务

- 定义受支持的查询意图：Owned、Watched、Unwatched、Runtime、Year、Person、Genre、Theme、Movement、Mood 等。
- 将自然语言解析为经过验证的结构化 Query Plan。
- 先由数据库执行严格过滤，再使用 Graph/Taste 排序。
- LLM 只解释候选结果和关联原因。
- 显示解析出的过滤条件，让用户可以修正。
- 同时支持无 LLM 的表单式高级筛选回退。
- 对零结果区分“严格无结果”和“可放宽条件的建议”。
- 记录响应耗时、候选数量、成本和失败原因。
- 防止把媒体路径、API Key 或无关本地数据发送给模型。

#### 交付物

- Ask Query Plan schema。
- Query executor 和 ranking。
- Ask UI 与条件回显。
- 成本、隐私和回退处理。

#### 验收标准

- `Owned AND Unwatched AND Runtime < 100` 等条件由数据库严格执行。
- 推荐理由引用实际 Film、Viewing、Concept 或 Assertion。
- 系统不会把不满足严格条件的电影伪装成满足条件。
- 无 LLM 或 LLM 失败时，用户仍能使用结构化筛选。
- Ask 不回答与个人电影收藏无关的通用问题。

### W11｜Release Candidate 加固

#### 目标

停止开发新的大功能，完成可安装、可升级、可诊断和可恢复的候选版本。

#### 任务

- 完成 DB 备份、恢复预览和一次完整恢复演练。
- 测试从至少一个已发布版本升级到当前版本。
- 增加日志下载和隐私清理。
- 完善 health check、Job 卡死恢复和分析断点续跑。
- 审查 API Key 保存、日志脱敏、路径验证和 CORS 默认值。
- 测试无 Key、无媒体目录、只读目录、磁盘不足和外部 API 失败。
- 检查大库分页、Graph 节点上限和慢查询。
- 完成中英文 onboarding、错误提示和核心页面文案。
- 更新 README、部署文档、API 文档和 Agent Skill。
- 运行完整的前端检查和后端测试。
- 从干净 Docker volume 完成一次发布候选验收。

#### 交付物

- Release Candidate 镜像或构建产物。
- 迁移/恢复验收记录。
- 安装和故障排查文档。
- 已知问题清单。

#### 验收标准

- 支持的旧数据库可以成功升级。
- 备份恢复后 Film、LibraryItem、Viewing 和 Assertion 数量一致。
- 默认 Docker 部署只需要选择媒体目录即可进入基础产品。
- API Key 不出现在日志和诊断导出中。
- 所有阻断级和高优先级问题清零。
- 关键前端检查、后端测试和 Docker smoke 通过。

### W12｜Public Beta

#### 目标

发布给真实用户，停止以新增功能代替产品验证。

#### 任务

- 发布 Beta 版本和简洁安装说明。
- 分批邀请用户，避免一次性制造无法处理的支持压力。
- 建立问题模板：安装、导入、Graph 质量、Diary、Ask、数据安全。
- 每日检查失败漏斗和阻断问题。
- 只修复阻断、数据安全、严重 Graph 错误和高频体验问题。
- 访谈成功用户与流失用户。
- 输出 W12 Beta 报告。
- 在 W13–W14 继续测量第二周留存。

#### 初始 KPI

| 指标 | 目标 | 说明 |
| --- | ---: | --- |
| 安装尝试 | 30 | 明确定义开始安装的用户 |
| 成功启动 | 25 | 可以打开应用并通过基础健康检查 |
| 成功导入 Library | 20 | 至少导入一部有效 Film |
| 看到首个 Graph | 15 | 完成首次 Graph 激活 |
| 创建 Viewing | 10 | 至少记录一次观看 |
| 使用 Explore 或 Ask | 10 | 至少一次有效交互 |
| 第二周仍使用 | 8 | W13–W14 按 cohort 统计 |
| 主动反馈 | 5 | 非仅安装问题的产品反馈 |

#### 验收标准

- 记录完整的安装到激活漏斗。
- 所有数据安全问题在继续招募前优先修复。
- W12 结束时形成继续、调整或停止某些功能的明确决策。
- 第二周留存结论明确标记为 W13–W14 后才能完成。

## 11. 条件功能决策

### 11.1 Global Graph / Path Finding

满足以下条件后才开发：

- 单电影 Graph 的正式展示边达到质量目标。
- 至少 5 名 Alpha 用户中有 3 名主动尝试继续探索关系。
- Explore 已证明用户理解节点和关系语义。
- 查询性能在目标库规模下可接受。

Path Finding 不应只返回最少 hop。路径排序至少考虑：

- 关系可信度。
- 关系类型的解释价值。
- 是否经过过度连接的热门节点。
- 用户是否拥有或看过节点对应的 Film。
- 路径长度和多样性。

如果条件不满足，W10 保持 Ask MVP，不制作 Global Graph Demo。

### 11.2 Jellyfin Read-only Sync

满足以下条件之一再进入开发：

- 前 5–10 名用户中至少 3 名明确因缺少 Jellyfin 无法使用。
- Local/NFO 导入已达到激活目标，接入成为增长的主要阻塞。
- 能获得真实 Jellyfin 环境用于开发和回归测试。

实施前必须先写 Integration RFC，覆盖：

- 连接、认证和用户选择。
- 分页、增量同步和断点续传。
- Jellyfin Item 与 FilmIdentity 的匹配。
- 多次观看、评分和 favorite 的字段语义。
- 只读边界、删除行为和冲突处理。
- 外部服务断开或重建后的稳定性。
- API 版本兼容和测试 fixture。

默认情况下，Jellyfin 推迟到 Beta 后；若验证通过，可替换 W10 的部分范围，但不得替换 W11 的稳定性工作。

## 12. 跨周期工程要求

### 12.1 数据迁移与备份

- 每次 schema 变更都有版本化 migration。
- migration 有向前测试；危险变更有备份和恢复说明。
- 使用旧数据库 fixture 运行升级回归。
- 用户数据和可重建 Graph projection 分开处理。
- Viewing、用户接受/拒绝的 Assertion 和设置属于不可丢失数据。
- 自动生成关系可以重建，但不能覆盖用户审核结果。

### 12.2 测试策略

#### 后端单元测试

- Entity resolution。
- ExternalIdentity 唯一性。
- Analysis V2 schema validation。
- Assertion 去重和状态保护。
- Viewing CRUD 与旧状态迁移。
- Cinema DNA 计算。
- Ask Query Plan 验证与严格过滤。

#### 后端集成测试

- 旧数据库升级。
- 扫描 → Film/LibraryItem → metadata → analysis → graph。
- Job 重试和幂等。
- 备份与恢复。
- API 兼容响应。

#### 前端检查

- ESLint。
- TypeScript typecheck。
- Next.js production build。
- Graph、Explore、Diary 和 Ask 的空状态/错误状态。
- 手机、桌面和长文本溢出检查。

#### 端到端 Smoke

- Docker 启动。
- Setup Wizard。
- 导入最小 NFO fixture。
- 打开 Film 详情与 Graph。
- 创建第二次 Viewing。
- 执行一条严格 Ask 查询。
- 下载诊断信息和创建备份。

### 12.3 性能预算

Beta 前定义并记录至少以下指标：

- 1,000、5,000、10,000 部 Library 的列表查询性能。
- 扫描吞吐和重复扫描耗时。
- 单电影 Graph 查询时间。
- Explore 聚合查询时间。
- Ask 检索时间与 LLM 时间分布。
- 每 10/100 部电影的分析成本和成功率。

没有真实数据前不做复杂性能优化，但必须避免无分页全表返回和无上限 Graph 扩展。

### 12.4 安全与隐私

- API Key 不写入日志、事件 payload、诊断包或前端响应。
- 所有用户控制的 movie ID、路径和 provider 地址使用现有验证模式。
- 文件操作限制在配置的媒体目录内。
- 默认不上传完整 Library、Viewing、review 或媒体路径作为遥测。
- Beta 指标使用本地统计和用户主动导出的匿名摘要。
- 发送给 LLM 的上下文只包含完成查询所需字段。
- 外部 Evidence URI 视为不可信输入，前端安全渲染。

### 12.5 可观测性与错误恢复

- 每个 AnalysisRun 和导入 Job 有 correlation ID。
- 错误分为用户配置、外部服务、数据质量和内部错误。
- 用户可查看失败原因、重试或跳过。
- health check 区分 liveness 和 readiness。
- 诊断导出包含版本、迁移版本、Job 摘要和脱敏错误，不包含密钥和媒体绝对路径。

### 12.6 文档同步

以下变更必须同步文档：

- 后端 endpoint 或响应结构：更新 `docs/api.md`。
- 外部 Agent 可调用能力：更新 `skills/5x49-backend/SKILL.md`。
- Docker、端口、变量和安装：更新 README 与部署示例。
- 数据迁移和恢复：更新升级指南。
- Analysis schema 与关系语义：更新 domain model 和 Graph 说明。

## 13. 产品指标定义

### 13.1 激活漏斗

```text
Started Install
  → App Ready
  → Library Connected
  → First Film Imported
  → First Graph Ready
  → First Exploration
  → First Viewing / Ask
```

必须为每一步定义分母、成功条件和失败原因，避免只报告成功用户。

### 13.2 核心指标

- **安装成功率**：App Ready / Started Install。
- **导入成功率**：First Film Imported / App Ready。
- **Graph 激活率**：First Graph Ready / First Film Imported。
- **首次价值时间**：Started Install 到 First Graph Ready 的中位时间。
- **Graph 信任度**：被接受或未被报告错误的展示边比例，结合人工抽查。
- **W2 留存**：首次激活后第 8–14 天有核心行为的用户比例。
- **核心行为**：Explore、Viewing、Ask 或重新打开 Film Graph；仅打开设置页不算。
- **分析成功率**：成功 AnalysisRun / 开始的 AnalysisRun。
- **单位成本**：每成功分析 10/100 部 Film 的实际或估算成本。

### 13.3 诊断方式

- 安装高、导入低：优先修复权限、路径、NFO 和 onboarding。
- 导入高、Graph 低：优先修复 Key、成本、Job 和实体解析。
- Graph 高、留存低：Graph 可能只有展示价值，优先验证 Explore、Diary 和 Ask。
- Ask 使用高、Graph 浏览低：Graph 可能更适合作为底层能力而不是独立主页面。
- Diary 使用高、AI 使用低：保持 AI 可选，不把 Diary 锁在付费分析之后。

## 14. 阶段 Gate

### Gate A｜W2 Schema Ready

- Film 与 LibraryItem 已分离。
- Viewing 为多记录模型。
- Canonical Library、Media、Viewing 与旧 API 兼容读取/双写经过真实库副本演练。
- Assertion、Evidence、AnalysisRun 的边界明确，但其持久化、去重和拒绝保护由 W4/Gate B
  验收。
- 旧数据迁移和恢复方案可执行。
- Docker 首装、旧库升级、canonical/shadow/legacy 回退、恢复和中英文 smoke 有脱敏证据。

未通过：继续完善领域模型，不开始 Graph UI。

当前状态（2026-08-24）：**Blocked**。策展式验收库已通过本地 Gate，但自然积累的真实资料库
副本和 Docker 运行证据仍缺失；不能记录 Gate A Passed。

### Gate B｜W4 Graph Data Trusted

- 评测集覆盖主要边界情况。
- 实体解析和边质量达到目标。
- 事实、证据和推断可区分。
- 分析重试幂等。

未通过：减少关系类型或调整数据来源，不扩大 Graph。

### Gate C｜W6 Alpha Activated

- 至少 3 名外部用户成功导入。
- 至少 2 名用户看到并理解首个 Graph。
- 没有数据丢失或密钥泄漏问题。

未通过：暂停 Explore、DNA 和 Ask，集中修复 onboarding 与 Graph 可信度。

### Gate D｜W10 Product Signal

- Explore、Diary 或 Ask 至少一个功能出现重复使用。
- 用户能说出 5X49 与媒体服务器海报墙的差异。
- 核心查询和统计可以解释。

未通过：缩减功能面，集中到重复使用最多的一个工作流。

### Gate E｜W12 Beta Ready

- 支持升级、备份、恢复和诊断。
- 阻断与高优先级问题清零。
- 安装和隐私文档完整。
- 已准备 W13–W14 留存跟踪。

未通过：延迟公开招募，不以发布日期换取用户数据风险。

## 15. 主要风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
| --- | --- | --- | --- |
| Film 与本地媒体继续混用 | 高 | 高 | W2 完成 Schema RFC，W3 先迁移再做 UI |
| AI 生成错误关系损害信任 | 高 | 高 | Assertion 状态、Evidence、人工评测、减少关系类型 |
| 新 schema 损坏旧数据库 | 中 | 高 | 版本化迁移、旧库 fixture、升级前备份和恢复演练 |
| 12 周范围过大 | 高 | 高 | Global Graph/Jellyfin 条件化，Gate 未通过时停止扩张 |
| 用户没有或不愿配置 API Key | 高 | 中 | AI 可选、跳过路径、成本预估、基础功能不依赖 AI |
| Graph 好看但没有留存价值 | 中 | 高 | W5 早测、W7 Explore、W8 Diary、按重复行为决策 |
| 路径搜索产生无意义捷径 | 中 | 中 | 按可信度和关系价值加权，惩罚超级节点 |
| 大型 Library 查询变慢 | 中 | 中 | 分页、索引、节点上限和目标规模基准 |
| Jellyfin 集成吞噬周期 | 高 | 中 | 用户需求 Gate，默认移到 Beta 后 |
| 指标采集侵犯本地隐私 | 低 | 高 | 本地统计、主动导出、默认不上传收藏和日记 |
| 继续投入底层平台工程 | 中 | 中 | W1 冻结项，只有阻塞产品链路才解除 |

## 16. 每周执行节奏

建议每周保持以下节奏：

### 周一

- 检查上周 Gate、用户反馈和未解决风险。
- 只确认一个本周核心结果。
- 把条件性功能排除在承诺范围之外。

### 周二至周四

- 以小分支、小提交实现端到端切片。
- 先补迁移、服务和测试，再连接 UI。
- 每天在真实或 fixture 数据上验证一次主链路。

### 周五

- 运行相关检查。
- 做一次干净环境或升级场景 smoke。
- 审查 diff：正确性、回归、安全、迁移和文档。
- 邀请至少一名外部用户或维护者体验当前结果。
- 更新风险、指标和下周范围。

## 17. Definition of Done

任何功能只有满足以下条件才算完成：

- 行为和范围与 Product Spec 一致。
- 数据模型和迁移已经覆盖。
- 失败、空状态、无 Key 和重复执行行为明确。
- 有与风险相称的测试或人工验证记录。
- 不破坏现有 API，或已经按计划版本化。
- UI 支持桌面和手机，无明显文字溢出。
- 用户可理解结果来源和限制。
- 日志、指标和诊断中不暴露敏感信息。
- 相关 API、Skill、安装或升级文档已更新。
- 完成 diff review，没有混入无关重构。

## 18. Beta 后候选 Backlog

Beta 数据确认产品命题后，再按用户信号选择：

- Jellyfin Read-only Sync。
- Plex / Emby Sync。
- Letterboxd / Trakt Diary Import。
- Global Graph 和加权 Path Finding。
- 更多可核查的影史数据源。
- 用户维护的 Concept 和 Assertion。
- Graph 编辑、合并和审核队列。
- 更高级的 Cinema DNA 时间趋势。
- Ask 多轮上下文和保存查询。
- 多设备同步。
- 多 Profile 或家庭用户。
- 开放 API Token 和 Webhook。
- 商业模式与 Pro 边界。

商业化讨论只有在至少 10 名真实活跃用户出现后启动。基础 Library、用户数据导出和数据安全能力不应被锁定；付费边界必须来自用户访谈和实际使用，而不是当前阶段的猜测。

## 19. 立即执行清单

开始 12 周周期前，按以下顺序创建首批任务：

1. 编写 `docs/product-spec.md`。
2. 创建用户访谈问题和 Alpha 用户名单。
3. 在干净环境执行当前 Docker 安装并记录阻塞。
4. 编写 Film / LibraryItem / Viewing / Assertion Schema RFC。
5. 选择并建立版本化 migration runner。
6. 制作旧数据库 migration fixture。
7. 定义 Analysis V2 JSON Schema 和 30–50 部评测集。
8. 定义本地激活漏斗事件和匿名导出格式。
9. 建立 W2、W4、W6、W10、W12 Gate 检查表。
10. 将 Global Graph、Jellyfin、商业化和新 Agent 明确移入条件 backlog。

完成以上清单后，才进入 W3 的正式实现。

