"""
Telegram клиент для подключения к API и получения сообщений из каналов.
"""
import asyncio
import logging
from pathlib import Path
from typing import List, Optional
from telethon import TelegramClient
from telethon.tl.types import Message, MessageMediaDocument, DocumentAttributeVideo
from telethon.errors import ChannelPrivateError, UsernameNotOccupiedError

logger = logging.getLogger(__name__)


class TelegramClientWrapper:
    """Обертка над Telethon клиентом для удобной работы с каналами."""

    def __init__(self, api_id: int, api_hash: str, session_name: str = "tvdownloader"):
        """
        Инициализация клиента.

        Args:
            api_id: Telegram API ID
            api_hash: Telegram API Hash
            session_name: Имя файла сессии (без расширения)
        """
        self.api_id = api_id
        self.api_hash = api_hash
        
        # Определяем абсолютный путь к папке sessions относительно корня проекта
        current_file = Path(__file__).resolve()
        project_root = current_file.parent.parent
        session_path = project_root / "sessions" / session_name
        session_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.client = TelegramClient(str(session_path), api_id, api_hash)
        self._connected = False

    async def connect(self):
        """Подключение к Telegram."""
        if not self._connected:
            await self.client.start()
            self._connected = True
            logger.info("Успешно подключено к Telegram")

    async def disconnect(self):
        """Отключение от Telegram."""
        if self._connected:
            await self.client.disconnect()
            self._connected = False
            logger.info("Отключено от Telegram")

    async def get_channel_entity(self, channel_identifier: str):
        """
        Получение сущности канала по различным идентификаторам.

        Args:
            channel_identifier: Username (@channel), invite link или ID канала

        Returns:
            Entity канала или None если не найдено
        """
        try:
            # Пробуем разные способы получения канала
            if channel_identifier.startswith("https://t.me/joinchat/"):
                # Invite link
                entity = await self.client.get_entity(channel_identifier)
            elif channel_identifier.startswith("@"):
                # Username
                entity = await self.client.get_entity(channel_identifier)
            else:
                # ID канала (может быть строкой или числом)
                try:
                    channel_id = int(channel_identifier)
                    entity = await self.client.get_entity(channel_id)
                except ValueError:
                    entity = await self.client.get_entity(channel_identifier)

            logger.info(f"Канал найден: {entity.title if hasattr(entity, 'title') else channel_identifier}")
            return entity
        except ChannelPrivateError:
            logger.error(f"Канал {channel_identifier} приватный или недоступен")
            return None
        except UsernameNotOccupiedError:
            logger.error(f"Канал {channel_identifier} не найден")
            return None
        except Exception as e:
            logger.error(f"Ошибка при получении канала {channel_identifier}: {e}")
            return None

    async def get_video_messages(self, channel_identifier: str, limit: Optional[int] = None) -> List[Message]:
        """
        Получение всех сообщений с видео из канала.

        Args:
            channel_identifier: Username, invite link или ID канала
            limit: Максимальное количество сообщений (None = все)

        Returns:
            Список сообщений с видео
        """
        entity = await self.get_channel_entity(channel_identifier)
        if not entity:
            return []

        video_messages = []
        try:
            async for message in self.client.iter_messages(entity, limit=limit):
                if self._is_video_message(message):
                    video_messages.append(message)
                    logger.debug(f"Найдено видео: {message.id} из канала {channel_identifier}")
        except Exception as e:
            logger.error(f"Ошибка при получении сообщений из {channel_identifier}: {e}")

        logger.info(f"Найдено {len(video_messages)} видео в канале {channel_identifier}")
        return video_messages

    def _is_video_message(self, message: Message) -> bool:
        """
        Проверка, является ли сообщение видео.

        Args:
            message: Сообщение для проверки

        Returns:
            True если это видео
        """
        if not message.media:
            return False

        if isinstance(message.media, MessageMediaDocument):
            doc = message.media.document
            if doc:
                # Проверяем атрибуты документа
                for attr in doc.attributes:
                    if isinstance(attr, DocumentAttributeVideo):
                        return True

        return False

    async def get_channel_name(self, channel_identifier: str) -> str:
        """
        Получение имени канала для создания папки.

        Args:
            channel_identifier: Username, invite link или ID канала

        Returns:
            Имя канала (безопасное для файловой системы)
        """
        entity = await self.get_channel_entity(channel_identifier)
        if entity and hasattr(entity, 'title'):
            # Очищаем имя от недопустимых символов
            name = entity.title
            # Заменяем недопустимые символы на подчеркивания
            invalid_chars = '<>:"/\\|?*'
            for char in invalid_chars:
                name = name.replace(char, '_')
            return name
        # Если не удалось получить имя, используем идентификатор
        safe_name = channel_identifier.replace('@', '').replace('https://t.me/joinchat/', 'invite_')
        return safe_name[:50]  # Ограничиваем длину

