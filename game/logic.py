"""Игровая логика без привязки к движку.

Здесь только чистые функции и данные: урон грузу, оплата, ряды в фургоне,
оценка «возни» с разгрузкой, длина маршрута. Ничего из Ursina сюда не
импортируется, поэтому файл легко тестировать без окна и переписать на Rust.
"""
from __future__ import annotations

from dataclasses import dataclass

MAX_INTEGRITY = 100.0

# Скорости игрока (м/с)
WALK_SPEED = 5.0
SPRINT_SPEED = 8.0
CREEP_SPEED = 2.0

# Пороги скорости, выше которых груз страдает
SHAKE_SPEED = 6.0     # бег трясёт груз в руках
NARROW_SPEED = 2.5    # в узком проходе надо идти медленно

# Фургон
VAN_MAX_SPEED = 11.0
VAN_REVERSE_SPEED = 4.0
VAN_ACCEL = 7.0
VAN_COAST_DECEL = 8.0    # отпустил газ
VAN_BRAKE_DECEL = 14.0   # нажал тормоз (S)
SAFE_DECEL = 9.0         # торможение жёстче этого бьёт груз в кузове

BAY_LANES = 2
BAY_DEPTH = 4

# fragility: множитель урона, pay: базовая оплата
CARGO = {
    "parcel": {"name": "Посылка", "fragility": 0.6, "pay": 40},
    "cake": {"name": "Торт", "fragility": 1.1, "pay": 65},
    "glass": {"name": "Стекло", "fragility": 1.6, "pay": 90},
}

# Наборы препятствий у домов (по одному на дом, перемешиваются)
OBSTACLE_VARIANTS = [
    ["dog"],
    ["narrow"],
    ["sprinkler"],
    ["dog", "sprinkler"],
    ["narrow", "sprinkler"],
    [],
]


# ---------------------------------------------------------------- урон грузу
def shake_damage(speed: float, dt: float, fragility: float) -> float:
    """Урон от тряски при беге с грузом в руках."""
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
    """Разовый урон от толчка собаки."""
    return 10.0 + 8.0 * fragility


def hard_brake_damage(decel: float, speed: float, dt: float, fragility: float) -> float:
    """Урон грузу в кузове при резком торможении на скорости."""
    if decel <= SAFE_DECEL or speed <= 3.0:
        return 0.0
    return (decel - SAFE_DECEL) * min(speed, VAN_MAX_SPEED) / VAN_MAX_SPEED * 3.0 * fragility * dt


# -------------------------------------------------------------------- оплата
def time_multiplier(elapsed: float, limit: float) -> float:
    """1.0 пока укладываешься в срок, потом падает до 0.4."""
    if limit <= 0 or elapsed <= limit:
        return 1.0
    return max(0.4, 1.0 - (elapsed - limit) / limit * 0.6)


def payment(base_pay: float, integrity: float, elapsed: float, limit: float) -> int:
    """Итоговая оплата за одну посылку."""
    if integrity <= 0:
        return 0
    pay = base_pay * (integrity / MAX_INTEGRITY) * time_multiplier(elapsed, limit)
    if integrity >= 98.0:  # бонус за аккуратность
        pay *= 1.25
    return int(round(pay))


def base_pay(kind: str, distance: float) -> int:
    return CARGO[kind]["pay"] + int(distance * 0.4)


# -------------------------------------------------------------------- груз
@dataclass
class Cargo:
    id: int
    house_index: int
    kind: str
    integrity: float = MAX_INTEGRITY

    @property
    def fragility(self) -> float:
        return CARGO[self.kind]["fragility"]

    @property
    def kind_name(self) -> str:
        return CARGO[self.kind]["name"]


def make_cargo(rng, n_houses: int) -> list[Cargo]:
    """По одной посылке на каждый дом, в случайном порядке лежат на земле."""
    houses = list(range(n_houses))
    rng.shuffle(houses)
    return [Cargo(i, h, rng.choice(list(CARGO))) for i, h in enumerate(houses)]


class Bay:
    """Кузов: 2 ряда по 4 места. Ряд это стопка: достать можно только то,
    что лежит ближе всех к двери (конец списка). Положили последним, достаём первым."""

    def __init__(self, lanes: int = BAY_LANES, depth: int = BAY_DEPTH):
        self.depth = depth
        self.lanes: list[list[int]] = [[] for _ in range(lanes)]

    def can_push(self, lane: int) -> bool:
        return len(self.lanes[lane]) < self.depth

    def push(self, lane: int, item: int) -> None:
        if not self.can_push(lane):
            raise ValueError("ряд заполнен")
        self.lanes[lane].append(item)

    def peek(self, lane: int):
        return self.lanes[lane][-1] if self.lanes[lane] else None

    def pop(self, lane: int):
        return self.lanes[lane].pop() if self.lanes[lane] else None

    def remove(self, item: int) -> None:
        for lane in self.lanes:
            if item in lane:
                lane.remove(item)
                return

    def find(self, item: int):
        for li, lane in enumerate(self.lanes):
            if item in lane:
                return li, lane.index(item)
        return None

    def in_front(self, item: int) -> int:
        """Сколько посылок лежит между этой и дверью."""
        pos = self.find(item)
        if pos is None:
            return 0
        li, idx = pos
        return len(self.lanes[li]) - 1 - idx

    def count(self) -> int:
        return sum(len(lane) for lane in self.lanes)

    def items(self) -> list[int]:
        return [i for lane in self.lanes for i in lane]


def dig_estimate(route: list[int], lanes: list[list[int]], house_of) -> int:
    """Сколько посылок придётся вынуть, чтобы добраться до нужных по маршруту.

    route: индексы домов по порядку, lanes: id посылок в рядах (конец = у двери),
    house_of(id) -> индекс дома. Вынутые посылки возвращаются в тот же ряд."""
    lanes = [list(lane) for lane in lanes]
    total = 0
    for house in route:
        found = False
        for lane in lanes:
            for i, item in enumerate(lane):
                if house_of(item) == house:
                    total += len(lane) - 1 - i
                    del lane[i]
                    found = True
                    break
            if found:
                break
    return total


# ------------------------------------------------------------------ маршрут
def route_length(zs: list[float], start_z: float) -> float:
    """Длина пути по улице от старта через все остановки по порядку."""
    total, cur = 0.0, start_z
    for z in zs:
        total += abs(z - cur)
        cur = z
    return total


def route_time_limit(length: float, stops: int, obstacles: int) -> int:
    """Время на весь маршрут в секундах."""
    return int(30 + length / 8.0 + stops * 28 + obstacles * 12)
