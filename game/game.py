"""Главный цикл: загрузка фургона, планирование маршрута, езда и выгрузка по очереди.

Фазы дня:
  LOAD  посылки лежат на земле, игрок сам раскладывает их по рядам кузова
  PLAN  карта маршрута (в этот момент время стоит)
  DRIVE едем по маршруту, достаём посылки из кузова и вручаем у дверей
  DONE  итоги дня
"""
from __future__ import annotations

import random
from pathlib import Path

from ursina import (Entity, Text, Texture, Vec3, application, camera, clamp, color, destroy,
                    distance_xz, held_keys, invoke, lerp, scene, time, window)
from ursina.prefabs.first_person_controller import FirstPersonController

from . import logic
from .planner import Planner
from .textures import ensure_textures
from .world import SPAWN_POS, VAN_HALF, VAN_POS, Z_MAX, Z_MIN, build_world, slot_local

TEX_DIR = Path(__file__).resolve().parent.parent / "assets" / "textures"

KIND_COLORS = {"parcel": "#c4965c", "cake": "#f7a8c4", "glass": "#9fd8ee"}
DEPOT = [(0.2, 3.4), (2.0, 3.4), (3.8, 3.4), (0.2, 1.9), (2.0, 1.9), (3.8, 1.9)]
LANE_NAMES = ("Левый ряд", "Правый ряд")


def move_toward(a: float, b: float, step: float) -> float:
    return a + clamp(b - a, -step, step)


