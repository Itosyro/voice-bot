from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

WEEKDAY_LABELS = ["ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС"]
AREA_LABELS = {
    "pdd": "ПДД",
    "cafe": "Кафе",
    "volleyball": "Волейбол",
    "social": "Соцсети",
    "recovery": "Восстановление",
    "other": "Разное",
}
ENERGY_LABELS = {0: "Лежу", 1: "5 минут", 2: "Норм", 3: "Много"}
BODY_LABELS = {0: "Ок", 1: "Ноет", 2: "Ломит", 3: "Стоп"}
STRESS_LABELS = {0: "Тихо", 1: "Есть", 2: "Сильно", 3: "Шторм"}


@dataclass(frozen=True)
class Checkin:
    energy: int
    body: int
    stress: int
    created_at_utc: datetime


@dataclass(frozen=True)
class SmartDecision:
    mode: str
    headline: str
    action: str
    minutes: int
    caution: str | None = None


def parse_hhmm(value: str) -> time:
    hh, mm = (int(x) for x in value.split(":", 1))
    return time(hh, mm)


def weekday_mask(days: set[int]) -> int:
    mask = 0
    for day in days:
        if day < 0 or day > 6:
            raise ValueError("weekday must be 0..6")
        mask |= 1 << day
    return mask


def mask_has_day(mask: int, day: int) -> bool:
    return bool(mask & (1 << day))


def describe_weekdays(mask: int) -> str:
    if mask == 0b1111111:
        return "каждый день"
    weekdays = weekday_mask({0, 1, 2, 3, 4})
    if mask == weekdays:
        return "по будням"
    return " ".join(label for index, label in enumerate(WEEKDAY_LABELS) if mask_has_day(mask, index))


def local_to_utc(day: date, hhmm: str, tz_name: str) -> datetime:
    tz = ZoneInfo(tz_name)
    local = datetime.combine(day, parse_hhmm(hhmm), tzinfo=tz)
    return local.astimezone(ZoneInfo("UTC"))


def is_quiet(now_utc: datetime, tz_name: str, quiet_start: str, quiet_end: str) -> bool:
    tz = ZoneInfo(tz_name)
    local = now_utc.astimezone(tz).time().replace(tzinfo=None)
    start = parse_hhmm(quiet_start)
    end = parse_hhmm(quiet_end)
    if start == end:
        return False
    if start < end:
        return start <= local < end
    return local >= start or local < end


def checkin_is_fresh(checkin: Checkin | None, now_utc: datetime, fresh_minutes: int) -> bool:
    if checkin is None:
        return False
    return now_utc - checkin.created_at_utc <= timedelta(minutes=fresh_minutes)


def _clamp_minutes(value: int, minimum: int = 2, maximum: int = 25) -> int:
    return max(minimum, min(maximum, int(value)))


def smart_decision(
    *,
    title: str,
    microstep: str | None,
    area: str,
    min_minutes: int,
    normal_minutes: int,
    energy_cost: int,
    checkin: Checkin | None,
) -> SmartDecision:
    micro = (microstep or "").strip() or f"Открой «{title}» и сделай первое очевидное действие."
    normal = _clamp_minutes(normal_minutes, 5, 25)
    minimum = _clamp_minutes(min_minutes, 2, 8)

    if checkin is None:
        return SmartDecision(
            mode="micro",
            headline="Без оценки ресурса — ставка маленькая.",
            action=micro,
            minutes=minimum,
        )

    if area == "volleyball" and checkin.body >= 2:
        caution = (
            "Сегодня не используем бот как медицинский допуск к нагрузке. "
            "Если боль выраженная, новая или усиливается — интенсивную игру лучше не форсировать."
        )
        return SmartDecision(
            mode="recovery",
            headline="Тело просит облегчить нагрузку.",
            action="Вместо интенсивной игры: 5 минут спокойного восстановления и повторная оценка состояния позже.",
            minutes=5,
            caution=caution,
        )

    effective_energy = checkin.energy
    if checkin.body == 1:
        effective_energy -= 1
    elif checkin.body >= 2:
        effective_energy -= 2
    if checkin.stress >= 2:
        effective_energy -= 1

    if effective_energy <= 0 or energy_cost >= 2 and effective_energy <= 1:
        return SmartDecision(
            mode="micro",
            headline="Не тащим всю задачу. Только вход.",
            action=micro,
            minutes=minimum,
        )

    if checkin.stress >= 3:
        return SmartDecision(
            mode="micro",
            headline="Шторм — уменьшаем ставку, а не отменяем день.",
            action=micro,
            minutes=minimum,
        )

    if effective_energy >= 3 and checkin.stress <= 1:
        return SmartDecision(
            mode="normal",
            headline="Ресурс есть. Берём нормальный раунд.",
            action=title,
            minutes=normal,
        )

    return SmartDecision(
        mode="short",
        headline="Короткий раунд без разгона.",
        action=title if energy_cost <= 1 else micro,
        minutes=min(normal, 8),
    )


def next_due_date(start: date, mask: int, include_start: bool = True) -> date:
    offset = 0 if include_start else 1
    for delta in range(offset, offset + 8):
        candidate = start + timedelta(days=delta)
        if mask_has_day(mask, candidate.weekday()):
            return candidate
    raise RuntimeError("weekday mask has no active days")
