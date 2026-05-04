from __future__ import annotations

from urllib.request import Request, urlopen
import json


class TelegramError(RuntimeError):
    pass



def send_telegram_message(bot_token: str, chat_id: str, text: str) -> dict:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = json.dumps({"chat_id": chat_id, "text": text}).encode("utf-8")
    request = Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(request, timeout=15) as response:
        result = json.loads(response.read().decode("utf-8"))
    if not result.get("ok"):
        raise TelegramError(result.get("description", "Telegram API request failed"))
    return result
