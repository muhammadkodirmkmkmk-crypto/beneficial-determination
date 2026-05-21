"""
  Отправка уведомлений ТОЛЬКО на TELEGRAM_CHAT_ID из переменных окружения.
  Горячие лиды — сразу. Тёплые — в утренний дайджест. Watch — с пометкой.
  """
  import logging
  from datetime import datetime

  import httpx

  from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, SCORE_HOT, WATCH_DAYS

  logger = logging.getLogger(__name__)

  TG_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"


  async def send_message(text: str, parse_mode: str = "Markdown") -> int | None:
      """
      Отправляет сообщение ТОЛЬКО на TELEGRAM_CHAT_ID из переменных окружения.
      Возвращает message_id.
      """
      if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
          logger.warning("Telegram не настроен (нет TELEGRAM_BOT_TOKEN или TELEGRAM_CHAT_ID) — пропускаю")
          return None

      try:
          async with httpx.AsyncClient() as client:
              resp = await client.post(
                  f"{TG_API}/sendMessage",
                  json={
                      "chat_id": TELEGRAM_CHAT_ID,
                      "text": text,
                      "parse_mode": parse_mode,
                      "disable_web_page_preview": False,
                  },
                  timeout=15,
              )
              data = resp.json()
              if data.get("ok"):
                  msg_id = data["result"]["message_id"]
                  logger.debug(f"Telegram: сообщение отправлено (id={msg_id})")
                  return msg_id
              else:
                  logger.error(f"Telegram API ошибка: {data.get('description')}")
                  if parse_mode:
                      return await send_message(text, parse_mode="")
      except Exception as e:
          logger.error(f"Ошибка отправки в Telegram: {e}")
      return None


  async def notify_hot_lead(lead_data: dict, decision: dict) -> int | None:
      """Горячий лид — отправляем немедленно с полным описанием."""
      score = decision.get("lead_quality", {}).get("score", 0)
      contact = decision.get("best_contact", {})
      source_emoji = {
          "instagram": "📸",
          "olx": "🏠",
          "tg_channels": "📢",
          "2gis": "🗺",
      }.get(lead_data.get("source", ""), "📍")

      name = lead_data.get("name", "Без названия")
      address = lead_data.get("address") or lead_data.get("channel", "") or "—"
      phone = contact.get("phone") or lead_data.get("phone") or "—"
      instagram = contact.get("instagram") or lead_data.get("instagram") or "—"
      url = lead_data.get("url") or "—"
      reasoning = decision.get("reasoning", "—")
      outreach = decision.get("outreach_message", "—")
      source = lead_data.get("source", "unknown")
      found_at = datetime.now().strftime("%H:%M")

      text = (
          f"🔥 *ГОРЯЧИЙ ЛИД*\n\n"
          f"🏪 *{name}*\n"
          f"📍 {address}\n"
          f"📞 {phone}\n"
          f"{source_emoji} {instagram}\n"
      )

      if url and url != "—":
          text += f"🔗 {url}\n"

      text += (
          f"\n💡 *Почему горячий:*\n{reasoning}\n\n"
          f"📊 Скор: *{score}/100*\n"
          f"🗂 Источник: {source}\n"
          f"🕐 Найден: {found_at}\n\n"
          f"━━━━━━━━━━━━━━━━━\n"
          f"💬 *Сообщение для WhatsApp:*\n{outreach}\n"
          f"━━━━━━━━━━━━━━━━━"
      )

      return await send_message(text)


  async def notify_watch_lead(lead_data: dict, decision: dict) -> int | None:
      """Лид на наблюдении — отправляем с пометкой."""
      name = lead_data.get("name", "Без названия")
      address = lead_data.get("address") or "—"
      reasoning = decision.get("reasoning", "—")

      text = (
          f"👁 *ДОБАВИЛ НА НАБЛЮДЕНИЕ*\n\n"
          f"🏪 {name}\n"
          f"📍 {address}\n\n"
          f"Причина: {reasoning}\n"
          f"Проверю снова: через {WATCH_DAYS} дня"
      )

      return await send_message(text)


  async def send_startup_message() -> int | None:
      """Сообщение при старте бота."""
      text = (
          f"🤖 *Zetta Lead Bot запущен. Работаю 24/7.*\n\n"
          f"Активные парсеры:\n"
          f"• 📸 Instagram (хэштеги ресторанов)\n"
          f"• 🏠 OLX.uz (коммерческая недвижимость)\n"
          f"• 📢 Telegram-каналы\n\n"
          f"2GIS будет подключён позже.\n"
          f"Время запуска: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
      )
      return await send_message(text)


  async def send_daily_digest(leads: list) -> int | None:
      """Утренний дайджест с тёплыми лидами."""
      if not leads:
          return None

      today = datetime.now().strftime("%d %B %Y")
      text = f"📋 *ДАЙДЖЕСТ — {today}*\n\n"
      text += f"Тёплых лидов: *{len(leads)}*\n\n"

      for i, lead in enumerate(leads[:15], 1):
          phone = lead.phone or "—"
          address = lead.address or "—"
          text += f"{i}. *{lead.name}* | {address} | {phone} | {lead.score}/100\n"

      if len(leads) > 15:
          text += f"\n_...и ещё {len(leads) - 15} лидов в базе_"

      return await send_message(text)


  async def send_weekly_report(stats: dict) -> int | None:
      """Еженедельный отчёт."""
      text = (
          f"📊 *ОТЧЁТ ЗА НЕДЕЛЮ*\n\n"
          f"Всего найдено: *{stats.get('total', 0)}*\n"
          f"Горячих лидов: *{stats.get('hot', 0)}*\n"
          f"Тёплых лидов: *{stats.get('warm', 0)}*\n"
          f"Пропущено (дубли/мусор): *{stats.get('skipped', 0)}*\n\n"
      )
      source_stats = stats.get("source_stats", {})
      if source_stats:
          text += "*По источникам:*\n"
          for source, s in source_stats.items():
              hot_pct = (s["hot"] / s["total"] * 100) if s.get("total", 0) > 0 else 0
              text += f"  • {source}: {s.get('total', 0)} найдено, {hot_pct:.0f}% горячих\n"
      return await send_message(text)
  