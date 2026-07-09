# 安泉CRM v3.5 产品需求文档（PRD）

> **版本**：v2.0 | **日期**：2026-07-09 | **基于**：服务器运行版 318KB 前端 + 最新后端

---

## 一、产品概述

### 1.1 产品定位
安泉CRM是面向安泉数智科技有限公司的轻量级客户关系管理系统，覆盖**线索获取 → 客户管理 → 商机跟踪 → 招投标 → 售前协同 → 渠道管理 → 经营分析**完整业务闭环。

### 1.2 版本演进

| 版本 | 主要变化 |
|------|----------|
| v3.3 | 基础CRM：客户/商机/产品/渠道 CRUD |
| v3.4.1 | 安全加固：PBKDF2密码、JWT环境变量、CORS白名单、越权修复、审计日志 |
| v3.5 | 业务扩展：经营驾驶舱、售前协同、招标雷达、客户360画像、渠道培训、通知系统 |

### 1.3 技术架构

| 层 | 技术 | 规模 |
|-----|------|------|
| 后端 | FastAPI + SQLAlchemy + SQLite | 33KB main.py + 22 个 Router |
| 前端 | React 18 + Ant Design 5 单文件 | 318KB / ~150 函数 |
| 认证 | JWT HS256 + PBKDF2-SHA256 | 5 种角色 |
| 部署 | systemd + Nginx | Ubuntu 22.04 |

### 1.4 角色权限体系

| 角色 | 英文标识 | 权限范围 |
|------|----------|----------|
| 管理员 | `admin` | 全部数据 + 管理后台 |
| 销售主管 | `manager` | 本人 + 下属销售数据 |
| 销售 | `sales` | 仅本人数据 |
| 渠道经理 | `channel_manager` | 渠道相关商机与客户 |
| 售前工程师 | `presales` | 被分配的售前请求相关数据 |

**数据隔离机制**（`permissions.py`）：
- `scoped_opportunity_query` / `scoped_customer_query` / `scoped_lead_query` 自动按角色过滤
- `managed_user_ids` 实现主管-下属层级可见性
- `presales_opportunity_ids` 限制售前仅见已分配商机
- 全部写操作记录审计日志（`audit_logs` + `audit_changes`）

---

## 二、功能模块详解

### 2.1 仪表盘 `/dashboard`

**核心指标卡片**：商机总数、活跃商机数、总金额（按角色自动过滤）、今日待跟进数

**销售漏斗**：5 阶段可视化（拖拽排序），标注各阶段商机数量和转化率

**销售绩效排行**：按月/全部周期统计，含金额、数量、转化率排名

### 2.2 经营驾驶舱 `/business-excellence`

| 子模块 | 功能 |
|--------|------|
| BI 看板 | 综合数据驾驶舱，关键业务指标一览 |
| 客户去重 | 检测重复客户记录，支持合并 |
| 售前 SLA 监控 | 售前响应时效、达标率统计 |
| 渠道信用评分 | 渠道伙伴信用评级体系 |
| 客户成熟度评估 | 客户安全成熟度打分 |
| 行业-产品推荐 | 按行业自动推荐产品组合，支持种子数据 |
| 售前资产库 | 方案文档管理（上传/下载/分类） |
| 预测准确度 | 历史预测 vs 实际成交对比 |
| 招标转化 | 招标项目 → 商机一键转化 |

### 2.3 客户管理

| 页面 | 路由 | 说明 |
|------|------|------|
| 客户列表 | `/customers` | 搜索/筛选（行业/等级）、CRUD、分页 |
| 客户360画像 | `/customers/profile` | 安全评估、成熟度、决策链图谱、竞品分析 |
| 客户分层运营 | `/customers/operations` | 客户运营记录、分层策略管理 |

**客户抽屉（CustomerDrawer）**：侧边栏展示客户详情 + 联系人行内编辑 + 关联商机列表

**客户属性**：名称、行业、地址、网站、等级（VIP/A/B/C）、描述、负责人

### 2.4 商机管理

| 页面 | 路由 | 说明 |
|------|------|------|
| 直销商机 | `/opportunities/direct` | 看板+表格双视图，拖拽变更阶段 |
| 渠道商机 | `/opportunities/channel` | 渠道类型商机，同上交互 |
| 商机详情 | `/opportunities/:id` | 完整信息、跟进记录、售前请求 |

