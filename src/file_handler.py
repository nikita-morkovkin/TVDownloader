"""
Модуль для обработки файлов, проверки дубликатов и организации по каналам.
"""
import os
import json
import logging
from pathlib import Path
from typing import Dict, Set, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class FileHandler:
    """Обработчик файлов и метаданных."""

    def __init__(self, download_path: str = "./downloads", data_path: str = "./data"):
        """
        Инициализация обработчика файлов.

        Args:
            download_path: Путь для сохранения файлов
            data_path: Путь для сохранения метаданных
        """
        self.download_path = Path(download_path)
        self.data_path = Path(data_path)
        self.metadata_file = self.data_path / "downloaded_files.json"
        
        # Создаем необходимые папки
        self.download_path.mkdir(parents=True, exist_ok=True)
        self.data_path.mkdir(parents=True, exist_ok=True)
        
        # Загружаем метаданные
        self.metadata = self._load_metadata()

    def _load_metadata(self) -> Dict:
        """Загрузка метаданных из файла."""
        if self.metadata_file.exists():
            try:
                with open(self.metadata_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Ошибка при загрузке метаданных: {e}, создаем новый файл")
                return {}
        return {}

    def _save_metadata(self):
        """Сохранение метаданных в файл."""
        try:
            with open(self.metadata_file, 'w', encoding='utf-8') as f:
                json.dump(self.metadata, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Ошибка при сохранении метаданных: {e}")

    def get_channel_folder(self, channel_name: str) -> Path:
        """
        Получение пути к папке канала.

        Args:
            channel_name: Имя канала

        Returns:
            Path к папке канала
        """
        channel_folder = self.download_path / channel_name
        channel_folder.mkdir(parents=True, exist_ok=True)
        return channel_folder

    def get_series_folder(self, channel_name: str, series_name: str) -> Path:
        """
        Получение пути к папке серии.

        Args:
            channel_name: Имя канала
            series_name: Название серии

        Returns:
            Path к папке серии
        """
        channel_folder = self.get_channel_folder(channel_name)
        # Очищаем имя серии от недопустимых символов
        invalid_chars = '<>:"/\\|?*'
        safe_series_name = series_name
        for char in invalid_chars:
            safe_series_name = safe_series_name.replace(char, '_')
        # Ограничиваем длину
        safe_series_name = safe_series_name[:200].strip('. ')
        
        series_folder = channel_folder / safe_series_name
        series_folder.mkdir(parents=True, exist_ok=True)
        return series_folder

    def is_file_downloaded(self, message_id: int, channel_name: str) -> bool:
        """
        Проверка, скачан ли уже файл.

        Args:
            message_id: ID сообщения
            channel_name: Имя канала

        Returns:
            True если файл уже скачан и существует на диске
        """
        channel_key = channel_name
        if channel_key not in self.metadata:
            return False

        message_key = str(message_id)
        message_data = self.metadata[channel_key].get('messages', {}).get(message_key)
        if not message_data:
            return False

        # Проверяем, существует ли файл на диске и его размер совпадает
        file_path = message_data.get('file_path')
        expected_size = message_data.get('file_size', 0)
        
        if file_path:
            file = Path(file_path)
            if file.exists():
                actual_size = file.stat().st_size
                # Если размер совпадает (или файл больше ожидаемого - возможно обновлен),
                # считаем что файл скачан
                if actual_size >= expected_size and expected_size > 0:
                    return True
                # Если файл существует, но размер меньше ожидаемого - файл неполный,
                # нужно перезагрузить
                elif actual_size < expected_size:
                    logger.debug(
                        f"Файл {file_path} неполный: {actual_size} < {expected_size}, "
                        f"будет перезагружен"
                    )
                    return False

        return False

    def mark_file_as_downloading(
        self,
        message_id: int,
        channel_name: str,
        file_path: str,
        expected_size: int,
        quality: Optional[int] = None
    ):
        """
        Отметка файла как начатого к загрузке (сохраняет метаданные сразу).

        Args:
            message_id: ID сообщения
            channel_name: Имя канала
            file_path: Путь к файлу
            expected_size: Ожидаемый размер файла
            quality: Качество видео (опционально)
        """
        channel_key = channel_name
        if channel_key not in self.metadata:
            self.metadata[channel_key] = {
                'channel_name': channel_name,
                'messages': {},
                'total_files': 0,
                'total_size': 0,
                'last_updated': None
            }

        message_key = str(message_id)
        is_new = message_key not in self.metadata[channel_key]['messages']
        
        # Сохраняем метаданные с пометкой "в процессе"
        self.metadata[channel_key]['messages'][message_key] = {
            'file_path': file_path,
            'file_size': expected_size,  # Ожидаемый размер
            'quality': quality,
            'status': 'downloading',  # Статус: в процессе загрузки
            'started_at': datetime.now().isoformat()
        }
        
        # Обновляем статистику только для новых файлов
        if is_new:
            self.metadata[channel_key]['total_files'] += 1
        
        self.metadata[channel_key]['last_updated'] = datetime.now().isoformat()
        self._save_metadata()

    def mark_file_as_downloaded(
        self,
        message_id: int,
        channel_name: str,
        file_path: str,
        file_size: int,
        quality: Optional[int] = None
    ):
        """
        Отметка файла как полностью скачанного.

        Args:
            message_id: ID сообщения
            channel_name: Имя канала
            file_path: Путь к файлу
            file_size: Реальный размер файла
            quality: Качество видео (опционально)
        """
        channel_key = channel_name
        if channel_key not in self.metadata:
            self.metadata[channel_key] = {
                'channel_name': channel_name,
                'messages': {},
                'total_files': 0,
                'total_size': 0,
                'last_updated': None
            }

        message_key = str(message_id)
        is_new = message_key not in self.metadata[channel_key]['messages']
        
        # Обновляем метаданные - файл полностью скачан
        old_data = self.metadata[channel_key]['messages'].get(message_key, {})
        old_size = old_data.get('file_size', 0)
        
        self.metadata[channel_key]['messages'][message_key] = {
            'file_path': file_path,
            'file_size': file_size,  # Реальный размер
            'quality': quality,
            'status': 'completed',  # Статус: завершено
            'downloaded_at': datetime.now().isoformat()
        }
        
        # Обновляем статистику
        if is_new:
            self.metadata[channel_key]['total_files'] += 1
            self.metadata[channel_key]['total_size'] += file_size
        else:
            # Если файл был в процессе загрузки, обновляем размер
            if old_size != file_size:
                self.metadata[channel_key]['total_size'] = (
                    self.metadata[channel_key]['total_size'] - old_size + file_size
                )
        
        self.metadata[channel_key]['last_updated'] = datetime.now().isoformat()
        self._save_metadata()

    def get_download_statistics(self) -> Dict:
        """
        Получение статистики скачанных файлов.

        Returns:
            Словарь со статистикой
        """
        stats = {
            'total_channels': len(self.metadata),
            'total_files': 0,
            'total_size': 0,
            'channels': {}
        }

        for channel_key, channel_data in self.metadata.items():
            channel_stats = {
                'files': channel_data.get('total_files', 0),
                'size': channel_data.get('total_size', 0),
                'last_updated': channel_data.get('last_updated')
            }
            stats['channels'][channel_key] = channel_stats
            stats['total_files'] += channel_stats['files']
            stats['total_size'] += channel_stats['size']

        return stats

    def format_file_size(self, size_bytes: int) -> str:
        """
        Форматирование размера файла в читаемый вид.

        Args:
            size_bytes: Размер в байтах

        Returns:
            Отформатированная строка
        """
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f} PB"

