"""
Менеджер загрузок с поддержкой параллельных загрузок и очереди.
"""
import asyncio
import logging
import time
from typing import List, Optional, Callable, Dict
from pathlib import Path
from tqdm.asyncio import tqdm
from tqdm import tqdm as sync_tqdm
from telethon.tl.types import Message, MessageMediaDocument, MessageMediaPhoto
from telethon.errors import FloodWaitError

from .file_handler import FileHandler
from .video_quality import VideoQualityHandler

logger = logging.getLogger(__name__)


class DownloadManager:
    """Менеджер для управления загрузкой файлов."""

    def __init__(
        self,
        client,
        file_handler: FileHandler,
        quality_handler: VideoQualityHandler,
        max_concurrent: int = 5,
        retry_attempts: int = 3,
        retry_delay: int = 5
    ):
        """
        Инициализация менеджера загрузок.

        Args:
            client: Telegram клиент
            file_handler: Обработчик файлов
            quality_handler: Обработчик качества видео
            max_concurrent: Максимальное количество одновременных загрузок
            retry_attempts: Количество попыток при ошибке
            retry_delay: Задержка между попытками (секунды)
        """
        self.client = client
        self.file_handler = file_handler
        self.quality_handler = quality_handler
        self.max_concurrent = max_concurrent
        self.retry_attempts = retry_attempts
        self.retry_delay = retry_delay
        
        self.downloaded_count = 0
        self.skipped_count = 0
        self.failed_count = 0
        self.total_size = 0
        
        # Словарь для хранения прогресс-баров активных загрузок
        self.active_progress_bars: Dict[int, sync_tqdm] = {}

    def _create_progress_callback(self, message_id: int, file_name: str, total_size: int) -> Callable:
        """
        Создание callback для отслеживания прогресса загрузки.

        Args:
            message_id: ID сообщения
            file_name: Имя файла
            total_size: Общий размер файла в байтах

        Returns:
            Callback функция для telethon
        """
        # Создаем прогресс-бар для этого файла
        pbar = sync_tqdm(
            total=total_size,
            unit='B',
            unit_scale=True,
            unit_divisor=1024,
            desc=file_name[:50],  # Ограничиваем длину имени
            leave=False,  # Не оставляем прогресс-бар после завершения
            ncols=100
        )
        
        self.active_progress_bars[message_id] = pbar
        last_update_time = time.time()
        last_downloaded = 0

        def callback(current: int, total: int):
            """Callback для обновления прогресса."""
            nonlocal last_update_time, last_downloaded
            
            # Обновляем прогресс-бар
            if pbar.total != total:
                pbar.total = total
            pbar.n = current
            pbar.refresh()
            
            # Вычисляем скорость загрузки
            current_time = time.time()
            time_diff = current_time - last_update_time
            
            if time_diff >= 1.0:  # Обновляем скорость раз в секунду
                downloaded_diff = current - last_downloaded
                speed = downloaded_diff / time_diff if time_diff > 0 else 0
                
                # Обновляем описание с информацией о скорости
                speed_str = self.file_handler.format_file_size(speed) + "/s"
                pbar.set_postfix_str(speed_str)
                
                last_update_time = current_time
                last_downloaded = current

        return callback

    async def _download_description(self, message: Message, series_folder: Path) -> bool:
        """
        Скачивание описания в файл description.txt.

        Args:
            message: Сообщение с видео
            series_folder: Папка серии

        Returns:
            True если описание сохранено
        """
        try:
            description_text = ""
            
            # Получаем текст сообщения
            if hasattr(message, 'message') and message.message:
                description_text = message.message.strip()
            
            # Если есть описание, сохраняем его
            if description_text:
                description_file = series_folder / "description.txt"
                with open(description_file, 'w', encoding='utf-8') as f:
                    f.write(description_text)
                logger.debug(f"Сохранено описание: {description_file}")
                return True
            else:
                logger.debug("Описание отсутствует")
                return False
        except Exception as e:
            logger.warning(f"Ошибка при сохранении описания: {e}")
            return False

    async def _download_poster(self, message: Message, series_folder: Path, client) -> bool:
        """
        Скачивание картинки-постера (если есть).

        Args:
            message: Сообщение с видео
            series_folder: Папка серии
            client: Telegram клиент

        Returns:
            True если постер скачан
        """
        try:
            # Проверяем, есть ли фото в сообщении
            if message.media and isinstance(message.media, MessageMediaPhoto):
                poster_file = series_folder / "poster.jpg"
                await client.download_media(message.media, file=str(poster_file))
                if poster_file.exists() and poster_file.stat().st_size > 0:
                    logger.debug(f"Скачан постер: {poster_file}")
                    return True
            
            # Проверяем, есть ли thumbnail в документе
            if message.media and hasattr(message.media, 'document'):
                doc = message.media.document
                if doc and hasattr(doc, 'thumbs') and doc.thumbs and len(doc.thumbs) > 0:
                    # Пробуем скачать thumbnail
                    poster_file = series_folder / "poster.jpg"
                    try:
                        # Скачиваем thumbnail используя thumb параметр
                        await client.download_media(message, thumb=doc.thumbs[0], file=str(poster_file))
                        if poster_file.exists() and poster_file.stat().st_size > 0:
                            logger.debug(f"Скачан постер из thumbnail: {poster_file}")
                            return True
                    except Exception as thumb_error:
                        logger.debug(f"Не удалось скачать thumbnail: {thumb_error}")
                        # Пробуем альтернативный способ - скачать как фото
                        try:
                            await client.download_media(message, file=str(poster_file), thumb=-1)
                            if poster_file.exists() and poster_file.stat().st_size > 0:
                                logger.debug(f"Скачан постер альтернативным способом: {poster_file}")
                                return True
                        except:
                            pass
            
            logger.debug("Постер отсутствует")
            return False
        except Exception as e:
            logger.debug(f"Ошибка при скачивании постера: {e}")
            return False

    async def download_video(
        self,
        message: Message,
        channel_name: str,
        progress_callback: Optional[Callable] = None
    ) -> bool:
        """
        Загрузка одного видео с описанием и постером.

        Структура папок:
        downloads/
          channel_name/
            series_name/
              series_name.480p.mp4
              series_name.720p.mp4
              description.txt
              poster.jpg

        Args:
            message: Сообщение с видео
            channel_name: Имя канала
            progress_callback: Callback для прогресса (если None, создается автоматически)

        Returns:
            True если загрузка успешна
        """
        message_id = message.id
        
        # Проверяем, не скачан ли уже файл
        if self.file_handler.is_file_downloaded(message_id, channel_name):
            logger.debug(f"Файл {message_id} уже скачан, пропускаем")
            self.skipped_count += 1
            return False

        # Проверяем качество видео
        if not message.media or not isinstance(message.media, MessageMediaDocument):
            logger.warning(f"Сообщение {message_id} не содержит видео")
            return False

        document = message.media.document
        should_download, quality = self.quality_handler.should_download_video(document)
        
        if not should_download:
            logger.debug(f"Видео {message_id} не подходит по качеству, пропускаем")
            self.skipped_count += 1
            return False

        # Получаем название серии
        series_name = self._get_series_name(message)
        
        # Создаем папку для серии
        series_folder = self.file_handler.get_series_folder(channel_name, series_name)
        
        # Скачиваем описание (только один раз для серии)
        description_file = series_folder / "description.txt"
        if not description_file.exists():
            await self._download_description(message, series_folder)
        
        # Скачиваем постер (только один раз для серии)
        poster_file = series_folder / "poster.jpg"
        if not poster_file.exists():
            await self._download_poster(message, series_folder, self.client)
        
        # Определяем имя файла в новом формате: название.качество.mp4
        file_name = self._get_file_name(series_name, quality)
        file_path = series_folder / file_name

        # Проверяем, не скачан ли уже файл этого качества
        if file_path.exists():
            logger.debug(f"Файл {file_name} уже существует, пропускаем")
            self.skipped_count += 1
            return False

        # Получаем размер файла для прогресс-бара
        total_size = document.size if hasattr(document, 'size') else 0
        
        # Создаем callback для прогресса, если не передан
        if progress_callback is None:
            progress_callback = self._create_progress_callback(message_id, file_name, total_size)

        # Пробуем загрузить с повторными попытками
        for attempt in range(self.retry_attempts):
            try:
                # Загружаем файл
                await self.client.download_media(
                    message,
                    file=str(file_path),
                    progress_callback=progress_callback
                )
                
                # Закрываем прогресс-бар после успешной загрузки
                if message_id in self.active_progress_bars:
                    self.active_progress_bars[message_id].close()
                    del self.active_progress_bars[message_id]

                # Проверяем, что файл действительно скачан
                if file_path.exists():
                    file_size = file_path.stat().st_size
                    self.total_size += file_size
                    
                    # Отмечаем как скачанный
                    self.file_handler.mark_file_as_downloaded(
                        message_id,
                        channel_name,
                        str(file_path),
                        file_size,
                        quality
                    )
                    
                    self.downloaded_count += 1
                    logger.info(f"✓ Скачано: {series_name}/{file_name} ({self.file_handler.format_file_size(file_size)})")
                    return True
                else:
                    raise Exception("Файл не был создан после загрузки")

            except FloodWaitError as e:
                logger.warning(f"FloodWait: нужно подождать {e.seconds} секунд")
                await asyncio.sleep(e.seconds)
                # Не считаем это как попытку, продолжаем
                continue

            except Exception as e:
                # Закрываем прогресс-бар при ошибке
                if message_id in self.active_progress_bars:
                    self.active_progress_bars[message_id].close()
                    del self.active_progress_bars[message_id]
                
                logger.warning(f"Попытка {attempt + 1}/{self.retry_attempts} не удалась для {message_id}: {e}")
                if attempt < self.retry_attempts - 1:
                    await asyncio.sleep(self.retry_delay)
                else:
                    logger.error(f"Не удалось скачать {message_id} после {self.retry_attempts} попыток")
                    self.failed_count += 1
                    return False

        return False

    def _sanitize_filename(self, filename: str) -> str:
        """
        Очистка имени файла от недопустимых символов.

        Args:
            filename: Имя файла для очистки

        Returns:
            Очищенное имя файла
        """
        # Заменяем недопустимые символы на подчеркивания
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '_')
        
        # Удаляем лишние пробелы и точки
        filename = filename.strip('. ')
        
        # Ограничиваем длину (Windows ограничение - 255 символов, но оставляем запас)
        if len(filename) > 200:
            filename = filename[:200]
        
        return filename

    def _get_series_name(self, message: Message) -> str:
        """
        Получение названия серии из сообщения.

        Приоритет:
        1. Текст сообщения (если есть)
        2. Имя из атрибутов документа
        3. ID сообщения

        Args:
            message: Сообщение с видео

        Returns:
            Название серии
        """
        series_name = None
        
        # Приоритет 1: Пробуем получить название из текста сообщения
        if hasattr(message, 'message') and message.message:
            text = message.message.strip()
            if text:
                # Очищаем текст от лишних символов
                text = text.replace('\n', ' ').replace('\r', ' ')
                # Берем первые 150 символов (чтобы не было слишком длинно)
                series_name = text[:150].strip()
                logger.debug(f"Использован текст сообщения для названия: {series_name[:50]}...")
        
        # Приоритет 2: Пробуем получить имя из документа
        if not series_name and message.media and hasattr(message.media, 'document'):
            doc = message.media.document
            if doc and hasattr(doc, 'attributes'):
                for attr in doc.attributes:
                    if hasattr(attr, 'file_name') and attr.file_name:
                        # Убираем расширение
                        name_parts = attr.file_name.rsplit('.', 1)
                        series_name = name_parts[0]
                        logger.debug(f"Использовано имя из документа: {series_name}")
                        break
        
        # Приоритет 3: Генерируем по ID сообщения
        if not series_name:
            series_name = f"video_{message.id}"
            logger.debug(f"Использован ID сообщения для названия: {series_name}")
        
        # Очищаем имя от недопустимых символов
        series_name = self._sanitize_filename(series_name)
        
        return series_name

    def _get_file_name(self, series_name: str, quality: Optional[int] = None) -> str:
        """
        Генерация имени файла для видео.

        Формат: название.качество.mp4
        Например: я люблю сестру.720p.mp4

        Args:
            series_name: Название серии
            quality: Качество видео (обязательно)

        Returns:
            Имя файла
        """
        extension = "mp4"
        
        # Формируем имя в формате: название.качество.mp4
        if quality:
            file_name = f"{series_name}.{quality}p.{extension}"
        else:
            file_name = f"{series_name}.{extension}"
        
        return file_name

    async def download_batch(
        self,
        messages: List[Message],
        channel_name: str
    ) -> Dict:
        """
        Загрузка пакета видео с параллелизмом.

        Args:
            messages: Список сообщений для загрузки
            channel_name: Имя канала

        Returns:
            Словарь со статистикой загрузки
        """
        if not messages:
            return {
                'downloaded': 0,
                'skipped': 0,
                'failed': 0,
                'total_size': 0
            }

        # Создаем семафор для ограничения параллелизма
        semaphore = asyncio.Semaphore(self.max_concurrent)
        
        # Создаем прогресс-бар
        pbar = tqdm(total=len(messages), desc=f"Загрузка из {channel_name}", unit="файл")

        async def download_with_semaphore(message: Message):
            """Загрузка с ограничением параллелизма."""
            async with semaphore:
                result = await self.download_video(message, channel_name)
                pbar.update(1)
                return result

        # Запускаем все загрузки
        tasks = [download_with_semaphore(msg) for msg in messages]
        await asyncio.gather(*tasks)
        
        pbar.close()

        return {
            'downloaded': self.downloaded_count,
            'skipped': self.skipped_count,
            'failed': self.failed_count,
            'total_size': self.total_size
        }

    def get_statistics(self) -> Dict:
        """
        Получение статистики загрузок.

        Returns:
            Словарь со статистикой
        """
        return {
            'downloaded': self.downloaded_count,
            'skipped': self.skipped_count,
            'failed': self.failed_count,
            'total_size': self.total_size,
            'total_size_formatted': self.file_handler.format_file_size(self.total_size)
        }

    def reset_statistics(self):
        """Сброс статистики."""
        self.downloaded_count = 0
        self.skipped_count = 0
        self.failed_count = 0
        self.total_size = 0

