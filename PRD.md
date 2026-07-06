# 安泉CRM v3.5 产品需求文档

## 一、产品概述

### 1.1 产品定位
安泉CRM是一款面向安泉数智科技有限公司的轻量级客户关系管理系统，覆盖从线索获取、客户管理、商机跟踪到招投标、售前协同、渠道管理的完整业务链路。

### 1.2 版本信息
| 项目 | 说明 |
|------|------|
| 版本号 | v3.5 |
| 发布日期 | 2026-07-06 |
| 技术架构 | FastAPI + React 18 + Ant Design 5 + SQLite |
| 部署方式 | 单页HTML + systemd + Nginx 反向代理 |

### 1.3 用户角色体系

| 角色 | 标识 | 权限级别 | 可见范围 |
|------|------|----------|----------|
| 管理员 | `admin` | 全部 | 所有数据，含管理后台 |
| 销售主管 | `manager` | 高级 | 本人 + 下属销售数据 |
| 销售 | `sales` | 基础 | 仅本人数据 |
| 渠道经理 | `channel_manager` | 渠道 | 渠道相关商机与客户 |
| 售前工程师 | `presales` | 售前 | 被分配的售前请求相关商机 |

**权限控制系统**（`permissions.py`）：
- **数据隔离**：基于 `managed_user_ids`（主管可见下属）、`presales_opportunity_ids`（售前可见分配商机）
- **查询过滤**：`scoped_opportunity_query` / `scoped_customer_query` / `scoped_lead_query` 自动按角色过滤
- **操作审计**：全部 POST/PUT/DELETE 操作记录到 `audit_logs` + `audit_changes` 表，含操作前后快照

---

## 二、功能模块

### 2.1 仪表盘

| 页面 | 路由 | 功能描述 |
|------|------|----------|
| 仪表盘 | `/dashboard` | 销售漏斗（5阶段可视化）、今日待跟进、销售绩效排行、关键KPI卡片 |
| 经营驾驶舱 | `/business-excellence` | BI看板、客户去重检测、售前SLA监控、渠道信用评分、预测准确度、投标转化分析 |

**核心指标**：商机总数、活跃商机数、总金额（按角色过滤）、阶段分布、销售绩效排名

### 2.2 客户管理

| 页面 | 路由 | 功能描述 |
|------|------|----------|
| 客户列表 | `/customers` | 客户CRUD、搜索、行业/等级筛选、客户抽屉详情 |
| 客户360画像 | `/customers/profile` | 安全维度分析、客户成熟度评估、决策链图谱、竞品信息 |
| 客户分层运营 | `/customers/operations` | 客户运营记录、分层策略 |

**客户属性**：名称、行业、地址、网站、等级(VIP/A/B/C)、描述、负责人

**客户抽屉（CustomerDrawer）**：
- 联系人管理（CRUD，行内编辑）
- 关联商机列表
- 基本信息和操作历史

### 2.3 商机管理

| 页面 | 路由 | 功能描述 |
|------|------|----------|
| 直销商机 | `/opportunities/direct` | 看板视图（拖拽变更阶段）+ 表格视图 |
| 渠道商机 | `/opportunities/channel` | 同上，渠道类型商机 |
| 商机详情 | `/opportunities/:id` | 详细信息、跟进记录、售前请求、编辑/删除 |

**商机5阶段**（可配置）：
| 阶段 | 名称 | 进度 |
|------|------|------|
| 1 | 获取项目信息 | 20% |
| 2 | 见到用户/渠道 | 40% |
| 3 | 技术交流/试用 | 60% |
| 4 | 明确合作意向 | 80% |
| 5 | 确定合作/招投标 | 100% |

**商机属性**：名称、类型（直销/渠道）、金额、销售负责人、客户、渠道伙伴、行业、阶段、概率(HIGH/MID_HIGH/MID/LOW)、关键人、处理人、预计成交日、下次跟进日、状态

