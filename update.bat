@echo off
chcp 65001 >nul
cd /d C:\DingDanGuanLi
"C:\Program Files\Git\cmd\git.exe" pull
if %errorlevel% neq 0 (
    echo GIT_PULL_FAILED
    exit /b 1
)
echo GIT_PULL_SUCCESS
del /q data.db 2>nul
python init_db.py
echo DB_INIT_DONE