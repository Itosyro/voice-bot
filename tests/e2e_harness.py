"""Фейковый транспорт Telegram + драйвер реального Dispatcher'а.

Юнит-тесты мокали сессию БД и вызывали хендлеры напрямую — то есть ни разу не
проверяли то, что реально крутится на сервере: настоящий Dispatcher с
middleware, настоящую SQLite-базу и настоящую цепочку
`кнопка → save_user_settings → следующий апдейт`.

`FakeSession` подменяет только HTTP-слой aiogram: возвращает корректные
объекты по типу метода и ЗАПИСЫВАЕТ каждый вызов, чтобы тест мог утверждать,
что именно увидел бы пользователь (текст, клавиатура, parse_mode, тосты).
Поведение Telegram воспроизводится и в неприятной части: повторный
`editMessageText` с тем же текстом и той же клавиатурой падает с
`Bad Request: message is not modified` — ровно как в проде.
"""

from __future__ import annotations

import html as html_mod
import re
import time
from dataclasses import dataclass, field
from typing import Any

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.base import BaseSession
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import TelegramMethod
from aiogram.types import File, InlineKeyboardMarkup, Message, MessageEntity, Update

BOT_TOKEN = "42:TEST"
BOT_ID = 42

_TAG_RE = re.compile(r"</?([a-zA-Z]+)(\s[^>]*?)?/?>")

_ENTITY_BY_TAG = {
    "b": "bold",
    "strong": "bold",
    "i": "italic",
    "em": "italic",
    "u": "underline",
    "s": "strikethrough",
    "code": "code",
    "pre": "pre",
    "blockquote": "blockquote",
}


def u16(text: str) -> int:
    """Длина в UTF-16 code units — именно так Telegram считает offset/length."""
    return len(text.encode("utf-16-le")) // 2


def render_html(source: str) -> tuple[str, list[MessageEntity]]:
    """Мини-рендерер HTML → (plain text, entities), как это делает Telegram.

    Нужен, чтобы `_holds_result()` (детект «в сообщении лежит результат») видел
    те же entities, что и в проде: blockquote/code вокруг ответа модели.
    """
    text = ""
    entities: list[MessageEntity] = []
    stack: list[tuple[str, str, int]] = []
    pos = 0
    for match in _TAG_RE.finditer(source):
        text += html_mod.unescape(source[pos : match.start()])
        pos = match.end()
        tag = match.group(1).lower()
        if tag not in _ENTITY_BY_TAG:
            continue
        if match.group(0).startswith("</"):
            for i in range(len(stack) - 1, -1, -1):
                if stack[i][0] == tag:
                    _tag, etype, start = stack.pop(i)
                    entities.append(
                        MessageEntity(type=etype, offset=start, length=u16(text) - start)
                    )
                    break
            continue
        etype = _ENTITY_BY_TAG[tag]
        if tag == "blockquote" and "expandable" in (match.group(2) or ""):
            etype = "expandable_blockquote"
        stack.append((tag, etype, u16(text)))
    text += html_mod.unescape(source[pos:])
    entities.sort(key=lambda e: (e.offset, e.length))
    return text, entities


@dataclass
class Call:
    """Один запрос к Telegram API."""

    method: str
    payload: TelegramMethod
    text: str = ""  # отрендеренный (plain) текст, если метод его нёс
    chat_id: int | None = None
    message_id: int | None = None
    markup: InlineKeyboardMarkup | None = None
    parse_mode: Any = None

    def buttons(self) -> list[str]:
        if not self.markup:
            return []
        return [b.callback_data or "" for row in self.markup.inline_keyboard for b in row]


@dataclass
class _MsgState:
    chat_id: int
    message_id: int
    text: str
    entities: list[MessageEntity] = field(default_factory=list)
    markup: InlineKeyboardMarkup | None = None
    is_document: bool = False