**核心操作**：
- 新建商机（自动绑定当前销售）
- 看板拖拽变更阶段（KanbanBoard 组件）
- 快捷跟进记录（支持接触人）
- 售前支持请求
- 商机删除（权限校验）

### 2.4 线索管理

| 页面 | 路由 | 功能描述 |
|------|------|----------|
| 线索列表 | `/leads` | 线索CRUD、来源/质量/状态筛选、漏斗统计 |
| 招标雷达 | `/leads/bid-radar` | 关键词订阅、自动采集、招标任务管理 |
| 招标转化 | `/leads/bid-conversion` | 招标项目转商机、评分标准配置 |

**线索属性**：名称、公司、联系人、电话、来源(website/exhibition/partner/phone/bidding/other)、质量(cold/warm/hot)、状态(new/contacted/confirmed/converted/closed)、行业、备注、分配人

**线索转化**：线索 → 自动创建客户 + 商机

### 2.5 渠道管理

| 页面 | 路由 | 功能描述 |
|------|------|----------|
| 渠道档案 | `/partners` | 伙伴CRUD、联系人、抽屉详情 |
| 渠道绩效 | `/partners/performance` | 绩效报表（按周期统计） |
| 渠道成长 | `/partners/growth` | 成长记录、里程碑 |
| 项目报备 | `/partners/registration` | 渠道报备申请、审批、规则配置 |
| 返点管理 | `/partners/commission` | 返点规则CRUD（比例、结算周期） |
| 渠道信用 | `/partners/credit` | 信用评分（默认隐藏） |

**渠道属性**：名称、联系人、电话、描述、等级（金牌/银牌/铜牌/注册）、区域、状态

### 2.6 售前协同

| 页面 | 路由 | 功能描述 |
|------|------|----------|
| 售前协同 | `/presales` | 售前请求CRUD、分配、状态跟踪、SLA监控 |
| 售前资产 | `/presales/assets` | 方案文档管理、下载、分类 |

**售前请求属性**：商机关联、请求内容、售前负责人、状态、SLA时效

### 2.7 产品管理

| 页面 | 路由 | 功能描述 |
|------|------|----------|
| 产品列表 | `/products` | 产品CRUD、分类展示、拖拽排序 |
| 推荐产品 | `/products/recommendations` | 行业-产品推荐、种子数据 |

**产品属性**：名称、分类、子分类、描述、单价、状态(启用/禁用)

**新增功能**：
- 产品分类层级（一级分类 + 二级子分类）
- 拖拽排序（产品和分类均可拖拽调整顺序）
- 子分类管理（添加、编辑、删除）

### 2.8 今日待跟进

| 页面 | 路由 | 功能描述 |
|------|------|----------|
| 跟进工作台 | `/follow-ups` | 卡片式展示：逾期 > 今日 > 近期（7天内） |

**核心操作**：快捷跟进、跳转商机详情

### 2.9 网安业务（隐藏）

| 页面 | 路由 | 功能描述 |
|------|------|----------|
| 网安业务 | `/security-business` | 渠道报备、售前请求、招投标雷达、客户安全画像 |

**子模块**：
- 渠道报备登记
- 售前技术支持请求
- 招投标雷达订阅与采集
- 客户安全画像评估

### 2.10 销售增长（隐藏）

| 页面 | 路由 | 功能描述 |
|------|------|----------|
| 销售增长 | `/sales-growth` | 预测、目标、客户运营、商机复盘、伙伴增长 |

**子模块**：
- 销售预测（按时间分组统计）
- 目标管理（设定/追踪）
- 客户分层运营记录
- 商机复盘（经验沉淀）
- 伙伴增长记录

### 2.11 管理后台

| 页面 | 路由 | 功能描述 |
|------|------|----------|
| 管理后台 | `/admin` | 用户管理、菜单管理、阶段管理 |

**仅管理员可访问**。支持：
- 用户CRUD + 密码重置
- 侧栏菜单可见性控制
- 商机5阶段配置（名称/颜色/进度）

---

## 三、API端点清单

