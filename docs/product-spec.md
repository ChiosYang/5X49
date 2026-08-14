# 5X49 Product Spec

> 状态：提案（Proposed）
>
> 日期：2026-08-14
>
> 计划来源：[12 周产品化开发计划](./product-roadmap.md)
>
> 适用范围：从当前工程原型到 Public Beta 的产品基础与验收边界

## 1. 一句话定位

**5X49 是面向本地电影收藏用户的自托管个人电影知识与观影日记系统。**

“Personal Cinema OS”只作为品牌表达，不承诺播放器、媒体服务器或媒体自动化能力。

## 2. 目标用户

首个 Beta 面向愿意自托管、拥有 Local Folder / NFO 电影库，并希望理解收藏、记录观影和获得可解释建议的用户。他们可能同时使用 TinyMediaManager、Jellyfin、Plex 或 Emby，但 5X49 不取代这些工具。

普通流媒体用户、需要开箱即用云服务的用户和以播放、下载、转码为主要需求的用户，不是首个 Beta 的核心用户。

## 3. 核心 Jobs-to-be-Done

| ID | 当我…… | 我想要…… | 从而…… |
| --- | --- | --- | --- |
| JTBD-1 | 接入自己的本地电影库时 | 快速确认导入了哪些作品、身份是否匹配、元数据是否完整 | 我能信任后续探索建立在正确的收藏之上 |
| JTBD-2 | 查看一部电影时 | 看懂它与人物、概念和其他电影的关系，以及关系的来源与可信度 | 我能理解电影从何而来、影响了什么、为何相关 |
| JTBD-3 | 不知道接下来浏览什么时 | 按人物、主题、运动、年代和国家重新探索收藏 | 我能发现海报墙无法呈现的结构与收藏缺口 |
| JTBD-4 | 看完或重看电影时 | 分别记录日期、评分和当时的想法 | 我的历史不会被下一次观看覆盖 |
| JTBD-5 | 回顾长期观影时 | 看到样本量透明、可追溯的偏好与接触面 | 我能理解自己的 Cinema DNA，而不是接受黑盒分数 |
| JTBD-6 | 带着约束挑电影时 | 用自然语言或结构化条件查询自己的收藏 | 我能获得严格满足条件且理由可核查的建议 |

## 4. 主链路

```text
Import → Understand → Explore → Remember → Ask
```

| 阶段 | 用户动作 | 必须得到的结果 | 失败或降级行为 |
| --- | --- | --- | --- |
| Import | 选择 Local Folder / NFO 并扫描 | 本地条目映射到规范 Film；冲突与缺失可见 | 保留 LibraryItem，标记待复核，不静默合并或丢弃 |
| Understand | 打开单部电影关系与证据 | 区分事实、外部证据、AI 推断和审核状态 | 无可靠关系时展示元数据与“数据不足”，不生成伪精确结论 |
| Explore | 从可靠维度浏览收藏 | 统计可回溯到 Film 列表，并显示覆盖率 | 低覆盖维度隐藏或明确提示，不依赖大量未审核 AI 边 |
| Remember | 新建或编辑一次 Viewing | 每次观看独立保存，可导出且不随媒体删除 | 可选字段为空不阻断保存；旧记录迁移后仍可见 |
| Ask | 输入自然语言或表单条件 | 数据库严格过滤，结果解释引用实际数据 | 无 LLM 时使用结构化筛选；零结果时区分严格结果与放宽建议 |

首次价值定义为：用户成功导入至少一部 Film，并看到一个来源和关系类型可理解的单电影 Graph。若未配置 AI Key，则以成功导入、完成基础 Explore 或创建 Viewing 作为可用的非 AI 首次价值，不阻断进入产品。

## 5. Beta 范围

### 5.1 必做

