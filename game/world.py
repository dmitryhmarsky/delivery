"""Улица, дома, заборы, фургон. Всё собирается из примитивов + процедурных текстур."""
from __future__ import annotations

from dataclasses import dataclass, field

from ursina import Color, Entity, Vec3, color

from .obstacles import Dog, Sprinkler

ROAD_HALF = 4.0
FENCE_X = 6.5        # линия забора вдоль тротуара (по модулю)
BACK_X = 26.8        # задняя граница района
Z_MIN, Z_MAX = -5.0, 112.0
YARD_HALF = 9.0      # половина ширины участка по z
FRONT_X = 17.0       # передняя стена дома (по модулю)
HOUSE_CX = 21.0      # центр дома по x (по модулю)

VAN_POS = Vec3(2.0, 0, 8.0)
SPAWN_POS = Vec3(2.0, 1.0, 0.0)
VAN_HALF = 2.1       # половина длины кузова

# Кузов: 2 ряда по 4 места, достать можно только ближайшую к двери посылку
LANE_X = (-0.5, 0.5)
FLOOR_Y = 0.55
SLOT_Z0 = 1.25       # место 0 (самое глубокое) по z внутри кузова
SLOT_DZ = 0.95

# (номер дома, сторона: -1 слева / +1 справа, z, цвет, название цвета)
HOUSE_PLAN = [
    (12, -1, 22.0, "#e53935", "красный"),
    (21, 1, 36.0, "#1e88e5", "синий"),
    (14, -1, 54.0, "#fdd835", "жёлтый"),
    (23, 1, 68.0, "#43a047", "зелёный"),
    (16, -1, 86.0, "#fb8c00", "оранжевый"),
    (25, 1, 100.0, "#8e24aa", "фиолетовый"),
]


def slot_local(lane: int, idx: int) -> Vec3:
    """Позиция посылки в кузове (локальные координаты фургона)."""
    return Vec3(LANE_X[lane], FLOOR_Y + 0.35, SLOT_Z0 - idx * SLOT_DZ)


def box(x, y, z, sx, sy, sz, col=None, tex=None, tiles=None, collider=None, **kw):
    e = Entity(model="cube", position=(x, y, z), scale=(sx, sy, sz), **kw)
    if col is not None:
        e.color = col
    if tex is not None:
        e.texture = tex
    if tiles:
        e.texture_scale = tiles
    if collider:
        e.collider = collider
    return e


def plane(x, y, z, sx, sz, tex, tiles=None, collider=None):
    e = Entity(model="plane", position=(x, y, z), scale=(sx, 1, sz), texture=tex)
    e.texture_scale = tiles or (max(1, sx / 4), max(1, sz / 4))
    if collider:
        e.collider = collider
    return e


@dataclass
class House:
    number: int
    side: int
    z: float
    color_hex: str
    color_name: str
    obstacles: list
    door_pos: Vec3
    beam: Entity
    dogs: list = field(default_factory=list)
    sprinklers: list = field(default_factory=list)
    narrow_zone: tuple | None = None   # (xmin, xmax, zmin, zmax)
    gate: float = 3.2                  # ширина калитки

    def set_target(self, on: bool) -> None:
        self.beam.enabled = on

    @property
    def label(self) -> str:
        return f"№{self.number} ({self.color_name})"


def build_house(number, side, z, col_hex, col_name, obstacles, T) -> House:
    s = side
    gate = 1.3 if "narrow" in obstacles else 3.2
    mark = color.hex(col_hex)

    box(s * HOUSE_CX, 2.5, z, 8, 5, 8, tex=T("brick"), tiles=(3, 2), collider="box")
    box(s * HOUSE_CX, 5.15, z, 9, 0.3, 9, tex=T("roof"), tiles=(3, 3), collider="box")
    box(s * (HOUSE_CX + 1.5), 6.0, z - 2, 1, 1.6, 1, tex=T("brick"))
    box(s * (FRONT_X - 0.05), 1.05, z, 0.15, 2.1, 1.2, tex=T("door"))
    box(s * (FRONT_X - 0.08), 2.4, z, 0.2, 0.3, 1.6, col=mark)          # полоса над дверью
    for dz in (-2.6, 2.6):
        box(s * (FRONT_X - 0.03), 2.6, z + dz, 0.1, 1.2, 1.2, col=color.hex("#6fa8dc"))
    box(s * (FRONT_X - 0.9), 0.1, z, 1.8, 0.2, 2.4, tex=T("concrete"))
    plane(s * 10.8, 0.03, z, 8.6, 1.6, T("concrete"), tiles=(4, 1))     # дорожка
    box(s * 7.2, 0.9, z + gate / 2 + 0.7, 0.35, 1.8, 0.35, col=mark)    # цветной столбик у калитки

    door_pos = Vec3(s * (FRONT_X - 1.4), 1, z)
    beam = box(door_pos.x, 7, z, 0.3, 14, 0.3,
               col=Color(mark.r, mark.g, mark.b, 0.5))
    beam.enabled = False

    house = House(number, side, z, col_hex, col_name, list(obstacles), door_pos, beam, gate=gate)

    lo, hi = sorted((s * 7.5, s * 16.0))
    if "dog" in obstacles:
        house.dogs.append(Dog((lo, hi, z - 8.5, z + 8.5)))
    if "sprinkler" in obstacles:
        house.sprinklers.append(Sprinkler(Vec3(s * 11.5, 0, z)))
    if "narrow" in obstacles:
        length = 12.5 - FENCE_X
        cx = s * (FENCE_X + 12.5) / 2
        hedge = color.hex("#2f6b2f")
        for dz in (-(gate / 2 + 0.2), gate / 2 + 0.2):
            box(cx, 0.9, z + dz, length, 1.8, 0.4, col=hedge, tex=T("grass"),
                tiles=(3, 1), collider="box")
        a, b = sorted((s * FENCE_X, s * 12.5))
        house.narrow_zone = (a, b, z - gate / 2, z + gate / 2)

    side_len = BACK_X - FENCE_X
    for dz in (-YARD_HALF, YARD_HALF):
        box(s * (FENCE_X + BACK_X) / 2, 0.6, z + dz, side_len, 1.2, 0.2,
            tex=T("wood"), tiles=(8, 1), collider="box")
    return house