### 3.1 认证
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/auth/login` | 登录，返回JWT Token |
| GET | `/api/auth/me` | 当前用户信息及菜单权限 |
| PUT | `/api/auth/change-password` | 修改密码 |

### 3.2 客户
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/customers` | 列表（支持 owner_id/关键词/分页） |
| POST | `/api/customers` | 创建 |
| GET/PUT/DELETE | `/api/customers/:id` | 详情/更新/删除 |
| GET | `/api/customers/:id/contacts` | 客户联系人列表 |
| POST | `/api/customers/:id/contacts` | 添加联系人 |
| PUT/DELETE | `/api/customers/:id/contacts/:cid` | 编辑/删除联系人 |

### 3.3 商机
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/opportunities` | 列表（支持 sales_rep_id/阶段/类型/分页） |
| POST | `/api/opportunities` | 创建 |
| GET/PUT/DELETE | `/api/opportunities/:id` | 详情/更新/删除 |
| GET | `/api/opportunities/stats/summary` | 统计摘要 |

### 3.4 跟进
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/follow-ups?opportunity_id=` | 商机跟进列表 |
| POST | `/api/follow-ups` | 创建跟进 |
| POST | `/api/follow-ups/:id/quick-log` | 快捷跟进（JSON body） |
| GET | `/api/follow-ups/today` | 今日待跟进（逾期/今日/近期） |

### 3.5 线索
| 方法 | 路径 | 说明 |
|------|------|------|
| GET/POST | `/api/leads` | 列表/创建 |
| GET/PUT/DELETE | `/api/leads/:id` | 详情/更新/删除 |
| POST | `/api/leads/:id/convert` | 转化为客户+商机 |
| GET | `/api/leads/stats/funnel` | 线索漏斗 |
| GET | `/api/leads/sales/list` | 销售列表（脱敏） |

### 3.6 产品
| 方法 | 路径 | 说明 |
|------|------|------|
| GET/POST | `/api/products` | 列表/创建 |
| GET/PUT/DELETE | `/api/products/:id` | 详情/更新/删除 |
| GET | `/api/products/categories` | 分类 + 子分类树 |
| POST/PUT/DELETE | `/api/products/sub-categories/:id` | 子分类CRUD |
| PUT | `/api/products/reorder` | 拖拽排序 |

### 3.7 渠道
| 方法 | 路径 | 说明 |
|------|------|------|
| GET/POST | `/api/channel-partners` | 列表/创建 |
| GET/PUT/DELETE | `/api/channel-partners/:id` | 详情/更新/删除 |
| GET/POST | `/api/commissions` | 返点列表/创建 |
| PUT/DELETE | `/api/commissions/:id` | 返点更新/删除 |

### 3.8 售前
| 方法 | 路径 | 说明 |
|------|------|------|
| GET/POST/PUT | `/api/security-business/presales-requests` | 售前请求CRUD |
| GET | `/api/security-business/presales-notifications` | 售前通知 |

### 3.9 招投标
| 方法 | 路径 | 说明 |
|------|------|------|
| GET/POST | `/api/security-business/bid-radar/subscriptions` | 订阅管理 |
| GET/POST | `/api/security-business/bid-radar/items` | 招标条目 |
| POST | `/api/security-business/bid-radar/collect` | 采集 |
| GET | `/api/security-business/bid-radar/tasks` | 任务列表 |

