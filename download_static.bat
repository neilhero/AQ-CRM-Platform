@echo off
echo ========================================
echo   AnQuan CRM v3.2 - Download CDN Assets
echo ========================================
echo.

if not exist "frontend\static" mkdir frontend\static

echo [1/7] React 18...
curl -sL -o frontend\static\react.min.js https://registry.npmmirror.com/react/18.2.0/files/umd/react.production.min.js
if %errorlevel% neq 0 echo FAILED & exit /b 1

echo [2/7] React-DOM 18...
curl -sL -o frontend\static\react-dom.min.js https://registry.npmmirror.com/react-dom/18.2.0/files/umd/react-dom.production.min.js

echo [3/7] DayJS...
curl -sL -o frontend\static\dayjs.min.js https://registry.npmmirror.com/dayjs/1.11.10/files/dayjs.min.js

echo [4/7] Ant Design 5.17...
curl -sL -o frontend\static\antd.min.js https://registry.npmmirror.com/antd/5.17.0/files/dist/antd.min.js

echo [5/7] Ant Design Icons...
curl -sL -o frontend\static\antd-icons.min.js https://registry.npmmirror.com/@ant-design/icons/5.3.0/files/dist/index.umd.min.js

echo [6/7] Axios...
curl -sL -o frontend\static\axios.min.js https://registry.npmmirror.com/axios/1.6.5/files/dist/axios.min.js

echo [7/7] Ant Design CSS...
curl -sL -o frontend\static\antd.min.css https://registry.npmmirror.com/antd/5.17.0/files/dist/reset.css

echo.
echo ========================================
echo   Done! All CDN assets downloaded.
echo   Run: cd backend ^&^& python -m uvicorn app.main:app --port 8097
echo ========================================
pause
