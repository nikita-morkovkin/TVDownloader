"""
Модуль для определения и выбора качества видео из Telegram.
"""
import logging
from typing import List, Optional, Tuple
from telethon.tl.types import Document, DocumentAttributeVideo

logger = logging.getLogger(__name__)


class VideoQualityHandler:
    """Обработчик качества видео."""

    # Целевые качества в пикселях (высота)
    TARGET_QUALITIES = [360, 480, 720]

    def __init__(self, target_qualities: List[int] = None, download_nearest: bool = True):
        """
        Инициализация обработчика качества.

        Args:
            target_qualities: Список целевых качеств (по умолчанию [360, 480, 720])
            download_nearest: Скачивать ближайшее меньшее качество, если точного нет
        """
        self.target_qualities = target_qualities or self.TARGET_QUALITIES
        self.download_nearest = download_nearest
        # Сортируем качества по возрастанию
        self.target_qualities = sorted(self.target_qualities)

    def get_video_quality(self, document: Document) -> Optional[int]:
        """
        Получение качества видео из документа.

        Args:
            document: Документ Telegram

        Returns:
            Высота видео в пикселях или None
        """
        for attr in document.attributes:
            if isinstance(attr, DocumentAttributeVideo):
                return attr.h  # Высота видео
        return None

    def should_download_video(self, document: Document) -> Tuple[bool, Optional[int]]:
        """
        Определение, нужно ли скачивать видео и какое качество выбрать.

        Логика выбора:
        1. Если доступное качество точно совпадает с целевым - скачиваем его
        2. Если доступное качество выше целевых - выбираем максимальное целевое качество
        3. Если доступное качество ниже целевых - выбираем ближайшее меньшее (если включено)

        Args:
            document: Документ Telegram

        Returns:
            Кортеж (нужно_ли_скачивать, выбранное_качество)
        """
        video_quality = self.get_video_quality(document)
        if video_quality is None:
            # Если не удалось определить качество, скачиваем
            logger.debug("Не удалось определить качество видео, скачиваем")
            return True, None

        # Проверяем, совпадает ли качество с целевыми
        if video_quality in self.target_qualities:
            logger.debug(f"Найдено целевое качество: {video_quality}p")
            return True, video_quality

        # Если точного совпадения нет
        if self.download_nearest:
            # Ищем максимальное целевое качество, которое не превышает доступное
            # (т.е. выбираем лучшее качество из доступных целевых)
            best_quality = None
            for target_q in reversed(self.target_qualities):  # Идем от большего к меньшему
                if video_quality >= target_q:
                    best_quality = target_q
                    break

            if best_quality:
                logger.debug(
                    f"Выбрано лучшее доступное качество: {best_quality}p "
                    f"(доступно {video_quality}p, целевые: {self.target_qualities})"
                )
                return True, best_quality
            else:
                # Если доступное качество меньше всех целевых
                logger.debug(
                    f"Доступное качество {video_quality}p меньше всех целевых "
                    f"({self.target_qualities}), пропускаем"
                )
                return False, None
        else:
            # Если не скачивать ближайшее, пропускаем
            logger.debug(
                f"Качество {video_quality}p не совпадает с целевыми "
                f"({self.target_qualities}), пропускаем"
            )
            return False, None

    def get_available_qualities_from_messages(self, messages: List) -> List[int]:
        """
        Получение списка всех доступных качеств из списка сообщений.

        Args:
            messages: Список сообщений с видео

        Returns:
            Список уникальных качеств
        """
        qualities = set()
        for message in messages:
            if hasattr(message, 'media') and message.media:
                if hasattr(message.media, 'document') and message.media.document:
                    quality = self.get_video_quality(message.media.document)
                    if quality:
                        qualities.add(quality)

        return sorted(list(qualities))

