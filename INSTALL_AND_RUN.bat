@echo off
echo ========================================
echo   TV Downloader - Установка и запуск
echo ========================================
echo.

echo [1/2] Установка зависимостей...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo ОШИБКА: Не удалось установить зависимости
    echo Проверьте, что Python установлен правильно
    pause
    exit /b 1
)

echo.
echo [2/2] Запуск загрузчика...
echo.
python run.py

pause