def _fence_segment(x, z0, z1, T):
    length = z1 - z0
    if length <= 0.05:
        return
    box(x, 0.6, (z0 + z1) / 2, 0.2, 1.2, length, tex=T("wood"),
        tiles=(max(1, length / 2), 1), collider="box")


def build_fence_line(side, houses, T):
    x = side * FENCE_X
    cur = Z_MIN
    for h in sorted((h for h in houses if h.side == side), key=lambda h: h.z):
        _fence_segment(x, cur, h.z - h.gate / 2, T)
        for pz in (h.z - h.gate / 2, h.z + h.gate / 2):
            box(x, 0.9, pz, 0.35, 1.8, 0.35, tex=T("wood"))
        cur = h.z + h.gate / 2
    _fence_segment(x, cur, Z_MAX, T)


def build_van(T) -> Entity:
    """Фургон с открытым задом: внутри видно ряды с посылками."""
    van = Entity(position=VAN_POS)
    white = color.hex("#f2f2f2")
    solids = []

    def part(*a, **kw):
        e = box(*a, parent=van, **kw)
        if kw.get("collider"):
            solids.append(e)
        return e

    part(0, 0.475, 0, 2.2, 0.15, 4.2, col=color.hex("#8d8d8d"), collider="box")      # пол
    part(-1.05, 1.45, 0, 0.1, 1.8, 4.2, col=white, collider="box")                   # левая стена
    part(1.05, 1.45, 0, 0.1, 1.8, 4.2, col=white, collider="box")                    # правая стена
    part(0, 2.4, 0, 2.2, 0.15, 4.2, col=white, collider="box")                       # крыша
    part(0, 1.45, VAN_HALF, 2.2, 1.8, 0.1, col=white, collider="box")                # перегородка
    part(0, 1.3, 2.8, 2.2, 1.5, 1.4, col=color.hex("#d9d9d9"), collider="box")       # кабина
    part(0, 1.55, 3.51, 2.0, 0.7, 0.05, col=color.hex("#2b3a4a"))                    # лобовое
    for sx in (-1.11, 1.11):
        part(sx, 1.5, 0, 0.02, 0.2, 4.25, col=color.hex("#e0a030"))                  # жёлтая полоса
    part(0, 0.56, 0, 0.04, 0.01, 4.0, col=color.hex("#555555"))                      # разметка рядов
    for sx in (-1.1, 1.1):
        for wz in (-1.4, 2.5):
            part(sx, 0.35, wz, 0.3, 0.7, 0.7, col=color.black)
    van.solids = solids
    return van


def _tree(x, z, T):
    box(x, 1.5, z, 0.5, 3, 0.5, tex=T("wood"))
    box(x, 3.6, z, 3, 2.6, 3, col=color.hex("#2e7d32"), tex=T("grass"), tiles=(2, 2))
    box(x, 5.4, z, 2, 1.8, 2, col=color.hex("#3a8f3e"), tex=T("grass"), tiles=(1, 1))


def build_world(T, obstacle_sets):
    """Возвращает (houses, van). obstacle_sets: набор препятствий для каждого дома."""
    span = Z_MAX - Z_MIN
    cz = (Z_MAX + Z_MIN) / 2

    plane(0, 0, cz, BACK_X * 2 + 2, span + 10, T("grass"),
          tiles=(BACK_X * 2 / 4, span / 4), collider="box")
    plane(0, 0.01, cz, ROAD_HALF * 2, span, T("asphalt"), tiles=(2, span / 4))
    for sx in (-1, 1):
        plane(sx * (ROAD_HALF + FENCE_X) / 2, 0.01, cz, FENCE_X - ROAD_HALF, span,
              T("concrete"), tiles=(1, span / 2))
    for zc in range(0, int(Z_MAX), 6):
        box(0, 0.03, zc + 1.5, 0.2, 0.01, 2.5, col=color.hex("#f5c518"))

    hedge = color.hex("#2f6b2f")
    for sx in (-1, 1):
        box(sx * BACK_X, 1.25, cz, 0.4, 2.5, span, col=hedge, tex=T("grass"),
            tiles=(1, span / 3), collider="box")
    for ez in (Z_MIN, Z_MAX):
        box(0, 1.25, ez, BACK_X * 2, 2.5, 0.4, col=hedge, tex=T("grass"),
            tiles=(BACK_X / 3, 1), collider="box")

    houses = [build_house(n, s, z, ch, cn, obs, T)
              for (n, s, z, ch, cn), obs in zip(HOUSE_PLAN, obstacle_sets)]
    build_fence_line(-1, houses, T)
    build_fence_line(1, houses, T)

    for tx, tz in [(-14, 6), (-20, 38), (-14, 70), (-22, 4), (-14, 106),
                   (14, 10), (20, 52), (14, 84), (22, 20)]:
        _tree(tx, tz, T)

    van = build_van(T)
    return houses, van