- **数据基础与安全**：Film / LibraryItem 身份分离；Person、Concept、Credit、Assertion、Evidence、AnalysisRun、Viewing 边界；版本化迁移；升级前备份与恢复路径。
- **Import**：Local Folder / NFO 导入、稳定外部身份、幂等扫描、匹配复核和现有 Library 兼容。
- **Understand**：Analysis V2 结构化输出、来源与生成记录、去重与错误恢复；单电影 Graph、证据侧栏和列表回退。
- **Explore**：只选择质量达标的 2–3 个维度，展示 Owned / Watched / Unwatched、覆盖率和可回溯列表。
- **Remember**：多次 Viewing、旧状态迁移、Diary 时间线和稳定导出。
- **Cinema DNA**：区分 exposure 与 preference，展示样本量、计算依据和贡献 Film / Viewing。
- **Ask**：受约束 Query Plan、数据库严格过滤、可解释排序、条件回显和无 LLM 表单回退。
- **首次启动与运营安全**：Setup Wizard、无 Key 路径、成本提示、增强健康检查、日志导出、备份恢复、隐私保护和本地指标摘要导出。
- **发布验证**：Private Alpha、Release Candidate、Public Beta 和 W13–W14 留存观察；这些是待执行阶段，不代表已有候选人、反馈或结果。

### 5.2 条件范围

以下能力只有满足第 12 节的进入条件且不挤占数据安全、首次安装、Graph 可信度和 Diary 数据安全时，才可排期：

- Global Graph 与加权 Path Finding。
- Jellyfin Read-only Sync。
- 大规模全库自动分析。

它们不是 Beta 发布承诺；未通过 Gate 时继续留在条件 backlog。

### 5.3 明确不做

- 播放、转码、串流、下载和 BT/Usenet 管理。
- 替代 Radarr、Sonarr、Jellyfin、Plex 或 Emby。
- 通用 AI Chatbot、新 Agent 或多 Agent 编排扩张。
- 社交、云同步、多用户权限和账号中心。
- Stripe、订阅、License Server、Pricing Page 或 Beta 内商业化。
- 为展示 Graph 而迁移 Neo4j，或训练推荐模型。
- 电视、剧集和音乐库。

## 6. 信息架构

```text
Home
├── Library
│   └── Film Detail
│       ├── Cinema DNA
│       └── Genealogy Graph + Evidence
├── Explore
│   ├── People
│   ├── Selected Concepts
│   └── Decades / Countries（按数据质量启用）
├── Diary
└── Ask

Management
├── Settings
└── Admin
    ├── Activity
    ├── Health
    └── Diagnostics / Backup
```

- `Graph` 在 Beta 中是 Film Detail 与 Explore 的上下文能力，不是独立主导航。
- `Settings` 和 `Admin` 放入管理入口；`Activity` 不占主导航。
- 不展示不可用的 Television、Notes 等占位入口。
- Global Graph 只有通过条件 Gate 后才可评估为独立入口。

## 7. 无 Key 与外部依赖降级

| 情况 | 仍可使用 | 明确不可用或受限 | 产品要求 |
| --- | --- | --- | --- |
| 无 TMDB Key | NFO / Local Folder 导入、Library、Diary、本地元数据 Explore | TMDB 搜索、补全与 artwork 抓取 | Setup 可跳过；缺失身份或字段可见并可复核 |
| 无 AI Provider Key | Library、Diary、结构化元数据 Explore、基础 Cinema DNA、表单式高级筛选 | AI Analysis、推断关系、自然语言解析与结果解释 | 不阻断启动；不把 AI 推断伪装成已有数据 |
| 两种 Key 都没有 | 导入 NFO、本地浏览、记录 Viewing、导出数据 | 外部补全和 AI 能力 | 用户仍能完成一条完整的非 AI 主链路 |
| Provider 暂时失败 | 已持久化的 Film、Viewing、已审核关系和本地查询 | 新的远程补全或分析 | 显示失败类型；允许取消、恢复、重试或跳过 |

API Key 不得进入日志、事件 payload、诊断包、指标摘要或前端响应。发送给 LLM 的上下文只包含完成请求所需字段，不包含媒体绝对路径或无关本地数据。

## 8. 成功指标

