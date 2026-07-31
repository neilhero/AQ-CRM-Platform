# 安泉 CRM 发布规范

## 发布原则

1. 版本号只在根目录 `VERSION` 维护，页面、后台和 API 都从它同步。
2. 每次上线必须先提交 Git，再发布；发布脚本拒绝携带未提交的文件上线。
3. 每次发布自动保留数据库备份和前端/后端文件快照。出现问题时先回滚文件，数据库仅在确认需要时回滚。
4. 每个正式版本必须有 `CHANGELOG.md` 记录和 Git 标签，例如 `v3.7.0`。

## 日常修复发布

1. 修改根目录 `VERSION`，例如 `3.7.0` 改为 `3.7.1`。
2. 更新 `CHANGELOG.md`，说明本次新增、优化和修复。
3. 执行 `./deploy/sync-version.ps1`，同步前端版本文件。
4. 完成功能测试后执行：

```powershell
git add .
git commit -m "release: v3.7.1"
git tag -a v3.7.1 -m "安泉CRM v3.7.1"
./deploy/publish-release.ps1
git push origin main --follow-tags
```

发布脚本会在上线前检查工作区干净、保存服务器快照、备份数据库、重启后端并调用 `/api/system/version` 核验版本。

## 紧急回滚

发布完成后脚本会打印快照目录。只回滚页面和后端代码：

```powershell
./deploy/rollback-release.ps1 -Snapshot /opt/aq-crm/backups/releases/pre-v3.7.1-20260731-120000
```

仅在确认数据也需回退时才额外传入 `-RestoreDatabase`。数据库回滚会丢弃快照之后的数据，必须谨慎使用。

## 版本含义

- `3.7.1`：补丁版本，修复缺陷或做小范围体验调整。
- `3.8.0`：次版本，增加完整业务能力或明显可感知的模块升级。
- `4.0.0`：主版本，包含不兼容的数据结构、流程或权限模型调整。
