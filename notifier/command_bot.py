"""
Telegram-команды для управления ботом (long polling без PTB).

/start   — приветствие (любой пользователь)
/help    — справка (любой пользователь)
/status  — лиды за сегодня (любой)
/sources — статистика источников (любой)
/test    — немедленный тестовый прогон (любой)
/pause   — поставить на паузу (только владелец)
/resume  — возобновить парсинг (только владелец)
"""
import asyncio
import logging
from datetime import datetime

import httpx

import database
import state
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

logger = logging.getLogger(__name__)

# Функция тестового прогона — устанавливается из main.py
_trigger_test_func = None


def _api(method: str) -> str:
    return f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"


async def _reply(chat_id: str | int, text: str) -> None:
    """Отправить сообщение любому пользователю по chat_id."""
    if not TELEGRAM_BOT_TOKEN:
        return
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                _api("sendMessage"),
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": True,
                },
                timeout=10,
            )
            data = resp.json()
            if not data.get("ok"):
                logger.warning(f"sendMessage error: {data.get('description')}")
    except Exception as e:
        logger.error(f"_reply error: {e}")


async def _notify_owner(text: str) -> None:
    """Отправить сообщение владельцу (TELEGRAM_CHAT_ID)."""
    if TELEGRAM_CHAT_ID:
        await _reply(TELEGRAM_CHAT_ID, text)


# ── Обработчики команд ────────────────────────────────────────────────────────

async def _cmd_start(chat_id):
    await _reply(chat_id,
        "🤖 *Zetta Lead Bot*\n\n"
        "Автономный агент поиска лидов для Zetta Group.\n"
        "Находит новые рестораны и кафе в Узбекистане 24/7.\n\n"
        "*Команды:*\n"
        "/status — статистика за сегодня\n"
        "/sources — какие источники работают\n"
        "/test — запустить прогон прямо сейчас\n"
        "/pause — поставить на паузу\n"
        "/resume — возобновить поиск\n"
        "/help — эта справка"
    )


async def _cmd_help(chat_id):
    await _reply(chat_id,
        "📋 *Справка по командам*\n\n"
        "/status — лиды за последние 24 часа\n"
        "/sources — статистика по каждому источнику\n"
        "/test — немедленный прогон всех парсеров\n"
        "/pause — поставить парсинг на паузу\n"
        "/resume — возобновить парсинг\n\n"
        "_Бот работает 24/7 и ищет новые рестораны в Instagram, OLX, Telegram и 2GIS._"
    )