以下为指标定义和待验证方向，不是已采集结果。目标值、样本窗口和分母须在开放决策完成后冻结；原始计数和失败原因必须与比率一起报告。

| 维度 | 指标 | 定义 | Beta 所需证据 |
| --- | --- | --- | --- |
| 安装 | 安装成功率 | App Ready / Started Install | 本地漏斗摘要与失败分类 |
| 导入 | 导入成功率 | First Film Imported / App Ready | 有效 Film 数、扫描错误和耗时 |
| 激活 | Graph 激活率 | First Graph Ready / First Film Imported | Graph 来源可见且用户可打开 |
| 速度 | 首次价值时间 | Started Install 到首次 AI 或非 AI 价值事件的中位时间 | 分开报告有 Key / 无 Key 路径 |
| 信任 | Graph 质量 | 展示边的人工抽查结果、错误报告、接受/拒绝结果 | 固定评测集与版本化基线；不把“未报告”单独当作正确 |
| 使用 | 核心行为 | Explore、Viewing、Ask 或重新打开 Film Graph | 只统计有效行为，设置页访问不计入 |
| 留存 | W2 留存 | 首次激活后第 8–14 天发生核心行为的用户比例 | W13–W14 cohort 完成后才可下结论 |
| 稳定性 | 分析与任务成功率 | 成功运行 / 开始运行，并按失败类型拆分 | Job / AnalysisRun 摘要与重试结果 |
| 成本 | 单位分析成本 | 每成功分析 10 / 100 部 Film 的实际或估算成本 | provider、model、token 与估算规则 |
| 数据安全 | 迁移/恢复完整性 | 恢复前后 durable data 计数与抽查一致 | Film、LibraryItem、Viewing、审核状态的演练记录 |

Beta 是否继续、收缩或调整，依据激活、信任、重复核心行为、留存和数据安全综合判断，不以 GitHub Stars、功能数量或安装量单独判断。

## 9. 关键风险

| 风险 | 早期信号 | 缓解与停止条件 |
| --- | --- | --- |
| Film 与媒体条目继续混用 | 同一作品重复、删除媒体导致知识或日记丢失 | W2 先冻结边界；Gate 未过不进入 Graph UI |
| AI 错误关系损害信任 | 无来源边、重名解析错误、拒绝关系复现 | Assertion / Evidence / Provenance 分离；减少关系类型并暂停扩图 |
| 新 schema 损坏用户数据 | 记录数变化、重复迁移、恢复失败 | 旧库 fixture、幂等迁移、升级前备份和恢复演练 |
| 12 周范围失控 | 条件功能进入承诺路径、稳定性工作被挤占 | Gate 控制；Global Graph、Jellyfin、商业化和新 Agent 保持后置 |
| 无 Key 用户无法获得价值 | Setup 被 Key 卡住、空白 Explore / Ask | 保证 Library、Diary、基础 Explore 与结构化筛选可用 |
| Graph 只有展示价值 | 首次打开后无 Explore、Diary 或 Ask 重复行为 | W5 早测；W10 Gate 后聚焦重复使用最多的链路 |
| 指标或诊断侵犯隐私 | 导出包含路径、收藏明细或密钥 | 默认本地统计、主动导出、脱敏验证；有泄漏即暂停招募 |
| 大库性能退化 | 无分页查询、Graph 无上限扩展 | 分页、索引、节点/深度上限和目标规模基准 |

## 10. W2–W12 能力到核心任务映射

此表是范围审查基线。新增能力若不能映射到 JTBD，应移入 post-beta backlog。

