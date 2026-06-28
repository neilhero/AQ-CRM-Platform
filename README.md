# 安泉CRM v3.2 (AQ-CRM-Platform)

安泉数智科技有限公司客户关系管理系统。

## 技术栈

- **后端**: FastAPI + SQLAlchemy + SQLite + JWT
- **前端**: React 18 + Ant Design 5（单文件 HTML）
- **部署**: Nginx 反向代理 + systemd

## 快速启动

### 1. 安装依赖

```bash
cd backend
pip install -r requirements.txt
cd ..
python setup.py
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

- 前端: `http://localhost:8097`（或通过 Nginx 代理 80 端口）
- API 文档: `http://localhost:8097/docs`

## 默认账号

| 用户名 | 密码 | 角色 |
|--------|------|------|
| admin | admin123 | 管理员 |
| channel001 | channel123 | 渠道经理 |
| sales001 | sales123 | 销售 |

## 项目结构

```
AQ-CRM-Platform/
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI 入口 + 种子数据
│   │   ├── database.py      # SQLite 数据库配置
│   │   ├── models/          # SQLAlchemy 数据模型
│   │   ├── routers/         # API 路由
│   │   ├── schemas/         # Pydantic 数据校验
│   │   └── services/        # 认证服务
│   └── requirements.txt
├── frontend/
│   ├── index.html           # 单文件 React 前端
│   └── static/              # CDN 依赖（需下载）
└── setup.py
```
