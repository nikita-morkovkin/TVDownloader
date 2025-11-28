"""
Скрипт для запуска TV Downloader.
"""
import sys
from pathlib import Path

# Добавляем корневую папку проекта в путь
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Запускаем главный модуль
if __name__ == "__main__":
    from src.main import main
    import asyncio
    asyncio.run(main())