**商机5阶段**（管理后台可配置名称/颜色/进度）：

| 编号 | 默认名称 | 进度 |
|------|----------|------|
| 1 | 获取项目信息 | 20% |
| 2 | 见到用户/渠道 | 40% |
| 3 | 技术交流/试用 | 60% |
| 4 | 明确合作意向 | 80% |
| 5 | 确定合作/招投标 | 100% |

**属性**：名称、类型（直销/渠道）、金额、销售、客户、渠道伙伴、行业、阶段、概率（HIGH/MID_HIGH/MID/LOW）、关键人、处理人、预计成交日、下次跟进日、状态

**核心操作**：新建（自动绑定当前销售）、看板拖拽、快捷跟进（支持接触人）、售前请求、删除（权限校验）

### 2.5 线索管理

| 页面 | 路由 | 说明 |
|------|------|------|
| 线索列表 | `/leads` | CRUD、来源/质量/状态筛选、漏斗统计 |
| 招标雷达 | `/leads/bid-radar` | 关键词订阅、自动采集来源、招标任务跟踪 |
| 招标转化 | `/leads/bid-conversion` | 招标项目 → 商机转化、评分标准配置 |

**线索属性**：名称、公司、联系人、电话、来源（website/exhibition/partner/phone/bidding/other）、质量（cold/warm/hot）、状态（new/contacted/confirmed/converted/closed）、行业、备注、分配人

**线索转化流程**：线索确认 → 自动创建客户 + 商机

**招标雷达增强**（v3.5 新增）：
- 关键词管理：添加/删除监测关键词
- 来源配置：配置招标信息来源网站
- 配置面板：`fetchBiddingConfig` 统一管理

### 2.6 渠道管理

| 页面 | 路由 | 说明 |
|------|------|------|
| 渠道档案 | `/partners` | 伙伴CRUD、联系人管理、抽屉详情 |
| 渠道业绩 | `/partners/performance` | 商机转化统计、业绩排行（按月/全部） |
| 渠道培训 | `/partners/growth` | 伙伴认证、培训记录、违规管理 |
| 项目报备 | `/partners/registration` | 报备申请/审批/编辑/删除、规则配置 |
| 返点管理 | `/partners/commission` | 返点比例、结算周期、伙伴关联 |

**渠道属性**：名称、联系人、电话、描述、等级（金牌/银牌/铜牌/注册）、区域、状态

### 2.7 售前协同

| 页面 | 路由 | 说明 |
|------|------|------|
| 售前协同 | `/presales` | 售前请求CRUD、分配、状态跟踪、SLA监控 |
| 售前资产 | `/presales/assets` | 方案文档管理、下载、分类、子分类 |

**售前请求属性**：商机关联、请求内容、售前负责人、状态、SLA时效

### 2.8 产品管理 `/products`

**功能**：
- 产品CRUD（写操作仅 admin）
- 一级分类 + 二级子分类层级
- 拖拽排序（产品、分类、子分类均可拖拽）
- 子分类管理（添加/编辑/删除）
- 推荐产品 `/products/recommendations`（行业-产品匹配）

**产品属性**：名称、分类、子分类、描述、单价、状态（启用/禁用）、排序权重

### 2.9 今日待跟进 `/follow-ups`

卡片式工作台：**逾期** → **今日** → **近7天** 三级分类展示。快捷跟进、一键跳转商机详情。

### 2.10 通知系统（v3.5 新增）

| 功能 | 说明 |
|------|------|
| 未读通知 | 顶部铃铛图标 + 未读计数 |
| 通知类型 | 售前请求通知、渠道报备通知 |
| 通知操作 | 标记已读、查看详情 |
| 持久化 | `localStorage` 存储已读状态（`getReadNotices`/`saveReadNotices`） |

### 2.11 网安业务 `/security-business`（隐藏）

渠道报备、售前技术支持、招投标雷达订阅/采集、客户安全画像评估。

**v3.5 增强**：报备编辑/删除功能、报备通知集成。

### 2.12 销售增长 `/sales-growth`（隐藏）

销售预测、目标设定/追踪、客户分层运营记录、商机复盘、伙伴增长记录。

