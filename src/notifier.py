"""
Модуль для отправки уведомлений через Telegram бота.
"""
import logging
import aiohttp
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Отправка уведомлений через Telegram бота."""

    def __init__(self, bot_token: str, chat_id):
        """
        Инициализация уведомлений.

        Args:
            bot_token: Токен бота
            chat_id: ID чата для отправки (может быть int или str)
        """
        self.bot_token = bot_token
        # Chat ID может быть как числом, так и строкой
        self.chat_id = str(chat_id) if isinstance(chat_id, int) else chat_id
        self.api_url = f"https://api.telegram.org/bot{bot_token}"

    async def send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        """
        Отправка текстового сообщения.

        Args:
            text: Текст сообщения
            parse_mode: Режим парсинга (HTML или Markdown)

        Returns:
            True если отправлено успешно
        """
        url = f"{self.api_url}/sendMessage"
        data = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data) as response:
                    if response.status == 200:
                        logger.debug("Уведомление отправлено успешно")
                        return True
                    else:
                        error_text = await response.text()
                        # Парсим JSON ошибки для более понятного сообщения
                        try:
                            import json
                            error_json = json.loads(error_text)
                            error_desc = error_json.get('description', error_text)
                            if 'chat not found' in error_desc.lower():
                                logger.warning(
                                    f"⚠️ Не удалось отправить уведомление: чат не найден. "
                                    f"Убедитесь, что вы начали диалог с ботом (напишите ему /start) "
                                    f"или проверьте правильность Chat ID в конфиге. "
                                    f"Работа продолжается без уведомлений."
                                )
                            else:
                                logger.warning(f"⚠️ Ошибка при отправке уведомления: {error_desc}. Работа продолжается.")
                        except:
                            logger.warning(f"⚠️ Ошибка при отправке уведомления: {error_text}. Работа продолжается.")
                        return False
        except Exception as e:
            logger.warning(f"⚠️ Исключение при отправке уведомления: {e}. Работа продолжается.")
            return False

    async def notify_start(self, channels: list) -> bool:
        """
        Уведомление о начале загрузки.

        Args:
            channels: Список каналов

        Returns:
            True если отправлено успешно
        """
        channels_text = "\n".join([f"• {ch}" for ch in channels])
        text = f"🎬 <b>Начало загрузки видео</b>\n\nКаналы:\n{channels_text}"
        return await self.send_message(text)

    async def notify_completion(self, statistics: Dict) -> bool:
        """
        Уведомление о завершении загрузки.

        Args:
            statistics: Статистика загрузки

        Returns:
            True если отправлено успешно
        """
        downloaded = statistics.get('downloaded', 0)
        skipped = statistics.get('skipped', 0)
        failed = statistics.get('failed', 0)
        total_size = statistics.get('total_size_formatted', '0 B')

        text = (
            f"✅ <b>Загрузка завершена!</b>\n\n"
            f"📥 Скачано: <b>{downloaded}</b>\n"
            f"⏭ Пропущено: <b>{skipped}</b>\n"
            f"❌ Ошибок: <b>{failed}</b>\n"
            f"💾 Общий размер: <b>{total_size}</b>"
        )
        return await self.send_message(text)

    async def notify_error(self, error_message: str) -> bool:
        """
        Уведомление об ошибке.

        Args:
            error_message: Текст ошибки

        Returns:
            True если отправлено успешно
        """
        text = f"❌ <b>Критическая ошибка</b>\n\n{error_message}"
        return await self.send_message(text)

    async def notify_channel_progress(
        self,
        channel_name: str,
        downloaded: int,
        total: int,
        size: str
    ) -> bool:
        """
        Уведомление о прогрессе загрузки канала.

        Args:
            channel_name: Имя канала
            downloaded: Количество скачанных
            total: Всего файлов
            size: Размер в читаемом формате

        Returns:
            True если отправлено успешно
        """
        percentage = (downloaded / total * 100) if total > 0 else 0
        text = (
            f"📊 <b>Прогресс: {channel_name}</b>\n\n"
            f"Скачано: {downloaded}/{total} ({percentage:.1f}%)\n"
            f"Размер: {size}"
        )
        return await self.send_message(text)

