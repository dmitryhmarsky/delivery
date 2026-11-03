"""Тесты чистой логики. Запуск: python tests/test_logic.py (или pytest)."""
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import logic  # noqa: E402


def test_no_damage_when_walking():
    assert logic.shake_damage(logic.WALK_SPEED, 1.0, 1.0) == 0
    assert logic.shake_damage(logic.SPRINT_SPEED, 1.0, 1.0) > 0


def test_fragile_cargo_takes_more_damage():
    d_glass = logic.shake_damage(8, 1, logic.CARGO["glass"]["fragility"])
    d_parcel = logic.shake_damage(8, 1, logic.CARGO["parcel"]["fragility"])
    assert d_glass > d_parcel


def test_narrow_passage_punishes_speed():
    assert logic.narrow_damage(logic.CREEP_SPEED, 1, 1) == 0
    assert logic.narrow_damage(logic.WALK_SPEED, 1, 1) > 0


def test_hard_braking_only_hurts_when_hard_and_fast():
    assert logic.hard_brake_damage(logic.VAN_COAST_DECEL, 11, 1, 1) == 0     # плавно
    assert logic.hard_brake_damage(logic.VAN_BRAKE_DECEL, 2, 1, 1) == 0      # медленно
    assert logic.hard_brake_damage(logic.VAN_BRAKE_DECEL, 11, 1, 1) > 0      # резко и быстро


def test_payment():
    assert logic.payment(100, 100, 10, 60) == 125          # бонус за аккуратность
    assert logic.payment(100, 50, 10, 60) == 50            # половина целостности
    assert logic.payment(100, 0, 10, 60) == 0              # груз уничтожен
    assert logic.payment(100, 80, 120, 60) == int(round(100 * 0.8 * 0.4))  # сильно опоздал


def test_bay_is_a_stack_per_lane():
    bay = logic.Bay()
    bay.push(0, 10)
    bay.push(0, 11)
    bay.push(1, 12)
    assert bay.peek(0) == 11            # последний положенный достаётся первым
    assert bay.in_front(10) == 1        # перед десяткой лежит одиннадцатая
    assert bay.in_front(11) == 0
    assert bay.pop(0) == 11 and bay.pop(0) == 10 and bay.pop(0) is None
    for i in range(logic.BAY_DEPTH):          # левый ряд к этому моменту пуст
        bay.push(0, 100 + i)
    assert not bay.can_push(0)


def test_dig_estimate_good_and_bad_packing():
    house_of = {1: 0, 2: 1, 3: 2}.get
    route = [0, 1, 2]
    # правильно: первый по маршруту лежит ближе к двери (положен последним)
    good = [[3, 2, 1], []]
    assert logic.dig_estimate(route, good, house_of) == 0
    # плохо: первый по маршруту лежит глубже всех
    bad = [[1, 2, 3], []]
    assert logic.dig_estimate(route, bad, house_of) == 2 + 1
    # разложить по двум рядам тоже убирает возню
    split = [[1], [3, 2]]
    assert logic.dig_estimate(route, split, house_of) == 0


def test_route_changes_dig_cost():
    house_of = {1: 0, 2: 1, 3: 2}.get
    lanes = [[1, 2, 3], []]                 # у двери лежит дом 2
    assert logic.dig_estimate([2, 1, 0], lanes, house_of) == 0
    assert logic.dig_estimate([0, 1, 2], lanes, house_of) > 0


def test_route_length_and_time():
    assert logic.route_length([20, 50, 10], 0) == 20 + 30 + 40
    assert logic.route_time_limit(100, 6, 5) > logic.route_time_limit(100, 6, 0)


def test_make_cargo_one_parcel_per_house():
    cargo = logic.make_cargo(random.Random(3), 6)
    assert sorted(c.house_index for c in cargo) == list(range(6))
    assert len({c.id for c in cargo}) == 6


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