| 周次 | 主要能力 | 对应核心任务 | 用户结果 |
| --- | --- | --- | --- |
| W2 | Schema RFC、迁移、备份 | JTBD-1、JTBD-4 | 收藏身份清楚，升级不丢日记与审核数据 |
| W3 | 规范实体、身份解析、兼容层 | JTBD-1、JTBD-2 | 重复扫描稳定，作品与本地媒体不混淆 |
| W4 | Analysis V2、Assertion、Evidence、评测 | JTBD-2、JTBD-6 | 关系来源可核查，查询不会建立在不可追踪文本上 |
| W5 | 单电影 Graph 垂直切片 | JTBD-2、JTBD-3 | 从一部电影理解并继续探索可信关系 |
| W6 | Setup Wizard、无 Key 路径、Private Alpha | JTBD-1、JTBD-2 | 外部用户可独立安装、导入并获得首次价值 |
| W7 | Explore MVP | JTBD-3 | 按可靠维度重看收藏并回溯统计 |
| W8 | Diary 与多次 Viewing | JTBD-4 | 重看记录不覆盖，可迁移、保存和导出 |
| W9 | Cinema DNA V1 | JTBD-5 | 以透明统计理解接触面与偏好 |
| W10 | Ask Your Cinema MVP | JTBD-6 | 用自然语言或表单执行严格、可解释的收藏查询 |
| W11 | 升级、恢复、诊断与 RC 加固 | JTBD-1、JTBD-4、JTBD-6 | 核心数据和主链路在故障与升级后仍可靠 |
| W12 | Public Beta 与验证 | JTBD-1–JTBD-6 | 用真实使用证据决定继续、调整或收缩 |

## 11. Gate 检查表

所有条目初始均为未勾选；未勾选表示**尚未评估**，不表示失败或完成。每次 Gate 评审必须附证据链接或记录，不得用计划、口头确认或推测替代实测结果。

### Gate A｜W2 Schema Ready

- [ ] Film 与 LibraryItem 已分离，删除或断开媒体不会误删 Film。
- [ ] Viewing 为多记录事件模型，旧状态映射明确。
- [ ] Assertion、Evidence、AnalysisRun 的边界和 durable / projection 分类明确。
- [ ] 旧数据迁移、升级前备份和失败恢复方案可执行并有验证记录。
- [ ] 现有 Library / user-state API 的兼容策略明确。

未通过动作：继续完善领域模型、迁移与恢复；不开始 Graph UI。

### Gate B｜W4 Graph Data Trusted

- [ ] 固定评测集覆盖中英文片名、重名、冷门作品和跨年代样本。
- [ ] 实体解析与正式展示边达到事先冻结的质量阈值。
- [ ] UI/API 可区分结构化事实、外部证据和 AI 推断。
- [ ] 相同输入重试幂等，拒绝的 Assertion 不会因重分析复活。
- [ ] 未解析引用进入 review queue，不直接成为正式节点。

未通过动作：减少关系类型、调整数据来源或修复解析；不扩大 Graph。

### Gate C｜W6 Alpha Activated

- [ ] 至少 3 名外部用户在无开发者代操作的情况下成功导入 Library。
- [ ] 至少 2 名用户看到并能说明首个 Graph 的关系和来源语义。
- [ ] 无 AI Key 时仍可进入 Library、Diary 和基础 Explore。
- [ ] 没有已知数据丢失或密钥泄漏问题。
- [ ] 安装、导入和首次价值的阻塞点有可复核记录。

未通过动作：暂停 Explore、Cinema DNA 和 Ask 扩张，集中修复 onboarding 与 Graph 可信度。

### Gate D｜W10 Product Signal

- [ ] Explore、Diary 或 Ask 至少一项出现可证实的重复使用。
- [ ] 用户能说明 5X49 与媒体服务器海报墙的差异。
- [ ] 核心查询、推荐理由和偏好统计均可回溯到实际数据。
- [ ] 严格条件不会被 LLM 静默放宽，无 LLM 回退可用。
- [ ] 条件 backlog 的任何进入请求均附用户或质量证据。

未通过动作：缩减功能面，聚焦重复使用最多的一个工作流；不制作 Global Graph Demo。

### Gate E｜W12 Beta Ready

- [ ] 支持版本升级、备份、恢复预览和完整恢复演练。
- [ ] 阻断级和高优先级问题清零。
- [ ] 安装、隐私、诊断和已知问题文档完整。
- [ ] 无 Key、只读目录、磁盘不足和外部 API 失败路径已验证。
- [ ] W13–W14 cohort 留存跟踪方案已准备，但未提前宣称结果。