### 2.13 管理后台 `/admin`

仅管理员可访问：
- **用户管理**：CRUD + 密码重置 + 角色分配
- **菜单管理**：侧栏菜单可见性开关
- **阶段管理**：商机5阶段配置（名称/颜色/进度）

---

## 三、API 端点清单

系统共 **106 个唯一 API 端点**，按模块分类：

### 3.1 认证（3）
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/auth/login` | 登录，返回 JWT Token |
| GET | `/api/auth/me` | 当前用户信息及菜单 |
| PUT | `/api/auth/change-password` | 修改密码 |

### 3.2 仪表盘（3）
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/dashboard/stats` | 核心统计（角色过滤） |
| GET | `/api/dashboard/sales-performance?period=` | 销售绩效排行 |
| GET | `/api/dashboard/partner-performance?period=` | 渠道业绩排行 |

### 3.3 客户（9）
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/customers` | 列表（owner_id/关键词/分页） |
| POST | `/api/customers` | 创建 |
| GET/PUT/DELETE | `/api/customers/:id` | 详情/更新/删除 |
| GET | `/api/customers/:id/contacts` | 联系人列表 |
| POST | `/api/customers/:id/contacts` | 添加联系人 |
| PUT/DELETE | `/api/customers/:id/contacts/:cid` | 编辑/删除联系人 |

### 3.4 商机（5）
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/opportunities` | 列表（sales_rep_id/阶段/类型/分页） |
| POST | `/api/opportunities` | 创建 |
| GET/PUT/DELETE | `/api/opportunities/:id` | 详情/更新/删除 |
| GET | `/api/opportunities/stats/summary` | 统计摘要 |

### 3.5 线索（8）
| 方法 | 路径 | 说明 |
|------|------|------|
| GET/POST | `/api/leads` | 列表/创建 |
| GET/PUT/DELETE | `/api/leads/:id` | 详情/更新/删除 |
| POST | `/api/leads/:id/convert` | 转化线索 |
| GET | `/api/leads/stats/funnel` | 线索漏斗 |
| GET | `/api/leads/sales/list` | 销售列表（脱敏） |

### 3.6 招标（8）
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/bidding/collect` | 采集招标 |
| GET/POST/DELETE | `/api/bidding/keywords` | 关键词管理 |
| GET/POST/DELETE | `/api/bidding/sources` | 来源配置 |

### 3.7 产品（8）
| 方法 | 路径 | 说明 |
|------|------|------|
| GET/POST | `/api/products` | 列表/创建 |
| GET/PUT/DELETE | `/api/products/:id` | 详情/更新/删除 |
| GET | `/api/products/categories` | 分类树 |
| POST/PUT/DELETE | `/api/products/sub-categories/:id` | 子分类CRUD |
| PUT | `/api/products/reorder` | 拖拽排序 |

### 3.8 渠道（10）
| 方法 | 路径 | 说明 |
|------|------|------|
| GET/POST | `/api/channel-partners` | 列表/创建 |
| GET/PUT/DELETE | `/api/channel-partners/:id` | 详情/更新/删除 |
| GET/POST | `/api/commissions` | 返点列表/创建 |
| PUT/DELETE | `/api/commissions/:id` | 返点更新/删除 |
| GET | `/api/commissions/partners` | 可返点伙伴列表 |

### 3.9 跟进（4）
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/follow-ups?opportunity_id=` | 商机跟进列表 |
| POST | `/api/follow-ups` | 创建跟进 |
| POST | `/api/follow-ups/:id/quick-log` | 快捷跟进（JSON） |
| GET | `/api/follow-ups/today` | 今日待跟进 |

### 3.10 安全业务 / 售前（16）
| 方法 | 路径 | 说明 |
|------|------|------|
| GET/POST | `/api/security-business/channel-registrations` | 渠道报备 |
| PUT/DELETE | `/api/security-business/channel-registrations/:id` | 报备操作 |
| GET/POST/PUT | `/api/security-business/presales-requests` | 售前请求 |
| GET | `/api/security-business/presales-notifications` | 售前通知 |
| GET | `/api/security-business/channel-registration-notifications` | 报备通知 |
| GET/POST | `/api/security-business/bid-radar/subscriptions` | 招标订阅 |
| GET/POST | `/api/security-business/bid-radar/items` | 招标条目 |
| POST | `/api/security-business/bid-radar/collect` | 招标采集 |
| GET | `/api/security-business/bid-radar/tasks` | 招标任务 |
| GET/PUT | `/api/security-business/customer-profiles/:id` | 客户画像 |

