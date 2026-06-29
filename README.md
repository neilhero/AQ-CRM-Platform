# 安泉CRM v3.4 (AQ-CRM-Platform)

安泉数智科技有限公司客户关系管理系统。

## 技术栈

- **后端**: FastAPI + SQLAlchemy + SQLite + JWT（端口 8097）
- **前端**: React 18 + Ant Design 5（单文件 HTML，CDN 本地化）
- **管理后台**: 独立 React 单页（/admin）
- **部署**: Nginx 反向代理 + systemd

## 功能模块

| 模块 | 说明 |
|------|------|
| 仪表盘 | 关键指标统计看板 |
| 今日待跟进 | 逾期/今日/即将到期跟进提醒 |
| 客户管理 | 客户 CRUD + 嵌套联系人 + 数据权限隔离 |
| 商机管理 | 直销商机 + 渠道商机，销售漏斗追踪 |
| 线索管理 | 线索录入、分配、转换 |
| 产品管理 | 产品目录维护 |
| 渠道伙伴管理 | 伙伴档案、绩效、返点管理 |
| 招标采集 | 招标信息自动采集入库 |
| 数据导入 | 模板下载 → 预览 → 确认三步导入 |
| 用户管理 | 用户 CRUD + 密码重置（仅管理员） |
| 菜单管理 | v3.4 新增，侧栏菜单显隐开关 |

## 快速启动

### 1. 安装依赖

```bash
cd backend
pip install -r requirements.txt
```

### 2. 下载前端 CDN 依赖

```bash
mkdir -p frontend/static
curl -sL -o frontend/static/react.min.js https://registry.npmmirror.com/react/18.2.0/files/umd/react.production.min.js
curl -sL -o frontend/static/react-dom.min.js https://registry.npmmirror.com/react-dom/18.2.0/files/umd/react-dom.production.min.js
curl -sL -o frontend/static/dayjs.min.js https://registry.npmmirror.com/dayjs/1.11.10/files/dayjs.min.js
curl -sL -o frontend/static/antd.min.js https://registry.npmmirror.com/antd/5.17.0/files/dist/antd.min.js
curl -sL -o frontend/static/antd-icons.min.js https://registry.npmmirror.com/@ant-design/icons/5.3.0/files/dist/index.umd.min.js
curl -sL -o frontend/static/axios.min.js https://registry.npmmirror.com/axios/1.6.5/files/dist/axios.min.js
curl -sL -o frontend/static/antd.min.css https://registry.npmmirror.com/antd/5.17.0/files/dist/reset.css
```

### 3. 启动后端

```bash
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8097
```

### 4. 访问

- 前端 CRM: `http://localhost:8097`（或通过 Nginx 代理 80 端口）
- 管理后台: `http://localhost:8097/admin`
- API 文档: `http://localhost:8097/docs`

## 首次启动

系统首次启动时自动创建种子数据（3个用户、8个客户、5个产品、3个渠道伙伴、12个菜单项）。默认账号密码由种子脚本定义，详见 `backend/app/main.py` 中 `seed()` 函数。**生产环境请立即修改默认密码。**

## API 端点

| 路径 | 方法 | 说明 |
|------|------|------|
| /api/auth/login | POST | 登录（返回 JWT token） |
| /api/auth/me | GET | 当前用户信息 |
| /api/auth/change-password | PUT | 修改密码 |
| /api/customers | CRUD | 客户管理 |
| /api/customers/{id}/contacts | GET/POST | 客户下联系人（嵌套路由） |
| /api/opportunities | CRUD | 商机管理 |
| /api/products | CRUD | 产品管理 |
| /api/channel | CRUD | 渠道伙伴管理 |
| /api/contacts | CRUD | 联系人管理 |
| /api/leads | CRUD + convert | 线索管理 |
| /api/follow-ups/today | GET | 今日跟进统计 |
| /api/dashboard/stats | GET | 仪表盘统计 |
| /api/bidding/collect | POST | 招标采集 |
| /api/import/ | POST | 数据导入（模板/预览/确认） |
| /api/users | CRUD + reset-password | 用户管理（仅 admin） |
| /api/menu-config | GET/PUT | 菜单配置（v3.4） |

## 种子数据

- **8 客户**：浙江省政府云、上海AI研究院、北京智慧城市中心、广州数据局、深圳科技大学、江苏移动、工商银行数据中心、杭州公安
- **5 产品**：安泉大模型防火墙 v3.0、安泉数据防泄漏系统、安泉AI教育平台、安泉智能体安全套件、安泉红队测试工具
- **3 渠道伙伴**：北京网安科技(金牌)、上海安信网络(银牌)、深圳锐安信安(铜牌)
- **12 菜单项**：仪表盘、今日待跟进、客户管理、商机管理(组)、直销商机、渠道商机、线索管理、产品管理、渠道伙伴管理(组)、伙伴档案、伙伴绩效、返点管理

## 项目结构

```
AQ-CRM-Platform/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI 入口 + 种子数据 + 嵌套路由
│   │   ├── database.py          # SQLite 数据库配置（WAL模式）
│   │   ├── models/              # SQLAlchemy 数据模型（10表）
│   │   ├── routers/             # API 路由（14个模块）
│   │   ├── schemas/             # Pydantic 数据校验
│   │   └── services/            # 认证服务
│   └── requirements.txt
├── frontend/
│   ├── index.html               # 单文件 React 前端（~160KB）
│   ├── admin.html               # 管理后台（独立页面）
│   └── static/                  # CDN 依赖（本地化）
└── setup.py
```

## 版本历史

| 版本 | 更新内容 |
|------|----------|
| v3.4 | 菜单管理系统（侧栏动态显隐 + 管理后台开关） |
| v3.3 | 数据权限隔离（owner_id）、嵌套联系人路由、用户管理 |
| v3.2 | 仪表盘统计、销售业绩分析、今日跟进 |
| v3.1 | 渠道伙伴管理、返点规则、商机报备 |
| v3.0 | 初始版本：客户、商机、产品基础 CRUD |