未通过动作：延迟公开招募，优先保护用户数据；不以发布日期换取风险。

## 12. 条件 backlog

| 候选项 | 当前承诺 | 进入条件 | 未满足时 |
| --- | --- | --- | --- |
| Global Graph | 非 Beta 承诺 | 单电影 Graph 质量达标；至少 5 名 Alpha 用户中 3 名主动继续探索；Explore 语义被理解；目标库规模查询可接受 | 保持 Film Detail / Explore 内的局部 Graph |
| A → B Path Finding | 非 Beta 承诺，依赖 Global Graph | Global Graph 条件通过；排序同时考虑可信度、解释价值、超级节点惩罚、拥有/观看状态与路径长度 | 不制作只按最少 hop 的演示功能 |
| Jellyfin Read-only Sync | 默认 Beta 后 | 前 5–10 名用户中至少 3 名因缺失集成无法使用，或 Local/NFO 激活达标后接入成为主要阻塞；并有真实环境、Integration RFC 与 fixture | 继续支持 Local Folder / NFO，不替换 W11 稳定性工作 |
| 大规模全库自动分析 | 非 Beta 必做 | 单片分析质量、失败恢复、成本与隐私边界达标，并有用户价值证据 | 保持显式、小批量、可取消分析 |
| 商业化 / Pro 边界 | Beta 后研究 | 至少 10 名真实活跃用户，并完成基于实际使用和访谈的价值验证 | 不创建 Stripe、订阅、License Server 或 Pricing Page |
| 新 Agent / 多 Agent 编排 | Beta 后且无承诺 | 只有核心主链路出现无法由现有服务和受约束 Ask 解决的明确问题，并经单独 Product / Safety RFC 验证 | 冻结 Librarian Agent 扩张，不新增 Agent |

条件通过只允许进入排期评审，不等于自动开发。任何候选项都不得替换 W11 的稳定性工作或突破“明确不做”的产品边界。

## 13. 开放决策

以下事项尚未由本 Spec 决定，不得标记为已完成：

1. **指标阈值**：安装、导入、Graph 激活、Graph 质量、首次价值时间和 W2 留存的最终目标值、样本窗口与最小样本量。
2. **首次价值口径**：有 AI Key 与无 AI Key 是否采用不同激活事件，以及如何在同一漏斗中报告。
3. **Explore 维度**：由 W4 数据质量决定 Beta 采用的 2–3 个维度及最低覆盖率。
4. **实体与关系语义**：全局 Entity ID、别名/去重规则、Assertion 正式展示阈值和用户审核交互。
5. **迁移工具与保留策略**：是否采用 Alembic，以及备份格式、命名、保留数量和恢复 UX。
6. **Cinema DNA 公式**：最低样本量、重复观看上限、评分归一化和有限 recency adjustment。
7. **Ask 支持面**：Beta 首批 Query Plan 意图、可放宽条件规则和隐私上下文字段白名单。
8. **Alpha 执行**：招募渠道、候选人、访谈提纲和测试环境；目前不声明已有候选人或访谈结果。
9. **Beta 决策规则**：继续、聚焦、延迟或停止的综合判定方式，以及由谁在何时做出决定。

## 14. 本 Spec 的完成定义

- 新增能力能映射到至少一个 JTBD，并符合主链路与信息架构。
- Beta 必做、条件范围和明确不做之间没有冲突。
- Global Graph、Jellyfin、商业化和新 Agent 始终保持条件或后置范围，除非对应决策被证据化更新。
- 无 Key、失败、空状态、重复执行、备份和恢复行为有明确产品结果。
- Gate 只依据可复核证据勾选，不虚构用户、指标、访谈或完成状态。
- 若后续改变 API、安装、迁移或外部 Agent 能力，再按仓库规则同步对应文档；本次文档任务不改变这些能力。