### 3.11 经营驾驶舱（12）
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/business-excellence/bi-dashboard` | BI看板 |
| GET | `/api/business-excellence/customer-duplicates` | 客户去重 |
| GET | `/api/business-excellence/presales-sla` | 售前SLA |
| GET | `/api/business-excellence/partner-credit-scores` | 渠道信用 |
| GET | `/api/business-excellence/customer-maturity-scores` | 客户成熟度 |
| GET/POST/PUT/DELETE | `/api/business-excellence/industry-product-recommendations` | 行业推荐 |
| POST | `/api/business-excellence/industry-product-recommendations/seed` | 种子数据 |
| GET/DELETE | `/api/business-excellence/presales-assets` | 售前资产 |
| POST | `/api/business-excellence/forecast-snapshots` | 预测快照 |
| GET | `/api/business-excellence/forecast-accuracy` | 预测准确度 |
| POST | `/api/business-excellence/bid-radar/items/:id/convert` | 招标转化 |

### 3.12 销售增长（10）
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/sales-growth/forecast?group_by=` | 预测汇总 |
| GET/POST | `/api/sales-growth/targets/summary` | 目标管理 |
| GET/PUT | `/api/sales-growth/customer-operations` | 客户运营 |
| GET/POST | `/api/sales-growth/opportunity-reviews` | 商机复盘 |
| GET/POST | `/api/sales-growth/partner-growth/records` | 伙伴增长记录 |
| GET | `/api/sales-growth/partner-growth/summary` | 伙伴增长汇总 |
| GET | `/api/sales-growth/users` | 用户列表 |

### 3.13 系统管理（10）
| 方法 | 路径 | 说明 |
|------|------|------|
| GET/PUT | `/api/stages` | 阶段配置 |
| GET | `/api/industries` | 行业列表 |
| GET/PUT | `/api/menu-config` | 菜单配置 |
| GET/POST | `/api/users` | 用户管理 |
| PUT | `/api/users/:id/reset-password` | 密码重置 |
| POST | `/api/import/confirm?type=` | 数据导入 |
| GET | `/api/audit-logs` | 审计日志 |
| GET | `/api/export/...` | 数据导出 |
| GET | `/api/utils/validate-company?name=` | 公司名校验 |

---

## 四、数据模型

系统共 **40+ 张数据库表**，按业务域分类：

### 4.1 核心业务表

| 表名 | 用途 | 关键字段 |
|------|------|----------|
| `users` | 用户 | username, password_hash(PBKDF2), real_name, role, manager_id |
| `customers` | 客户 | name, industry, level, owner_id, address, website |
| `opportunities` | 商机 | name, opp_type, stage, amount, sales_rep_id, probability |
| `contacts` | 联系人 | name, customer_id/partner_id, position, phone, email |
| `leads` | 线索 | name, company, source, quality, status, assigned_to |
| `products` | 产品 | name, category, sub_category, unit_price, sort_order |
| `follow_ups` | 跟进记录 | opportunity_id, creator_id, content, contact_person |
| `channel_partners` | 渠道伙伴 | name, level, region, contact_person, created_by |

### 4.2 配置表

| 表名 | 用途 |
|------|------|
| `stage_configs` | 商机阶段配置（label/color/pct） |
| `menu_config` | 侧栏菜单结构（层级/可见性） |
| `industry_configs` | 行业列表 |
| `product_sub_categories` | 产品子分类 |
| `commission_rules` | 返点规则 |

### 4.3 安全业务表

