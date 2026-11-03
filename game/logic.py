"""Игровая логика без привязки к движку.

Здесь только чистые функции и данные: урон грузу, расчёт оплаты, генерация заказов.
Ничего из Ursina сюда не импортируется, поэтому этот файл легко переписать на Rust
(1 функция = 1 функция) и легко тестировать без окна.
"""
from __future__ import annotations

from dataclasses import dataclass

MAX_INTEGRITY = 100.0

# Скорости игрока (м/с)
WALK_SPEED = 5.0
SPRINT_SPEED = 8.0
CREEP_SPEED = 2.0

# Пороги скорости, выше которых груз страдает
SHAKE_SPEED = 6.0     # бег трясёт груз
NARROW_SPEED = 2.5    # в узком проходе надо идти медленно

# fragility: множитель урона, pay: базовая оплата
CARGO = {
    "parcel": {"name": "Посылка", "fragility": 0.6, "pay": 40},
    "cake": {"name": "Торт", "fragility": 1.1, "pay": 65},
    "glass": {"name": "Стекло (хрупкое!)", "fragility": 1.6, "pay": 90},
}

# Наборы препятствий у дома
OBSTACLE_VARIANTS = [
    ["dog"],
    ["narrow"],
    ["sprinkler"],
    ["dog", "sprinkler"],
]


# ---------------------------------------------------------------- урон грузу
def shake_damage(speed: float, dt: float, fragility: float) -> float:
    """Урон от тряски при беге."""
    if speed <= SHAKE_SPEED:
        return 0.0
    return (speed - SHAKE_SPEED) * 4.0 * fragility * dt


def landing_damage(fall_speed: float, fragility: float) -> float:
    """Урон от приземления после прыжка/падения (fall_speed > 0, м/с)."""
    return max(0.0, fall_speed - 4.0) * 3.0 * fragility


def narrow_damage(speed: float, dt: float, fragility: float) -> float:
    """Урон в узком проходе, если идти слишком быстро."""
    if speed <= NARROW_SPEED:
        return 0.0
    return (speed - NARROW_SPEED) * 6.0 * fragility * dt


def water_damage(dt: float, fragility: float) -> float:
    """Урон в секунду под струёй поливалки."""
    return 6.0 * (0.5 + fragility) * dt


def dog_bite_damage(fragility: float) -> float:
    """Разовый урон от укуса/толчка собаки."""
    return 10.0 + 8.0 * fragility


# -------------------------------------------------------------------- оплата
def time_multiplier(elapsed: float, limit: float) -> float:
    """1.0 пока укладываешься в срок, потом падает до 0.4."""
    if elapsed <= limit:
        return 1.0
    return max(0.4, 1.0 - (elapsed - limit) / limit * 0.6)


def payment(base_pay: float, integrity: float, elapsed: float, limit: float) -> int:
    """Итоговая оплата за доставку."""
    if integrity <= 0:
        return 0
    pay = base_pay * (integrity / MAX_INTEGRITY) * time_multiplier(elapsed, limit)
    if integrity >= 98.0:  # бонус за аккуратность
        pay *= 1.25
    return int(round(pay))


# -------------------------------------------------------------------- заказы
@dataclass
class Order:
    house_index: int
    number: int
    cargo: str
    base_pay: int
    time_limit: float
    elapsed: float = 0.0
    integrity: float = MAX_INTEGRITY

    @property
    def fragility(self) -> float:
        return CARGO[self.cargo]["fragility"]

    @property
    def cargo_name(self) -> str:
        return CARGO[self.cargo]["name"]


def new_order(rng, houses: list[dict], last_index: int | None = None) -> Order:
    """houses: [{'number': int, 'distance': float, 'obstacles': list[str]}, ...]"""
    choices = [i for i in range(len(houses)) if i != last_index] or list(range(len(houses)))
    idx = rng.choice(choices)
    house = houses[idx]
    cargo = rng.choice(list(CARGO))
    dist = house["distance"]
    base_pay = CARGO[cargo]["pay"] + int(dist * 0.6)
    time_limit = int(40 + dist / 3.0 + 10 * len(house["obstacles"]))
    return Order(idx, house["number"], cargo, base_pay, time_limit)
