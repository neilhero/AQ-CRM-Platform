# Deployment Notes

## Frontend

`frontend/index.html` is the main production entry file. `admin.html` and
`static/version.js` are released together with it.

On the production server, `frontend/fallback.html` is a symbolic link to
`frontend/index.html`. The repository therefore does not keep a second
`fallback.html` copy. A second tracked copy can become stale and writing it on
the server follows the symbolic link, overwriting the main page.

Deploy with:

```powershell
.\deploy\deploy-frontend.ps1
```

The script uploads all frontend release files and verifies their production
SHA-256 hashes after upload. It also checks critical dashboard and
opportunity-form markers before deployment so a stale frontend cannot silently
replace the current UI.

## Formal release

Use `publish-release.ps1` for a formal version release. It requires a clean Git
worktree, creates a production snapshot, backs up the database, deploys backend
and frontend code, reloads Nginx, and checks the API version.

See `docs/RELEASE.md` for the full versioning, tagging, release and rollback
workflow.
