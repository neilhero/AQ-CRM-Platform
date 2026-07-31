# Deployment Notes

## Frontend

`frontend/index.html` is the only production entry file.

On the production server, `frontend/fallback.html` is a symbolic link to
`frontend/index.html`. The repository therefore does not keep a second
`fallback.html` copy. A second tracked copy can become stale and writing it on
the server follows the symbolic link, overwriting the main page.

Deploy with:

```powershell
.\deploy\deploy-frontend.ps1
```

The script uploads only `index.html` and verifies the production SHA-256 hash
after upload. It also checks critical dashboard and opportunity-form markers
before deployment so a stale frontend cannot silently replace the current UI.
