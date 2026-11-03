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


def test_payment():
    assert logic.payment(100, 100, 10, 60) == 125          # бонус за аккуратность
    assert logic.payment(100, 50, 10, 60) == 50            # половина целостности
    assert logic.payment(100, 0, 10, 60) == 0              # груз уничтожен
    assert logic.payment(100, 80, 120, 60) == int(round(100 * 0.8 * 0.4))  # сильно опоздал


def test_order_generation():
    rng = random.Random(1)
    houses = [{"number": n, "distance": 30 + n, "obstacles": ["dog"]} for n in range(4)]
    seen = {logic.new_order(rng, houses, last_index=2).house_index for _ in range(50)}
    assert 2 not in seen
    o = logic.new_order(rng, houses)
    assert o.time_limit > 40 and o.base_pay > 0


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