| 表名 | 用途 |
|------|------|
| `channel_registrations` | 渠道项目报备 |
| `channel_registration_rules` | 报备规则配置 |
| `channel_registration_governance` | 报备治理/审批 |
| `presales_requests` | 售前支持请求 |
| `presales_sla_rules` | 售前SLA规则 |
| `presales_sla_tracking` | 售前SLA追踪 |
| `presales_assets` | 售前资产/文档 |
| `bid_radar_subscriptions` | 招标关键词订阅 |
| `bid_radar_items` | 招标条目 |
| `bid_radar_follow_tasks` | 招标跟进任务 |
| `bid_conversions` | 招标→商机转化记录 |
| `bid_score_criteria` | 招标评分标准 |
| `customer_security_profiles` | 客户安全画像 |

### 4.4 客户深度表

| 表名 | 用途 |
|------|------|
| `customer_identities` | 客户决策链联系人 |
| `customer_decision_nodes` | 决策图谱节点 |
| `customer_decision_edges` | 决策图谱关系 |
| `customer_competitor_installs` | 竞品安装信息 |
| `customer_operation_profiles` | 客户运营记录 |
| `customer_maturity_scores` | 客户成熟度评分 |

### 4.5 经营分析表

| 表名 | 用途 |
|------|------|
| `sales_targets` | 销售目标设定 |
| `opportunity_reviews` | 商机复盘记录 |
| `partner_growth_records` | 渠道成长/培训记录 |
| `industry_product_recommendations` | 行业-产品推荐 |
| `forecast_snapshots` | 预测快照 |
| `poc_records` | POC测试记录 |

### 4.6 系统表

| 表名 | 用途 |
|------|------|
| `audit_logs` | 操作审计日志（操作人/路径/状态码） |
| `audit_changes` | 变更快照（操作前后数据对比） |

---

## 五、安全架构

### 5.1 认证
- **算法**：JWT HS256，密钥来自 `JWT_SECRET_KEY` 环境变量
- **密码**：PBKDF2-SHA256 + 16字节随机盐 + 100,000次迭代，向后兼容旧SHA256
- **过期**：24小时

### 5.2 授权
- **5种角色**：admin / manager / sales / channel_manager / presales
- **数据隔离**：`scoped_*_query` 系列函数自动按角色过滤查询
- **操作控制**：产品/渠道/线索写操作仅 admin

### 5.3 安全措施
- **CORS**：白名单域名（localhost:8097, 127.0.0.1:8097, 121.41.66.121）
- **XSS**：`innerHTML` 错误信息 HTML 标签转义
- **审计**：全部 POST/PUT/DELETE 记录操作快照
- **依赖**：Python 依赖使用 `==` 精确版本锁

---

## 六、部署运维

### 6.1 服务器配置

| 项目 | 值 |
|------|-----|
| 服务器 | 阿里云 Ubuntu 22.04 |
| 后端端口 | 8097（127.0.0.1 仅本地） |
| 反向代理 | Nginx → `/api/` 转发 |
| 前端路径 | `/opt/aq-crm/frontend/` |
| 后端路径 | `/opt/aq-crm/backend/` |
| 数据库 | `/opt/aq-crm/backend/aq_crm.db`（SQLite WAL） |

### 6.2 运维工具

| 脚本 | 用途 |
|------|------|
| `deploy/systemd/aq-crm.service` | systemd 服务定义 |
| `deploy/nginx/aq-crm.conf` | Nginx 配置模板 |
| `deploy/env/aq-crm.env.example` | 环境变量示例 |
| `backend/scripts/backup_db.py` | 数据库备份 |
| `backend/scripts/restore_db.py` | 数据库恢复 |
| `backend/scripts/migrate_sqlite_to_db.py` | SQLite → PostgreSQL 迁移 |

---

## 七、已知限制

| 类别 | 说明 | 建议 |
|------|------|------|
| 性能 | 前端 318KB 单文件，无懒加载 | 超过 350KB 后考虑代码分割 |
| 数据库 | SQLite 单文件，不支持并发写入 | 用户量 >50 时考虑 PostgreSQL |
| 通知 | 无实时推送 | 可考虑 WebSocket |
| 招标雷达 | 外部数据源依赖手动配置 | 需对接公开招标 API |
| 搜索 | 仅支持关键词匹配 | 可考虑全文索引 |
| 移动端 | 无响应式适配 | 按需开发移动端 |

---

> **文档版本**：v2.0 | **基于代码版本**：服务器 318KB 前端 / GitHub `0bbd3b2+`  
> **生成日期**：2026-07-09 | **作者**：AQClaw
