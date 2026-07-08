from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from app.routers.auth import get_current_user
import os, urllib.request, json
from datetime import datetime

router = APIRouter(prefix="/api/admin", tags=["管理部署"])

GITHUB_REPO = "neilhero/AQ-CRM-Platform"
GITHUB_FILE = "frontend/index.html"
DEPLOY_PATH = "/opt/aq-crm/frontend/index.html"
TOKEN_FILE = "/opt/aq-crm/backend/.ghtoken"


def _require_admin(current_user=Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return current_user


def _read_token():
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE) as f:
            return f.read().strip()
    return None


@router.post("/set-token")
def set_github_token(token: str = Query(...), _=Depends(_require_admin)):
    """设置 GitHub Personal Access Token（admin 权限）"""
    with open(TOKEN_FILE, 'w') as f:
        f.write(token.strip())
    os.chmod(TOKEN_FILE, 0o600)
    return {"ok": True, "msg": "Token 已保存"}


@router.get("/deploy-status")
def deploy_status(_=Depends(get_current_user)):
    """检查部署状态"""
    token = _read_token()
    token_ok = bool(token)
    git_ok = False
    if token:
        try:
            url = f"https://api.github.com/repos/{GITHUB_REPO}"
            req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}", "User-Agent": "AQ-CRM"})
            urllib.request.urlopen(req, timeout=10)
            git_ok = True
        except Exception:
            pass

    last_deploy = None
    deploy_size = None
    if os.path.exists(DEPLOY_PATH):
        mtime = os.path.getmtime(DEPLOY_PATH)
        last_deploy = datetime.fromtimestamp(mtime).isoformat()
        deploy_size = os.path.getsize(DEPLOY_PATH)

    return {
        "token_set": token_ok,
        "github_ok": git_ok,
        "last_deploy": last_deploy,
        "deploy_size": deploy_size,
        "repo": GITHUB_REPO,
    }


@router.post("/deploy-frontend")
def deploy_frontend(_=Depends(_require_admin)):
    """从 GitHub 拉取最新 index.html 并部署到 /opt/aq-crm/frontend/"""
    token = _read_token()
    if not token:
        raise HTTPException(status_code=400, detail="未设置 GitHub Token，请先 POST /api/admin/set-token?token=ghp_xxx")

    url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/{GITHUB_FILE}"

    try:
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}", "User-Agent": "AQ-CRM"})
        r = urllib.request.urlopen(req, timeout=30)
        content = r.read()

        # 备份旧版
        if os.path.exists(DEPLOY_PATH):
            with open(DEPLOY_PATH, 'rb') as src:
                with open(DEPLOY_PATH + ".bak", 'wb') as dst:
                    dst.write(src.read())

        # 写入新版
        with open(DEPLOY_PATH, 'wb') as f:
            f.write(content)

        # 校验
        text = content.decode('utf-8')
        ok = '安泉' in text and 'function OppListPage' in text

        return {
            "ok": ok,
            "size": len(content),
            "backup": DEPLOY_PATH + ".bak",
        }
    except urllib.error.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"GitHub {e.code}: {e.reason}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"部署失败: {str(e)}")