class Game(Entity):
    def __init__(self, seed=None):
        super().__init__()
        self.rng = random.Random(seed)

        ensure_textures(TEX_DIR)
        self._tex_cache = {}

        variants = [list(v) for v in logic.OBSTACLE_VARIANTS]
        self.rng.shuffle(variants)
        self.houses, self.van = build_world(self.T, variants)

        self.player = FirstPersonController(position=SPAWN_POS, speed=logic.WALK_SPEED)
        self.default_jump = self.player.jump_height
        for house in self.houses:
            for dog in house.dogs:
                dog.game = self

        self.planner = Planner(self)
        self.money = 0
        self.day = 0
        self.bones = 3
        self.ent = {}
        self.summary = None

        self.speed = 0.0
        self.last_pos = Vec3(*self.player.position)
        self.last_y = self.player.y
        self.fall_speed = 0.0
        self.was_grounded = True
        self.flash = 0.0
        self.msg_t = 0.0
        self.water_msg_cd = 0.0

        self._build_hud()
        self.start_day()

    # ------------------------------------------------------------ ресурсы
    def T(self, name):
        if name not in self._tex_cache:
            self._tex_cache[name] = Texture(TEX_DIR / f"{name}.png")
        return self._tex_cache[name]

    # ---------------------------------------------------------------- HUD
    def _build_hud(self):
        tl = window.top_left
        self.info = Text(text="", origin=(-0.5, 0.5), position=(tl.x + 0.02, tl.y - 0.02), scale=1.1)
        self.order_text = Text(text="", origin=(-0.5, 0.5), position=(tl.x + 0.02, tl.y - 0.07), scale=1.0)
        self.bay_text = Text(text="", origin=(-0.5, 0.5), position=(tl.x + 0.02, -0.05), scale=1.0,
                             color=color.yellow)
        self.bar_bg = Entity(parent=camera.ui, model="quad", color=color.hex("#222222"),
                             scale=(0.5, 0.03), position=(0, -0.42))
        self.bar = Entity(parent=camera.ui, model="quad", color=color.lime,
                          origin=(-0.5, 0), scale=(0.5, 0.03), position=(-0.25, -0.42, -0.01))
        self.bar_text = Text(text="", origin=(0, 0), position=(0, -0.38), scale=0.9)
        self.hint = Text(text="", origin=(0, 0), position=(0, -0.32), scale=1.1)
        self.msg = Text(text="", origin=(0, 0), position=(0, 0.22), scale=1.5, color=color.yellow)
        Text(text="E действие   G взять/бросить   P маршрут   F кость   C осторожно   X разворот   R к фургону",
             origin=(0.5, -0.5), position=(window.bottom_right.x - 0.02, window.bottom_right.y + 0.02),
             scale=0.75, color=color.light_gray)

    def say(self, text, duration=2.5):
        self.msg.text = text
        self.msg_t = duration

    # --------------------------------------------------------------- день
    def start_day(self):
        for e in self.ent.values():
            destroy(e)
        self.ent = {}
        if self.summary:
            destroy(self.summary)
            self.summary = None
        for h in self.houses:
            h.set_target(False)
        if getattr(self, "driving", False):
            self._leave_driver_seat()

        self.day += 1
        self.cargo = {c.id: c for c in logic.make_cargo(self.rng, len(self.houses))}
        self.bay = logic.Bay()
        self.on_ground = set()
        self.carried = None
        self.delivered = set()
        self.lost = set()
        self.route = []
        self.prev_phase = "LOAD"
        self.phase = "LOAD"
        self.driving = False
        self.vel = 0.0
        self.elapsed = 0.0
        self.limit = 0
        self.dig_moves = 0
        self.day_earned = 0
        self.bones = 3

        self.van.position = VAN_POS
        self.van.rotation_y = 0
        for cid, c in self.cargo.items():
            self.ent[cid] = self._make_parcel(c)
            x, z = DEPOT[cid % len(DEPOT)]
            self._place(cid, "ground", pos=Vec3(x, 0.28, z))
            self.on_ground.add(cid)

        self.player.position = SPAWN_POS
        self.last_pos = Vec3(*self.player.position)
        self.say("Загрузи фургон: подними посылку (G), у задней двери нажми E. "
                 "Что положишь последним, достанешь первым!", 7)

    def finish_day(self):
        self.phase = "DONE"
        t = int(self.elapsed)
        lim = self.limit
        self.summary = Text(
            text=(f"День {self.day} завершён!\n\n"
                  f"Доставлено: {len(self.delivered)} из {len(self.cargo)}, разбито: {len(self.lost)}\n"
                  f"Заработано за день: ${self.day_earned}\n"
                  f"Время: {t // 60}:{t % 60:02d} из {lim // 60}:{lim % 60:02d}\n"
                  f"Лишних перекладываний в кузове: {self.dig_moves}\n\n"
                  f"N — новый день"),
            origin=(0, 0), position=(0, 0.05), scale=1.6, color=color.yellow)

    # ---------------------------------------------------------- посылки
    def _make_parcel(self, c):
        h = self.houses[c.house_index]
        e = Entity(model="cube", color=color.hex(h.color_hex))
        Entity(parent=e, model="cube", color=color.hex(KIND_COLORS[c.kind]),
               scale=(1.04, 0.22, 1.04), y=0.44)
        return e

    def _place(self, cid, where, pos=None):
        e = self.ent[cid]
        e.rotation = (0, 0, 0)
        if where == "carried":
            e.parent = camera
            e.scale = (0.45, 0.38, 0.45)
            e.position = (0.35, -0.4, 0.9)
        elif where == "bay":
            lane, idx = self.bay.find(cid)
            e.parent = self.van
            e.scale = (0.8, 0.7, 0.8)
            e.position = slot_local(lane, idx)
        else:
            e.parent = scene
            e.scale = (0.6, 0.55, 0.6)
            e.position = pos

    def refresh_bay(self):
        for lane in self.bay.lanes:
            for cid in lane:
                self._place(cid, "bay")

    def house_of(self, cid):
        return self.cargo[cid].house_index

    def item_label(self, cid):
        h = self.houses[self.cargo[cid].house_index]
        return f"№{h.number} {h.color_name} ({self.cargo[cid].kind_name.lower()})"

    def bay_description(self):
        out = []
        for li, lane in enumerate(self.bay.lanes):
            items = ", ".join(self.item_label(cid) for cid in reversed(lane)) or "пусто"
            out.append(f"{LANE_NAMES[li]}: {items}")
        return "\n".join(out)

    def cur(self):
        return self.cargo[self.carried] if self.carried is not None else None

    def _forget(self, cid):
        """Посылка пропала (доставлена или разбита): убрать отовсюду."""
        self.bay.remove(cid)
        self.on_ground.discard(cid)
        if self.carried == cid:
            self.carried = None
        if cid in self.ent:
            destroy(self.ent.pop(cid))
        house = self.cargo[cid].house_index
        if house in self.route:
            self.route.remove(house)
        self.refresh_bay()

    def break_item(self, cid, where):
        self._forget(cid)
        self.lost.add(cid)
        self.money = max(0, self.money - 20)
        self.day_earned -= 20
        self.say(f"Посылка разбита ({where})! Штраф $20", 3.5)
        self._check_done()

    def _check_done(self):
        if len(self.delivered) + len(self.lost) == len(self.cargo):
            self.finish_day()

    # --------------------------------------------------------------- урон
    def hurt(self, amount):
        c = self.cur()
        if c is None or amount <= 0:
            return
        c.integrity = max(0.0, c.integrity - amount)
        self.flash = 0.25
        if c.integrity <= 0:
            self.break_item(c.id, "в руках")

    def damage_bay(self, dmg_fn):
        for cid in list(self.bay.items()):
            c = self.cargo[cid]
            c.integrity = max(0.0, c.integrity - dmg_fn(c))
            if c.integrity <= 0:
                self.break_item(cid, "в кузове")

    def on_dog_bite(self):
        if self.carried is not None:
            self.hurt(logic.dog_bite_damage(self.cur().fragility))
            self.say("Собака толкнула тебя! Груз повреждён", 2)
        else:
            self.say("Собака тебя укусила!", 1.5)

    # ----------------------------------------------------- геометрия фургона
    def rear_point(self):
        return self.van.world_position + self.van.back * (VAN_HALF + 0.8)

    def cab_point(self):
        return self.van.world_position + self.van.forward * 2.6

    def near_rear(self):
        return distance_xz(self.player.position, self.rear_point()) < 2.4

    def near_cab(self):
        return distance_xz(self.player.position, self.cab_point()) < 3.2

    def lane_side(self):
        """0 = левый ряд, 1 = правый: смотря с какой стороны от оси фургона стоит игрок."""
        v, p, r = self.van.world_position, self.player.position, self.van.right
        lateral = (p.x - v.x) * r.x + (p.z - v.z) * r.z
        return 1 if lateral >= 0 else 0

    def nearest_ground(self):
        best, best_d = None, 2.2
        for cid in self.on_ground:
            d = distance_xz(self.player.position, self.ent[cid].position)
            if d < best_d:
                best, best_d = cid, d
        return best

    # ---------------------------------------------------------- ввод
    def input(self, key):
        if self.phase == "PLAN":
            return
        if key == "escape":
            application.quit()
        elif self.phase == "DONE":
            if key == "n":
                self.start_day()
        elif key == "e":
            self.interact()
        elif key == "g":
            self.pick_or_drop()
        elif key == "p":
            self.open_planner()
        elif key == "f":
            self.throw_bone()
        elif key == "x":
            self.turn_around()
        elif key == "r":
            self.player.position = self.rear_point() + self.van.back * 1.0 + Vec3(0, 0.15, 0)  # без падения
            self.last_pos = Vec3(*self.player.position)

    def interact(self):
        if self.driving:
            if abs(self.vel) < 1.0:
                self.exit_van()
            else:
                self.say("Сначала остановись", 1.5)
            return
        c = self.cur()
        p = self.player.position
        if c is not None:
            for i, h in enumerate(self.houses):
                if distance_xz(p, h.door_pos) < 2.4:
                    self.try_deliver(c, i)
                    return
            if self.near_rear():
                self.load_into_bay(c)
            else:
                self.say("Положить в фургон можно у задней двери (E)", 1.5)
        elif self.near_rear():
            self.take_from_bay()
        elif self.near_cab():
            if self.phase == "DRIVE":
                self.enter_van()
            else:
                self.say("Сначала загрузи всё и составь маршрут (P)", 2.5)

    def pick_or_drop(self):
        if self.driving:
            return
        if self.carried is not None:
            f = self.player.forward
            p = self.player.position
            cid = self.carried
            self.carried = None
            self.on_ground.add(cid)
            self._place(cid, "ground", pos=Vec3(p.x + f.x * 1.0, 0.28, p.z + f.z * 1.0))
            return
        cid = self.nearest_ground()
        if cid is None:
            self.say("Рядом нет посылок на земле", 1.2)
            return
        self.on_ground.discard(cid)
        self.carried = cid
        self._place(cid, "carried")
        self.say(f"Взял: {self.item_label(cid)}", 1.8)

    # -------------------------------------------------- кузов и доставка
    def load_into_bay(self, c):
        lane = self.lane_side()
        if not self.bay.can_push(lane):
            lane = 1 - lane
            if not self.bay.can_push(lane):
                self.say("Кузов заполнен", 1.5)
                return
        self.bay.push(lane, c.id)
        self.carried = None
        self._place(c.id, "bay")
        self.say(f"{LANE_NAMES[lane]}: {self.item_label(c.id)}", 1.5)

    def take_from_bay(self):
        lane = self.lane_side()
        cid = self.bay.peek(lane)
        if cid is None:
            self.say(f"{LANE_NAMES[lane]} пуст. Встань с другой стороны от оси фургона", 2)
            return
        if self.phase == "DRIVE" and (not self.route or self.cargo[cid].house_index != self.route[0]):
            self.dig_moves += 1
        self.bay.pop(lane)
        self.carried = cid
        self._place(cid, "carried")
        self.say(f"Достал: {self.item_label(cid)}", 1.5)

    def try_deliver(self, c, house_index):
        h = self.houses[house_index]
        if self.phase != "DRIVE":
            self.say("Сначала загрузи фургон и составь маршрут (P)", 2)
            return
        if c.house_index != house_index:
            target = self.houses[c.house_index]
            self.say(f"Это дом {h.label}, а посылка для {target.label}", 2.5)
            return
        if self.route and self.route[0] != house_index:
            self.say(f"По плану сейчас дом {self.houses[self.route[0]].label} (P: изменить маршрут)", 3)
            return
        dist = abs(h.door_pos.z - VAN_POS.z)
        pay = logic.payment(logic.base_pay(c.kind, dist), c.integrity, self.elapsed, self.limit)
        self.money += pay
        self.day_earned += pay
        self.delivered.add(c.id)
        extra = " Безупречно! +25%" if c.integrity >= 98 else ""
        late = " (с опозданием)" if self.elapsed > self.limit else ""
        self._forget(c.id)
        self.say(f"Доставлено в дом {h.label}! +${pay}{late}{extra}", 3.5)
        self._refresh_target()
        self._check_done()

    def _refresh_target(self):
        for h in self.houses:
            h.set_target(False)
        if self.route and self.phase == "DRIVE":
            self.houses[self.route[0]].set_target(True)

    # ------------------------------------------------------ планирование
    def open_planner(self):
        if self.driving or self.phase in ("PLAN", "DONE"):
            return
        if self.phase == "LOAD":
            left = len(self.cargo) - self.bay.count()
            if left > 0:
                self.say(f"Сначала загрузи все посылки в кузов (осталось {left})", 2.5)
                return
            stops = [c.house_index for c in self.cargo.values()]
        else:
            stops = [c.house_index for cid, c in self.cargo.items()
                     if cid not in self.delivered and cid not in self.lost]
        if not stops:
            return
        self.prev_phase = self.phase
        self.phase = "PLAN"
        self.player.speed = 0
        self.planner.open(stops, self.on_plan_confirm, self.on_plan_cancel)

    def on_plan_confirm(self, route):
        self.route = list(route)
        if self.prev_phase == "LOAD":
            zs = [self.houses[i].z for i in self.route]
            length = logic.route_length(zs, self.van.z)
            obstacles = sum(len(self.houses[i].obstacles) for i in self.route)
            self.limit = logic.route_time_limit(length, len(self.route), obstacles)
            self.elapsed = 0.0
            self.say("Маршрут принят. Садись в кабину (E у передней двери) и поехали!", 5)
        else:
            self.say("Маршрут изменён", 2)
        self.phase = "DRIVE"
        self._refresh_target()

    def on_plan_cancel(self):
        # Esc приходит и планировщику, и Game.input: пока фаза PLAN, второй его игнорирует,
        # поэтому возвращаем прежнюю фазу чуть позже, иначе игра закроется.
        invoke(setattr, self, "phase", self.prev_phase, delay=0.2)

    # ------------------------------------------------------------ фургон
    def enter_van(self):
        self.driving = True
        self.vel = 0.0
        for e in self.van.solids:
            e.collider = None
        self.player.speed = 0
        self.player.jump_height = 0
        self.player.camera_pivot.y = 1.5
        self.say("За рулём: W газ, S тормоз (резко не надо!), A/D сместиться, X разворот, E выйти", 5)

    def _leave_driver_seat(self):
        self.driving = False
        for e in self.van.solids:
            e.collider = "box"
        self.player.jump_height = self.default_jump
        self.player.camera_pivot.y = self.player.height

    def exit_van(self):
        self._leave_driver_seat()
        side = 2.0 if self.van.x >= 0 else -2.0
        self.vel = 0.0
        self.player.position = Vec3(self.van.x + side, 1, self.van.z + self.van.forward.z * 2.4)
        self.last_pos = Vec3(*self.player.position)
        self.say("Приехали. Задняя дверь сзади фургона: E чтобы достать посылку", 3)

    def turn_around(self):
        if self.driving and abs(self.vel) < 0.6:
            self.van.rotation_y += 180
            self.player.rotation_y += 180

    def update_driving(self, dt):
        v = self.van
        throttle = held_keys["w"] - held_keys["s"]
        old = self.vel
        if throttle > 0:
            target, rate = logic.VAN_MAX_SPEED, (logic.VAN_ACCEL if old >= 0 else logic.VAN_BRAKE_DECEL)
        elif throttle < 0:
            target, rate = -logic.VAN_REVERSE_SPEED, (logic.VAN_BRAKE_DECEL if old > 0 else logic.VAN_ACCEL)
        else:
            target, rate = 0.0, logic.VAN_COAST_DECEL
        self.vel = move_toward(old, target, rate * dt)

        if throttle < 0 and old > 3:
            self.damage_bay(lambda c: logic.hard_brake_damage(logic.VAN_BRAKE_DECEL, old, dt, c.fragility))
            self.flash = 0.25 if self.bay.count() else 0.0

        v.position += v.forward * (self.vel * dt)
        lat = (held_keys["d"] - held_keys["a"]) * v.right.x
        v.x = clamp(v.x + lat * 3.0 * dt, -3.0, 3.0)
        if not (Z_MIN + 4.5 < v.z < Z_MAX - 4.5):
            v.z = clamp(v.z, Z_MIN + 4.5, Z_MAX - 4.5)
            self.vel = 0.0

        self.player.speed = 0
        self.player.position = v.world_position + v.forward * 2.6 + v.right * -0.5
        self.last_pos = Vec3(*self.player.position)

    # --------------------------------------------------------------- кость
    def throw_bone(self):
        if self.bones <= 0:
            self.say("Кости кончились. Пополни у фургона (E у задней двери)", 2)
            return
        self.bones -= 1
        f = self.player.forward
        pos = Vec3(self.player.x + f.x * 7, 0.15, self.player.z + f.z * 7)
        bone = Entity(model="cube", color=color.white, scale=(0.4, 0.15, 0.15), position=pos)
        destroy(bone, delay=8)
        for h in self.houses:
            for dog in h.dogs:
                dog.distract(pos)

    # --------------------------------------------------------------- цикл
    def update(self):
        dt = min(time.dt, 0.05)
        if dt <= 0 or self.phase in ("PLAN", "DONE"):
            return
        if self.phase == "DRIVE":
            self.elapsed += dt
        if self.driving:
            self.update_driving(dt)
        else:
            self.update_walking(dt)
        self.update_hud(dt)

    def update_walking(self, dt):
        p = self.player.position
        if held_keys["c"]:
            self.player.speed = logic.CREEP_SPEED
        elif held_keys["left shift"]:
            self.player.speed = logic.SPRINT_SPEED
        else:
            self.player.speed = logic.WALK_SPEED

        moved = min(distance_xz(p, self.last_pos) / dt, 12.0)  # телепорт не считается бегом
        self.speed = lerp(self.speed, moved, min(1.0, dt * 10))
        self.last_pos = Vec3(*p)

        vy = (self.player.y - self.last_y) / dt
        self.last_y = self.player.y
        c = self.cur()
        if not self.player.grounded:
            self.fall_speed = max(self.fall_speed, -vy)
        elif not self.was_grounded:
            if c is not None:
                self.hurt(logic.landing_damage(self.fall_speed, c.fragility))
            self.fall_speed = 0.0
        self.was_grounded = self.player.grounded

        c = self.cur()
        if c is not None:
            dmg = logic.shake_damage(self.speed, dt, c.fragility)
            for h in self.houses:
                z = h.narrow_zone
                if z and z[0] <= p.x <= z[1] and z[2] <= p.z <= z[3]:
                    if self.speed > logic.NARROW_SPEED:
                        self.say("Тесно! Груз бьётся о стены. Иди осторожно (C)", 0.4)
                    dmg += logic.narrow_damage(self.speed, dt, c.fragility)
                for sp in h.sprinklers:
                    if sp.wets(p):
                        dmg += logic.water_damage(dt, c.fragility)
                        if self.water_msg_cd <= 0:
                            self.say("Поливалка! Жди, пока выключится", 1.2)
                            self.water_msg_cd = 2.0
            self.hurt(dmg)
        self.water_msg_cd = max(0.0, self.water_msg_cd - dt)

    # ----------------------------------------------------------------- HUD
    def _hint(self):
        p = self.player.position
        c = self.cur()
        if self.driving:
            return "E выйти (когда остановишься)   X разворот"
        if c is not None:
            for i, h in enumerate(self.houses):
                if distance_xz(p, h.door_pos) < 2.4:
                    return f"E вручить в дом {h.label}"
            if self.near_rear():
                return f"E положить в {LANE_NAMES[self.lane_side()].lower()}   G бросить на землю"
            return "G бросить на землю"
        if self.near_rear():
            cid = self.bay.peek(self.lane_side())
            if cid is not None:
                return f"E достать: {self.item_label(cid)} ({LANE_NAMES[self.lane_side()].lower()})"
            return f"{LANE_NAMES[self.lane_side()]} пуст"
        g = self.nearest_ground()
        if g is not None:
            return f"G поднять: {self.item_label(g)}"
        if self.phase == "DRIVE" and self.near_cab():
            return "E сесть за руль"
        return ""

    def update_hud(self, dt):
        N = len(self.cargo)
        self.info.text = (f"Деньги: ${self.money}   Доставлено: {len(self.delivered)}/{N}   "
                          f"Разбито: {len(self.lost)}   Кости: {self.bones}")

        if self.phase == "LOAD":
            self.order_text.text = (f"Загрузка: {self.bay.count()}/{N} в кузове. "
                                    f"Все в фургоне? Нажми P и составь маршрут")
        else:
            left = self.limit - self.elapsed
            timer = (f"{int(left // 60)}:{int(left % 60):02d}" if left >= 0
                     else f"просрочено на {int(-left)} с")
            if self.route:
                h = self.houses[self.route[0]]
                dist = int(distance_xz(self.player.position, h.door_pos))
                side = "справа" if h.side > 0 else "слева"
                drive = f"   Скорость: {int(abs(self.vel) * 3.6)} км/ч" if self.driving else ""
                self.order_text.text = (f"Дальше: дом {h.label}, {side}, {dist} м   "
                                        f"Время: {timer}{drive}")
            else:
                self.order_text.text = f"Время: {timer}"

        self.bay_text.text = ("Кузов (сначала у двери, потом вглубь):\n" + self.bay_description()
                              if self.near_rear() and not self.driving else "")

        c = self.cur()
        if c is not None:
            frac = c.integrity / logic.MAX_INTEGRITY
            self.bar_bg.enabled = self.bar.enabled = True
            self.bar.scale_x = max(0.001, 0.5 * frac)
            if self.flash > 0:
                self.bar.color = color.red
            else:
                self.bar.color = color.lime if frac > 0.6 else (color.yellow if frac > 0.3 else color.orange)
            self.bar_text.text = f"{self.item_label(c.id)}: целостность {int(c.integrity)}%"
        else:
            self.bar_bg.enabled = self.bar.enabled = False
            self.bar_text.text = ""
        self.flash = max(0.0, self.flash - dt)

        self.hint.text = self._hint()

        if self.msg_t > 0:
            self.msg_t -= dt
            if self.msg_t <= 0:
                self.msg.text = ""