### 3.10 其他
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/dashboard/stats` | 仪表盘统计 |
| GET | `/api/dashboard/sales-performance` | 销售绩效 |
| GET | `/api/dashboard/partner-performance` | 渠道绩效 |
| GET/PUT | `/api/stages` | 阶段配置 |
| GET | `/api/industries` | 行业列表 |
| GET/PUT | `/api/menu-config` | 菜单配置 |
| GET/POST | `/api/users` | 用户列表/创建 |
| PUT | `/api/users/:id/reset-password` | 密码重置 |
| POST | `/api/import/confirm` | 数据导入 |
| GET | `/api/audit-logs` | 操作审计日志 |
| GET | `/api/export/...` | 数据导出 |
| GET | `/api/utils/validate-company` | 公司名称校验 |

### 3.11 经营驾驶舱
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/business-excellence/bi-dashboard` | BI看板 |
| GET | `/api/business-excellence/customer-duplicates` | 客户去重 |
| GET | `/api/business-excellence/presales-sla` | 售前SLA |
| GET | `/api/business-excellence/partner-credit-scores` | 渠道信用 |
| GET | `/api/business-excellence/customer-maturity-scores` | 客户成熟度 |
| GET/POST/PUT/DELETE | `/api/business-excellence/industry-product-recommendations` | 行业推荐 |
| POST | `/api/business-excellence/industry-product-recommendations/seed` | 种子推荐 |
| GET/DELETE | `/api/business-excellence/presales-assets` | 售前资产 |
| POST | `/api/business-excellence/forecast-snapshots` | 预测快照 |
| GET | `/api/business-excellence/forecast-accuracy` | 预测准确度 |
| POST | `/api/business-excellence/bid-radar/items/:id/convert` | 招标转商机 |

