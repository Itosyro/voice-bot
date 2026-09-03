from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class ReadinessInputs:
    sleep_hours: float
    sleep_quality: int
    energy: int
    soreness: int
    pain: int
    stress: int
    illness: str = "none"
    red_flag: bool = False
    volleyball_today: bool = False
    lower_today: bool = False
    lower_load_36h: float = 0.0
    load_7d: float = 0.0
    baseline_weekly_load: float | None = None


@dataclass(frozen=True)
class ReadinessResult:
    score: int
    status: str
    label: str
    strength_level: str
    strength_text: str
    volleyball_level: str
    volleyball_text: str
    rpe_cap: int
    volume_factor: float
    reasons: tuple[str, ...]
    urgent: bool

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["reasons"] = list(self.reasons)
        return data


def _validate_scale(name: str, value: int) -> int:
    number = int(value)
    if not 0 <= number <= 3:
        raise ValueError(f"{name} must be 0..3")
    return number


def evaluate_readiness(inputs: ReadinessInputs) -> ReadinessResult:
    sleep_hours = float(inputs.sleep_hours)
    if not 0 <= sleep_hours <= 24:
        raise ValueError("sleep_hours must be 0..24")
    sleep_quality = _validate_scale("sleep_quality", inputs.sleep_quality)
    energy = _validate_scale("energy", inputs.energy)
    soreness = _validate_scale("soreness", inputs.soreness)
    pain = _validate_scale("pain", inputs.pain)
    stress = _validate_scale("stress", inputs.stress)
    illness = str(inputs.illness or "none")
    if illness not in {"none", "mild", "systemic"}:
        raise ValueError("illness must be none, mild or systemic")

    score = 100
    reasons: list[str] = []
    hard_stop = False
    urgent = False

    if inputs.red_flag:
        hard_stop = True
        urgent = True
        reasons.append("Есть опасный симптом: тренировку не начинать и обратиться за медицинской помощью.")
    if illness == "systemic":
        hard_stop = True
        reasons.append("Есть температура, выраженная слабость, ломота или симптомы ниже шеи.")
    elif illness == "mild":
        score -= 12
        reasons.append("Есть лёгкие симптомы простуды — только лёгкая нагрузка, если самочувствие не ухудшается.")

    if pain >= 3:
        hard_stop = True
        reasons.append("Сильная или ограничивающая движение боль.")
    elif pain == 2:
        score -= 24
        reasons.append("Заметная боль: избегай болезненных движений и прыжков.")
    elif pain == 1:
        score -= 8
        reasons.append("Есть лёгкая боль — контролируй её по ходу занятия.")

    if sleep_hours < 5:
        score -= 30
        reasons.append("Сна меньше 5 часов.")
    elif sleep_hours < 6:
        score -= 20
        reasons.append("Сна меньше 6 часов.")
    elif sleep_hours < 7:
        score -= 10
        reasons.append("Сна меньше 7 часов.")

    score -= (3 - sleep_quality) * 6
    if sleep_quality <= 1:
        reasons.append("Сон ощущается плохим.")

    energy_penalty = {0: 32, 1: 20, 2: 7, 3: 0}[energy]
    score -= energy_penalty
    if energy <= 1:
        reasons.append("Энергии мало.")

    soreness_penalty = {0: 0, 1: 5, 2: 15, 3: 27}[soreness]
    score -= soreness_penalty
    if soreness >= 2:
        reasons.append("Мышцы заметно не восстановились.")

    stress_penalty = {0: 0, 1: 3, 2: 9, 3: 16}[stress]
    score -= stress_penalty
    if stress >= 2:
        reasons.append("Высокая психическая нагрузка тоже считается нагрузкой.")

    if inputs.volleyball_today and inputs.lower_today:
        score -= 14
        reasons.append("На один день попали волейбол и тренировка низа — лучше разнести их.")

    lower_load_36h = max(0.0, float(inputs.lower_load_36h or 0.0))
    if inputs.volleyball_today and lower_load_36h >= 450:
        score -= 22
        reasons.append("За последние 36 часов уже была высокая нагрузка на ноги.")
    elif inputs.volleyball_today and lower_load_36h >= 250:
        score -= 12
        reasons.append("Ноги уже получали заметную нагрузку за последние 36 часов.")

    baseline = inputs.baseline_weekly_load
    if baseline is not None and baseline >= 300:
        load_7d = max(0.0, float(inputs.load_7d or 0.0))
        if load_7d > baseline * 1.45 and load_7d - baseline >= 300:
            score -= 12
            reasons.append("Недельная нагрузка резко выше твоего недавнего среднего.")
        elif load_7d > baseline * 1.25 and load_7d - baseline >= 200:
            score -= 6
            reasons.append("Недельная нагрузка выше твоего недавнего среднего.")

    score = max(0, min(100, round(score)))
    if hard_stop or score < 45:
        status = "red"
        label = "Красный день"
        strength_level = "recovery"
        strength_text = "Без тяжёлой силовой. Отдых или очень лёгкое восстановление без боли."
        volleyball_level = "stop"
        volleyball_text = "Полноценный волейбол и прыжковую работу сегодня пропусти."
        rpe_cap = 3
        volume_factor = 0.0
    elif score < 75:
        status = "yellow"
        label = "Жёлтый день"
        strength_level = "reduced"
        strength_text = "Можно облегчённую тренировку: убери 30–50% объёма, без отказа и максимумов."
        volleyball_level = "limited"
        volleyball_text = "Только техника/приём/подача или короткая игра; сократи прыжки и остановись при ухудшении."
        rpe_cap = 6
        volume_factor = 0.6
    else:
        status = "green"
        label = "Зелёный день"
        strength_level = "full"
        strength_text = "Можно плановую силовую, оставляя запас и не работая через боль."
        volleyball_level = "full"
        volleyball_text = "Можно играть по плану; контролируй самочувствие и не игнорируй боль."
        rpe_cap = 8
        volume_factor = 1.0

    if not reasons:
        reasons.append("Сон, энергия, боль и недавняя нагрузка выглядят нормально.")

    return ReadinessResult(
        score=score,
        status=status,
        label=label,
        strength_level=strength_level,
        strength_text=strength_text,
        volleyball_level=volleyball_level,
        volleyball_text=volleyball_text,
        rpe_cap=rpe_cap,
        volume_factor=volume_factor,
        reasons=tuple(reasons[:8]),
        urgent=urgent,
    )
