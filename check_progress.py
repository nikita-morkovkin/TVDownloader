"""
Скрипт для проверки текущего прогресса загрузки видео.
Показывает статистику по всем каналам из метаданных.
"""
import json
import sys
from pathlib import Path
from datetime import datetime


def format_size(size_bytes: int) -> str:
    """Форматирование размера файла в читаемый вид."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} PB"


def check_progress():
    """Проверка текущего прогресса загрузки."""
    # Определяем путь к метаданным
    current_file = Path(__file__).resolve()
    project_root = current_file.parent
    metadata_file = project_root / "data" / "downloaded_files.json"
    
    if not metadata_file.exists():
        print("❌ Метаданные не найдены.")
        print(f"   Файл: {metadata_file}")
        print("   Загрузка еще не началась или файл не был создан.")
        return
    
    try:
        with open(metadata_file, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
    except Exception as e:
        print(f"❌ Ошибка при чтении метаданных: {e}")
        return
    
    if not metadata:
        print("📭 Метаданные пусты. Файлы еще не скачаны.")
        return
    
    print("=" * 70)
    print("📊 ТЕКУЩИЙ ПРОГРЕСС ЗАГРУЗКИ")
    print("=" * 70)
    
    total_channels = len(metadata)
    total_files_all = 0
    total_size_all = 0
    
    for channel_name, channel_data in metadata.items():
        total_files = channel_data.get('total_files', 0)
        total_size = channel_data.get('total_size', 0)
        last_updated = channel_data.get('last_updated', 'N/A')
        
        # Форматируем дату
        try:
            if last_updated != 'N/A':
                dt = datetime.fromisoformat(last_updated)
                last_updated = dt.strftime("%Y-%m-%d %H:%M:%S")
        except:
            pass
        
        total_files_all += total_files
        total_size_all += total_size
        
        print(f"\n📺 Канал: {channel_name}")
        print(f"   ✅ Скачано файлов: {total_files}")
        print(f"   💾 Общий размер: {format_size(total_size)}")
        print(f"   🕐 Последнее обновление: {last_updated}")
        
        # Показываем информацию о последних файлах
        messages = channel_data.get('messages', {})
        if messages:
            print(f"   📝 Всего записей в метаданных: {len(messages)}")
    
    print("\n" + "=" * 70)
    print("📈 ОБЩАЯ СТАТИСТИКА")
    print("=" * 70)
    print(f"   Каналов обработано: {total_channels}")
    print(f"   Всего файлов скачано: {total_files_all}")
    print(f"   Общий размер: {format_size(total_size_all)}")
    print("=" * 70)


if __name__ == "__main__":
    try:
        check_progress()
    except KeyboardInterrupt:
        print("\n\nПрервано пользователем")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        sys.exit(1)