async def _cmd_status(chat_id):
    stats = database.get_last_24h_stats()
    status_icon = "⏸" if state.is_paused() else "▶️"
    status_text = "На паузе" if state.is_paused() else "Работает"
    await _reply(chat_id,
        f"📊 *Статус за последние 24ч*\n\n"
        f"🔍 Найдено: *{stats['total']}*\n"
        f"🔥 Горячих: *{stats['hot']}*\n"
        f"📋 Тёплых: *{stats['warm']}*\n"
        f"👁 На наблюдении: *{stats['watch']}*\n"
        f"⏭ Пропущено: *{stats['skipped']}*\n\n"
        f"{status_icon} Парсинг: *{status_text}*\n"
        f"🕐 {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    )


async def _cmd_sources(chat_id):
    stats = database.get_last_24h_stats()
    emoji_map = {"instagram": "📸", "olx": "🏠", "tg_channels": "📢", "2gis": "🗺"}
    text = "📡 *Источники за последние 24ч*\n\n"
    for source, s in stats["source_stats"].items():
        total = s.get("total", 0)
        hot = s.get("hot", 0)
        hot_pct = (hot / total * 100) if total > 0 else 0
        emoji = emoji_map.get(source, "📍")
        bar = "🟢" if total > 0 else "🔴"
        text += f"{bar} {emoji} *{source}*: {total} найдено, {hot} горячих ({hot_pct:.0f}%)\n"
    if state.is_paused():
        text += "\n⚠️ _Парсинг на паузе_"
    await _reply(chat_id, text)


async def _cmd_test(chat_id):
    global _trigger_test_func
    await _reply(chat_id,
        "🔄 *Запускаю тестовый прогон...*\n\n"
        "Прогоняю все парсеры прямо сейчас. "
        "Найденные лиды придут отдельными сообщениями."
    )
    if _trigger_test_func:
        asyncio.create_task(_trigger_test_func())
    else:
        await _reply(chat_id, "⚠️ Тестовый прогон недоступен — бот только стартовал.")


async def _cmd_pause(chat_id):
    if state.is_paused():
        await _reply(chat_id, "ℹ️ Парсинг уже на паузе. Отправь /resume чтобы возобновить.")
        return
    state.pause()
    await _reply(chat_id,
        "⏸ *Парсинг поставлен на паузу.*\n\n"
        "Бот не ищет новые лиды.\n"
        "Отправь /resume чтобы возобновить."
    )
    logger.info("Парсинг поставлен на паузу через Telegram-команду")


async def _cmd_resume(chat_id):
    if not state.is_paused():
        await _reply(chat_id, "ℹ️ Парсинг уже работает. Отправь /pause чтобы поставить на паузу.")
        return
    state.resume()
    await _reply(chat_id, "▶️ *Парсинг возобновлён!*\n\nБот снова ищет новые лиды.")
    logger.info("Парсинг возобновлён через Telegram-команду")


# ── Роутер команд ─────────────────────────────────────────────────────────────

COMMANDS = {
    "/start":   _cmd_start,
    "/help":    _cmd_help,
    "/status":  _cmd_status,
    "/sources": _cmd_sources,
    "/test":    _cmd_test,
    "/pause":   _cmd_pause,
    "/resume":  _cmd_resume,
}


async def _handle_update(update: dict):
    """Обрабатывает одно входящее обновление от Telegram."""
    msg = update.get("message", {})
    if not msg:
        return

    chat_id = msg.get("chat", {}).get("id")
    if not chat_id:
        return

    raw_text = msg.get("text", "").strip()
    if not raw_text:
        return  # стикер, фото или медиа без текста — игнорируем

    # Берём первое слово (команду), убираем @username суффикс
    cmd = raw_text.split()[0].lower().split("@")[0]

    logger.info(f"Command bot: получена команда '{cmd}' от chat_id={chat_id}")

    handler = COMMANDS.get(cmd)
    if handler:
        await handler(chat_id)
    else:
        # Неизвестная команда — отвечаем только если начинается с /
        if cmd.startswith("/"):
            await _reply(chat_id, "❓ Неизвестная команда. Напиши /help чтобы увидеть список команд.")


# ── Установка меню ─────────────────────────────────────────────────────────────

async def _set_my_commands() -> None:
    """Регистрирует меню команд в Telegram (кнопка /)."""
    commands = [
        {"command": "start",   "description": "Запустить бота"},
        {"command": "status",  "description": "Статистика за сегодня"},
        {"command": "sources", "description": "Какие источники работают"},
        {"command": "test",    "description": "Запустить тестовый прогон прямо сейчас"},
        {"command": "pause",   "description": "Поставить на паузу"},
        {"command": "resume",  "description": "Возобновить поиск"},
        {"command": "help",    "description": "Помощь"},
    ]
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                _api("setMyCommands"),
                json={"commands": commands},
                timeout=10,
            )
            data = resp.json()
            if data.get("ok"):
                logger.info("✅ Меню команд Telegram установлено")
            else:
                logger.warning(f"setMyCommands: {data.get('description')}")
    except Exception as e:
        logger.warning(f"setMyCommands ошибка: {e}")


# ── Главный цикл polling ───────────────────────────────────────────────────────

async def run_forever(trigger_test_func=None):
    """
    Бесконечный цикл получения команд через Telegram long polling.
    Запускается как одна из корутин в asyncio.gather() — не блокирует парсеры.
    """
    global _trigger_test_func
    _trigger_test_func = trigger_test_func

    if not TELEGRAM_BOT_TOKEN:
        logger.warning("Command bot: TELEGRAM_BOT_TOKEN не задан — команды недоступны")
        return

    logger.info("Command bot запущен (long polling, asyncio)")

    # Регистрируем меню команд
    await _set_my_commands()

    # Сбрасываем накопившиеся апдейты (чтобы не обрабатывать старые)
    try:
        async with httpx.AsyncClient() as client:
            await client.get(
                _api("getUpdates"),
                params={"offset": -1, "timeout": 1},
                timeout=5,
            )
    except Exception:
        pass

    logger.info("Command bot: начинаю принимать команды")
    offset = 0

    while True:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    _api("getUpdates"),
                    params={
                        "offset": offset,
                        "timeout": 30,
                        "allowed_updates": ["message"],
                    },
                    timeout=35,
                )
                data = resp.json()

                if not data.get("ok"):
                    logger.warning(f"getUpdates error: {data.get('description')}")
                    await asyncio.sleep(5)
                    continue

                for upd in data.get("result", []):
                    offset = upd["update_id"] + 1
                    try:
                        await _handle_update(upd)
                    except Exception as e:
                        logger.error(f"Command bot handle error: {e}", exc_info=True)

        except httpx.TimeoutException:
            pass  # Норма при long polling — просто нет новых сообщений
        except httpx.ConnectError as e:
            logger.warning(f"Command bot: нет соединения, жду 10с: {e}")
            await asyncio.sleep(10)
        except Exception as e:
            logger.error(f"Command bot polling error: {e}", exc_info=True)
            await asyncio.sleep(5)