### 3.12 销售增长
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/sales-growth/forecast` | 预测 |
| GET | `/api/sales-growth/targets/summary` | 目标汇总 |
| POST | `/api/sales-growth/targets` | 设定目标 |
| GET | `/api/sales-growth/customer-operations` | 客户运营 |
| PUT | `/api/sales-growth/customer-operations/:id` | 更新运营 |
| GET/POST | `/api/sales-growth/opportunity-reviews` | 商机复盘 |
| GET/POST | `/api/sales-growth/partner-growth/records` | 伙伴增长 |
| GET | `/api/sales-growth/partner-growth/summary` | 伙伴增长汇总 |
| GET | `/api/sales-growth/users` | 用户列表 |

---

## 四、数据模型（核心表）

| 表名 | 用途 | 关键字段 |
|------|------|----------|
| `users` | 用户 | username, password_hash(PBKDF2), real_name, role, manager_id |
| `customers` | 客户 | name, industry, level, owner_id, address, website |
| `opportunities` | 商机 | name, opp_type, stage, amount, sales_rep_id, customer_id, probability, expected_close_date, next_follow_up_date |
| `contacts` | 联系人 | name, customer_id/partner_id, position, phone, email, wechat |
| `leads` | 线索 | name, company, source, quality, status, assigned_to |
| `products` | 产品 | name, category, sub_category, unit_price, sort_order |
| `product_sub_categories` | 产品子分类 | category, name, sort_order |
| `channel_partners` | 渠道伙伴 | name, level, region, contact_person |
| `follow_ups` | 跟进记录 | opportunity_id, creator_id, content, contact_person |
| `commission_rules` | 返点规则 | partner_id, rate_percent, settlement_cycle |
| `stage_configs` | 阶段配置 | stage_key, label, color, pct, sort_order |
| `menu_config` | 菜单配置 | menu_key, label, is_visible, parent_key, sort_order |
| `industry_configs` | 行业配置 | name, is_active |
| `audit_logs` | 操作审计 | user_id, method, path, status_code, action |
| `audit_changes` | 变更快照 | entity_type, entity_id, before_snapshot, after_snapshot |
| `channel_registrations` | 渠道报备 | name, partner_id, status, registration_type |
| `presales_requests` | 售前请求 | opportunity_id, owner_id, status, content |
| `bid_radar_subscriptions` | 招标订阅 | keywords, frequency |
| `bid_radar_items` | 招标条目 | title, url, publish_date, deadline, source |
| `bid_radar_follow_tasks` | 招标任务 | item_id, assigned_to, status |
| `customer_security_profiles` | 客户安全画像 | customer_id, security_level, assessment |
| `customer_identities` | 客户决策链 | customer_id, name, role_type, influence |
| `customer_decision_nodes` | 决策节点 | customer_id, label, type |
| `customer_decision_edges` | 决策关系 | from_node, to_node, relation |
| `customer_competitor_installs` | 竞品信息 | customer_id, competitor_name, product |
| `sales_targets` | 销售目标 | user_id, period_label, target_amount |
| `customer_operation_profiles` | 客户运营 | customer_id, operation_type, content |
| `opportunity_reviews` | 商机复盘 | opportunity_id, review_content, lessons |
| `partner_growth_records` | 伙伴增长 | partner_id, metric, value, recorded_at |
| `industry_product_recommendations` | 行业推荐 | industry, product_category, product_sub_category |
| `presales_assets` | 售前资产 | name, category, file_url, file_name |
| `forecast_snapshots` | 预测快照 | period_label, forecast_data |
| `bid_conversions` | 投标转化 | bid_item_id, opportunity_id, conversion_date |
| `bid_score_criteria` | 评分标准 | name, weight, description |
| `presales_sla_rules` | SLA规则 | severity, response_hours, resolve_hours |
| `presales_sla_tracking` | SLA追踪 | request_id, breached, response_time |
| `channel_registration_rules` | 报备规则 | rule_type, config |
| `channel_registration_governance` | 报备治理 | registration_id, review_status |

---

## 五、安全架构

### 5.1 认证
- **JWT Token**：HS256算法，密钥来自环境变量 `JWT_SECRET_KEY`，24小时过期
- **密码哈希**：PBKDF2-SHA256 + 随机盐 + 100,000次迭代，向后兼容旧的SHA256格式
- **Token验证**：`require_user` 依赖项从 Authorization Header 提取 Bearer Token

### 5.2 授权
- **角色基础**：5种角色，`permissions.py` 统一管理
- **数据隔离**：`scoped_*_query` 系列函数自动按角色过滤查询结果
- **操作控制**：产品/渠道/线索的写操作仅 admin

### 5.3 安全加固
- **CORS**：白名单域名（localhost:8097, 127.0.0.1:8097, 121.41.66.121）
- **XSS防护**：前端 `innerHTML` 错误信息转义 HTML 标签
- **依赖锁版本**：所有 Python 依赖使用 `==` 精确版本
- **审计日志**：全部写操作记录操作人、路径、状态码、前后快照

---

## 六、技术架构

### 6.1 后端
| 组件 | 技术选型 |
|------|----------|
| Web框架 | FastAPI 0.110.0 |
| ORM | SQLAlchemy 2.0.30 |
| 数据库 | SQLite（WAL模式） |
| 认证 | PyJWT 2.8.0 |
| 数据校验 | Pydantic 2.7.0 |
| 服务管理 | systemd（端口8097，127.0.0.1） |
| 反向代理 | Nginx |

### 6.2 前端
| 组件 | 技术选型 |
|------|----------|
| UI框架 | React 18 |
| 组件库 | Ant Design 5 |
| 构建方式 | 单文件HTML（296KB），CDN改为本地 static/ |
| 路由 | Hash路由（window.location.hash） |
| HTTP | 原生 fetch 封装（`api()` 函数） |

### 6.3 部署
- 服务器：阿里云 Ubuntu 22.04（121.41.66.121）
- 部署路径：`/opt/aq-crm/`（backend/ + frontend/）
- 配置文件：`deploy/systemd/aq-crm.service` + `deploy/nginx/aq-crm.conf`

---

## 七、已知限制与规划

| 类别 | 项目 | 说明 |
|------|------|------|
| 性能 | 单文件 296KB | 无懒加载，所有页面代码同时载入 |
| 安全 | 招标雷达自动采集 | 当前无外部数据源对接，仅有API接口 |
| 数据 | SQLite | 适合轻量部署，高并发需迁移至 PostgreSQL |
| 体验 | 缺少全局 loading/empty/error 三态 | 部分新增模块需完善 |
| 架构 | 单文件维护 | 超过300KB后建议拆分 React 组件 |

---

> **文档版本**：v1.0 | **生成日期**：2026-07-06 | **基于代码版本**：GitHub `9aa61e6`
