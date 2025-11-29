"""
Главный скрипт для запуска загрузчика видео из Telegram каналов.
"""
import asyncio
import logging
import sys
from pathlib import Path
import yaml

from .telegram_client import TelegramClientWrapper
from .download_manager import DownloadManager
from .file_handler import FileHandler
from .video_quality import VideoQualityHandler
from .notifier import TelegramNotifier

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)


def load_config(config_path: str = "config/config.yaml") -> dict:
    """
    Загрузка конфигурации из YAML файла.

    Args:
        config_path: Путь к файлу конфигурации

    Returns:
        Словарь с конфигурацией
    """
    # Делаем путь абсолютным относительно корня проекта
    if not Path(config_path).is_absolute():
        # Ищем корень проекта (где находится config/)
        current_file = Path(__file__).resolve()
        project_root = current_file.parent.parent
        config_file = project_root / config_path
    else:
        config_file = Path(config_path)
    
    if not config_file.exists():
        logger.error(f"Файл конфигурации не найден: {config_path}")
        sys.exit(1)

    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        logger.info("Конфигурация загружена успешно")
        return config
    except Exception as e:
        logger.error(f"Ошибка при загрузке конфигурации: {e}")
        sys.exit(1)


def setup_logging(config: dict):
    """
    Настройка логирования из конфигурации.

    Args:
        config: Словарь конфигурации
    """
    log_config = config.get('logging', {})
    log_level = getattr(logging, log_config.get('level', 'INFO').upper())
    log_file = log_config.get('log_file')

    handlers = [logging.StreamHandler(sys.stdout)]
    
    if log_file:
        # Делаем путь абсолютным относительно корня проекта
        if not Path(log_file).is_absolute():
            current_file = Path(__file__).resolve()
            project_root = current_file.parent.parent
            log_path = project_root / log_file
        else:
            log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(str(log_path), encoding='utf-8'))

    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=handlers,
        force=True
    )


async def main():
    """Главная функция."""
    # Загружаем конфигурацию
    config = load_config()
    
    # Настраиваем логирование
    setup_logging(config)

    # Инициализируем компоненты
    telegram_config = config['telegram']
    download_config = config['download']
    notifications_config = config.get('notifications', {})

    # Telegram клиент
    client = TelegramClientWrapper(
        api_id=telegram_config['api_id'],
        api_hash=telegram_config['api_hash']
    )

    # Обработчик файлов
    file_handler = FileHandler(
        download_path=download_config['download_path'],
        data_path="./data"
    )

    # Обработчик качества видео
    quality_handler = VideoQualityHandler(
        target_qualities=download_config.get('video_qualities', [360, 480, 720]),
        download_nearest=download_config.get('download_nearest_quality', True)
    )

    # Менеджер загрузок
    download_manager = DownloadManager(
        client=client.client,
        file_handler=file_handler,
        quality_handler=quality_handler,
        max_concurrent=download_config.get('max_concurrent', 5),
        retry_attempts=download_config.get('retry_attempts', 3),
        retry_delay=download_config.get('retry_delay', 5)
    )

    # Уведомления (если включены)
    notifier = None
    if notifications_config.get('enabled', False):
        notifier = TelegramNotifier(
            bot_token=notifications_config['bot_token'],
            chat_id=notifications_config['chat_id']
        )

    try:
        # Подключаемся к Telegram
        await client.connect()

        # Получаем список каналов
        channels = telegram_config.get('channels', [])
        if not channels:
            logger.error("Не указаны каналы для скачивания")
            return

        # Уведомление о начале (если включено)
        if notifier and notifications_config.get('notify_on_start', False):
            try:
                await notifier.notify_start(channels)
            except Exception as e:
                logger.warning(f"Не удалось отправить уведомление о начале: {e}")

        # Обрабатываем каждый канал
        total_stats = {
            'downloaded': 0,
            'skipped': 0,
            'failed': 0,
            'total_size': 0
        }

        for channel_identifier in channels:
            logger.info(f"Обработка канала: {channel_identifier}")
            
            try:
                # Получаем имя канала
                channel_name = await client.get_channel_name(channel_identifier)
                logger.info(f"Имя канала: {channel_name}")

                # Получаем все видео из канала
                video_messages = await client.get_video_messages(channel_identifier)
                
                if not video_messages:
                    logger.info(f"Видео не найдены в канале {channel_name}")
                    continue

                logger.info(f"Найдено {len(video_messages)} видео в канале {channel_name}")

                # Сбрасываем статистику для нового канала
                download_manager.reset_statistics()

                # Загружаем видео
                stats = await download_manager.download_batch(video_messages, channel_name)
                
                # Обновляем общую статистику
                total_stats['downloaded'] += stats['downloaded']
                total_stats['skipped'] += stats['skipped']
                total_stats['failed'] += stats['failed']
                total_stats['total_size'] += stats['total_size']

                logger.info(
                    f"Канал {channel_name} обработан: "
                    f"скачано {stats['downloaded']}, "
                    f"пропущено {stats['skipped']}, "
                    f"ошибок {stats['failed']}"
                )

            except Exception as e:
                logger.error(f"Ошибка при обработке канала {channel_identifier}: {e}", exc_info=True)
                # Продолжаем обработку других каналов даже при ошибке
                if notifier and notifications_config.get('notify_on_errors', False):
                    try:
                        await notifier.notify_error(f"Ошибка в канале {channel_identifier}: {str(e)}")
                    except Exception as notify_error:
                        logger.warning(f"Не удалось отправить уведомление об ошибке: {notify_error}")
                continue

        # Форматируем общую статистику
        total_stats['total_size_formatted'] = file_handler.format_file_size(total_stats['total_size'])

        # Выводим итоговую статистику
        logger.info("=" * 50)
        logger.info("ИТОГОВАЯ СТАТИСТИКА:")
        logger.info(f"Скачано: {total_stats['downloaded']}")
        logger.info(f"Пропущено: {total_stats['skipped']}")
        logger.info(f"Ошибок: {total_stats['failed']}")
        logger.info(f"Общий размер: {total_stats['total_size_formatted']}")
        logger.info("=" * 50)

        # Уведомление о завершении (если включено)
        if notifier and notifications_config.get('notify_on_completion', False):
            try:
                await notifier.notify_completion(total_stats)
            except Exception as e:
                logger.warning(f"Не удалось отправить уведомление о завершении: {e}")

    except KeyboardInterrupt:
        logger.info("Прервано пользователем")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}", exc_info=True)
        if notifier and notifications_config.get('notify_on_errors', False):
            try:
                await notifier.notify_error(f"Критическая ошибка: {str(e)}")
            except Exception as notify_error:
                logger.warning(f"Не удалось отправить уведомление об ошибке: {notify_error}")
    finally:
        # Отключаемся от Telegram
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())

