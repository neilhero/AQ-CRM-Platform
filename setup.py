"""
AQ-CRM 部署指南
================
本文件为部署参考文档，不会自动执行任何系统级操作。

## 前置条件
- Ubuntu 22.04+ / Python 3.10+
- Nginx（反向代理）
- systemd（服务管理）

## 1. 安装依赖
    cd backend
    pip install -r requirements.txt

## 2. 配置环境变量（推荐）
    export JWT_SECRET_KEY=$(python -c "import secrets;print(secrets.token_hex(32))")

## 3. 启动后端（临时测试）
    cd backend
    python -m uvicorn app.main:app --host 127.0.0.1 --port 8097

## 4. 配置 systemd 服务
    参考 deploy/systemd/aq-crm.service 复制到 /etc/systemd/system/
    systemctl daemon-reload && systemctl enable --now aq-crm

## 5. 配置 Nginx 反向代理
    参考 deploy/nginx/aq-crm.conf 复制到 /etc/nginx/sites-available/
    ln -sf /etc/nginx/sites-available/aq-crm /etc/nginx/sites-enabled/
    nginx -t && systemctl restart nginx

## 6. 部署前端
    将 frontend/index.html 及 frontend/static/ 复制到 /opt/aq-crm/frontend/

## 安全建议
- 首次启动后立即修改 admin 默认密码
- 将 JWT_SECRET_KEY 写入 /etc/environment 或 systemd 环境变量
- 启用 HTTPS（Let's Encrypt + certbot）
- 限制 CORS 白名单为用户实际域名
"""

if __name__ == "__main__":
    print(__doc__)
    print("\n⚠ 此脚本仅为文档，不会自动部署。请按上面步骤手动操作。")