class FakeSession(BaseSession):
    """Транспорт-заглушка: ничего не шлёт в сеть, всё записывает."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[Call] = []
        self.messages: dict[tuple[int, int], _MsgState] = {}
        self.order: list[tuple[int, int]] = []  # порядок последних изменений
        self.file_bytes = b"fake-audio-bytes"
        self._next_id = 1000

    # ── BaseSession ──

    async def close(self) -> None:  # pragma: no cover - ничего не держим
        return None

    async def stream_content(
        self,
        url: str,
        headers: dict[str, Any] | None = None,
        timeout: int = 30,
        chunk_size: int = 65536,
        raise_for_status: bool = True,
    ):
        yield self.file_bytes

    async def make_request(
        self, bot: Bot, method: TelegramMethod, timeout: int | None = None
    ) -> Any:
        name = type(method).__name__
        handler = getattr(self, f"_do_{_snake(name)}", None)
        if handler is None:
            self.calls.append(Call(method=name, payload=method))
            return True
        return handler(bot, method)

    # ── методы Telegram ──

    def _do_send_message(self, bot: Bot, method: Any) -> Message:
        text, entities = self._render(bot, method)
        return self._store_message(
            bot, method.chat_id, self._new_id(), text, entities, method.reply_markup, method
        )

    def _do_edit_message_text(self, bot: Bot, method: Any) -> Message:
        text, entities = self._render(bot, method)
        key = (int(method.chat_id), int(method.message_id))
        current = self.messages.get(key)
        if current is not None and current.is_document:
            self.calls.append(Call(method="EditMessageText", payload=method, text=text))
            raise TelegramBadRequest(
                method=method,
                message="Bad Request: there is no text in the message to edit",
            )
        if current is not None and _same(current, text, entities, method.reply_markup):
            # Telegram отвечает ошибкой на «редактирование» в то же самое —
            # без обработки она долетает до глобального error-handler'а и
            # пользователь видит тост «⚠ Ошибка», будто кнопка сломана.
            self.calls.append(Call(method="EditMessageText", payload=method, text=text))
            raise TelegramBadRequest(method=method, message="Bad Request: message is not modified")
        return self._store_message(
            bot,
            method.chat_id,
            method.message_id,
            text,
            entities,
            method.reply_markup,
            method,
        )

    def _do_send_document(self, bot: Bot, method: Any) -> Message:
        message_id = self._new_id()
        caption = method.caption or ""
        data = {
            "message_id": message_id,
            "date": int(time.time()),
            "chat": {"id": int(method.chat_id), "type": "private"},
            "from": _bot_user(),
            "caption": caption,
            "document": {
                "file_id": "doc-file-id",
                "file_unique_id": "doc-unique",
                "file_name": getattr(method.document, "filename", "result.txt"),
            },
            "reply_markup": _dump(method.reply_markup),
        }
        key = (int(method.chat_id), message_id)
        self.messages[key] = _MsgState(
            chat_id=int(method.chat_id),
            message_id=message_id,
            text="",
            markup=method.reply_markup,
            is_document=True,
        )
        self._touch(key)
        self.calls.append(
            Call(
                method="SendDocument",
                payload=method,
                text=caption,
                chat_id=int(method.chat_id),
                message_id=message_id,
                markup=method.reply_markup,
            )
        )
        return Message.model_validate(data, context={"bot": bot})

    def _do_answer_callback_query(self, bot: Bot, method: Any) -> bool:
        self.calls.append(
            Call(method="AnswerCallbackQuery", payload=method, text=method.text or "")
        )
        return True

    def _do_get_file(self, bot: Bot, method: Any) -> File:
        self.calls.append(Call(method="GetFile", payload=method))
        return File.model_validate(
            {
                "file_id": method.file_id,
                "file_unique_id": f"{method.file_id}-u",
                "file_size": len(self.file_bytes),
                "file_path": f"voice/{method.file_id}.oga",
            },
            context={"bot": bot},
        )

    def _do_get_me(self, bot: Bot, method: Any):
        from aiogram.types import User as TgUser

        self.calls.append(Call(method="GetMe", payload=method))
        return TgUser.model_validate(_bot_user(), context={"bot": bot})

    def _do_delete_webhook(self, bot: Bot, method: Any) -> bool:
        self.calls.append(Call(method="DeleteWebhook", payload=method))
        return True

    # ── внутреннее ──

    def _new_id(self) -> int:
        self._next_id += 1
        return self._next_id

    def _render(self, bot: Bot, method: Any) -> tuple[str, list[MessageEntity]]:
        raw = method.text if hasattr(method, "text") else ""
        parse_mode = getattr(method, "parse_mode", None)
        if isinstance(parse_mode, str) and parse_mode.upper() == "HTML":
            return render_html(raw or "")
        return raw or "", []

    def _store_message(
        self,
        bot: Bot,
        chat_id: Any,
        message_id: Any,
        text: str,
        entities: list[MessageEntity],
        markup: InlineKeyboardMarkup | None,
        method: Any,
    ) -> Message:
        key = (int(chat_id), int(message_id))
        self.messages[key] = _MsgState(
            chat_id=int(chat_id),
            message_id=int(message_id),
            text=text,
            entities=entities,
            markup=markup,
        )
        self._touch(key)
        self.calls.append(
            Call(
                method=type(method).__name__,
                payload=method,
                text=text,
                chat_id=int(chat_id),
                message_id=int(message_id),
                markup=markup,
                parse_mode=getattr(method, "parse_mode", None),
            )
        )
        data = {
            "message_id": int(message_id),
            "date": int(time.time()),
            "chat": {"id": int(chat_id), "type": "private"},
            "from": _bot_user(),
            "text": text,
            "entities": [e.model_dump(exclude_none=True) for e in entities],
            "reply_markup": _dump(markup),
        }
        return Message.model_validate(data, context={"bot": bot})

    def _touch(self, key: tuple[int, int]) -> None:
        if key in self.order:
            self.order.remove(key)
        self.order.append(key)

    # ── запросы к записи ──

    def texts(self) -> list[str]:
        return [c.text for c in self.calls if c.method in ("SendMessage", "EditMessageText")]

    def toasts(self) -> list[str]:
        return [c.text for c in self.calls if c.method == "AnswerCallbackQuery"]

    def sent(self) -> list[Call]:
        return [c for c in self.calls if c.method == "SendMessage"]

    def edits(self) -> list[Call]:
        return [c for c in self.calls if c.method == "EditMessageText"]

    def documents(self) -> list[Call]:
        return [c for c in self.calls if c.method == "SendDocument"]

    def last_text(self) -> str:
        texts = self.texts()
        return texts[-1] if texts else ""

    def find_with_button(self, callback_data: str) -> _MsgState:
        """Последнее сообщение бота, в котором есть кнопка с таким callback_data."""
        for key in reversed(self.order):
            state = self.messages[key]
            if state.markup and any(
                b.callback_data == callback_data
                for row in state.markup.inline_keyboard
                for b in row
            ):
                return state
        raise AssertionError(
            f"кнопки {callback_data!r} нет ни в одном сообщении; "
            f"последнее: {self.last_text()[:120]!r}"
        )

    def clear(self) -> None:
        self.calls.clear()


def _same(
    state: _MsgState,
    text: str,
    entities: list[MessageEntity],
    markup: InlineKeyboardMarkup | None,
) -> bool:
    return (
        state.text == text
        and [e.model_dump(exclude_none=True) for e in state.entities]
        == [e.model_dump(exclude_none=True) for e in entities]
        and _dump(state.markup) == _dump(markup)
    )


def _dump(markup: InlineKeyboardMarkup | None) -> dict | None:
    return markup.model_dump(exclude_none=True) if markup else None


def _bot_user() -> dict:
    return {"id": BOT_ID, "is_bot": True, "first_name": "TestBot", "username": "testbot"}


def _snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


# ── драйвер апдейтов ──


class Harness:
    """Отправляет апдейты в РЕАЛЬНЫЙ Dispatcher, как это делает polling."""

    def __init__(self, dp: Dispatcher, bot: Bot, session: FakeSession) -> None:
        self.dp = dp
        self.bot = bot
        self.session = session
        self._update_id = 0
        self._message_id = 100

    def _next_update(self) -> int:
        self._update_id += 1
        return self._update_id

    def _next_message(self) -> int:
        self._message_id += 1
        return self._message_id

    @staticmethod
    def user(user_id: int) -> dict:
        return {
            "id": user_id,
            "is_bot": False,
            "first_name": f"User{user_id}",
            "username": f"user{user_id}",
            "language_code": "ru",
        }

    async def feed(self, payload: dict) -> Any:
        update = Update.model_validate(
            {"update_id": self._next_update(), **payload}, context={"bot": self.bot}
        )
        return await self.dp.feed_update(self.bot, update)

    def _message(self, user_id: int, chat_id: int | None, **extra: Any) -> dict:
        return {
            "message_id": self._next_message(),
            "date": int(time.time()),
            "chat": {"id": chat_id if chat_id is not None else user_id, "type": "private"},
            "from": self.user(user_id),
            **extra,
        }

    async def send_text(self, text: str, user_id: int = 1, chat_id: int | None = None) -> Any:
        return await self.feed({"message": self._message(user_id, chat_id, text=text)})

    async def send_command(self, command: str, user_id: int = 1, chat_id: int | None = None) -> Any:
        return await self.feed(
            {
                "message": self._message(
                    user_id,
                    chat_id,
                    text=command,
                    entities=[{"type": "bot_command", "offset": 0, "length": len(command)}],
                )
            }
        )

    def voice_payload(self, file_id: str = "voice-1", duration: int = 5) -> dict:
        return {
            "file_id": file_id,
            "file_unique_id": f"{file_id}-u",
            "duration": duration,
            "mime_type": "audio/ogg",
            "file_size": 4096,
        }

    async def send_voice(
        self,
        user_id: int = 1,
        chat_id: int | None = None,
        file_id: str = "voice-1",
        duration: int = 5,
        forwarded: bool = False,
    ) -> Any:
        extra: dict[str, Any] = {"voice": self.voice_payload(file_id, duration)}
        if forwarded:
            extra["forward_origin"] = {
                "type": "user",
                "date": int(time.time()),
                "sender_user": self.user(user_id + 500),
            }
        return await self.feed({"message": self._message(user_id, chat_id, **extra)})

    async def reply_to_voice(
        self, text: str | None = None, user_id: int = 1, chat_id: int | None = None
    ) -> Any:
        replied = self._message(user_id + 500, chat_id or user_id, voice=self.voice_payload())
        extra: dict[str, Any] = {"reply_to_message": replied}
        if text is not None:
            extra["text"] = text
        return await self.feed({"message": self._message(user_id, chat_id, **extra)})

    async def tap(self, callback_data: str, user_id: int = 1) -> Any:
        """Нажатие кнопки: ищем сообщение, в котором эта кнопка реально есть."""
        state = self.session.find_with_button(callback_data)
        return await self.tap_on(state, callback_data, user_id=user_id)

    async def tap_on(self, state: _MsgState, callback_data: str, user_id: int = 1) -> Any:
        message: dict[str, Any] = {
            "message_id": state.message_id,
            "date": int(time.time()),
            "chat": {"id": state.chat_id, "type": "private"},
            "from": _bot_user(),
            "reply_markup": _dump(state.markup),
        }
        if state.is_document:
            message["document"] = {"file_id": "doc-file-id", "file_unique_id": "doc-unique"}
        else:
            message["text"] = state.text
            message["entities"] = [e.model_dump(exclude_none=True) for e in state.entities]
        return await self.feed(
            {
                "callback_query": {
                    "id": f"cb-{self._update_id + 1}",
                    "from": self.user(user_id),
                    "chat_instance": f"ci-{user_id}",
                    "message": message,
                    "data": callback_data,
                }
            }
        )


def make_bot(session: FakeSession) -> Bot:
    return Bot(token=BOT_TOKEN, session=session, default=DefaultBotProperties(parse_mode=None))
