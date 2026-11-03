"""Главный игровой цикл: заказ, перенос груза, урон, оплата, HUD."""
from __future__ import annotations

import random
from pathlib import Path

from ursina import (Color, Entity, Text, Texture, Vec3, application, camera, color,
                    destroy, distance_xz, held_keys, lerp, time, window)
from ursina.prefabs.first_person_controller import FirstPersonController

from . import logic
from .textures import ensure_textures
from .world import SPAWN_POS, build_world

TEX_DIR = Path(__file__).resolve().parent.parent / "assets" / "textures"

CARGO_COLORS = {
    "parcel": color.hex("#c4965c"),
    "cake": color.hex("#f7a8c4"),
    "glass": color.hex("#9fd8ee"),
}


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
        for house in self.houses:
            for dog in house.dogs:
                dog.game = self

        self.money = 0
        self.delivered = 0
        self.bones = 3
        self.carrying = False
        self.box = None
        self.order = None
        self.last_house = None

        self.speed = 0.0
        self.last_pos = Vec3(*self.player.position)
        self.last_y = self.player.y
        self.fall_speed = 0.0
        self.was_grounded = True
        self.flash = 0.0
        self.msg_t = 0.0
        self.water_msg_cd = 0.0

        self._build_hud()
        self.new_order()
        self.say("Подойди к фургону и нажми E, чтобы взять груз", 5)

    # ------------------------------------------------------------ ресурсы
    def T(self, name):
        if name not in self._tex_cache:
            self._tex_cache[name] = Texture(TEX_DIR / f"{name}.png")
        return self._tex_cache[name]

    # ---------------------------------------------------------------- HUD
    def _build_hud(self):
        tl = window.top_left
        self.info = Text(text="", origin=(-0.5, 0.5), position=(tl.x + 0.02, tl.y - 0.02), scale=1.1)
        self.order_text = Text(text="", origin=(-0.5, 0.5), position=(tl.x + 0.02, tl.y - 0.08), scale=1.1)
        self.bar_bg = Entity(parent=camera.ui, model="quad", color=color.hex("#222222"),
                             scale=(0.5, 0.03), position=(0, -0.42))
        self.bar = Entity(parent=camera.ui, model="quad", color=color.lime,
                          origin=(-0.5, 0), scale=(0.5, 0.03), position=(-0.25, -0.42, -0.01))
        self.bar_text = Text(text="", origin=(0, 0), position=(0, -0.38), scale=0.9)
        self.hint = Text(text="", origin=(0, 0), position=(0, -0.32), scale=1.1)
        self.msg = Text(text="", origin=(0, 0), position=(0, 0.22), scale=1.5, color=color.yellow)
        self.crosshair_hint = Text(text="E — взять/вручить   F — кость   C — осторожно   Shift — бег   R — к фургону",
                                   origin=(0.5, -0.5), position=(window.bottom_right.x - 0.02, window.bottom_right.y + 0.02),
                                   scale=0.8, color=color.light_gray)

    def say(self, text, duration=2.5):
        self.msg.text = text
        self.msg_t = duration

    # -------------------------------------------------------------- заказы
    def new_order(self):
        for h in self.houses:
            h.set_target(False)
        infos = [{
            "number": h.number,
            "distance": distance_xz(self.van.position, h.door_pos),
            "obstacles": h.obstacles,
        } for h in self.houses]
        self.order = logic.new_order(self.rng, infos, self.last_house)
        self.last_house = self.order.house_index
        self.houses[self.order.house_index].set_target(True)

    def pick_up(self):
        self.carrying = True
        self.order.elapsed = 0.0
        self.order.integrity = logic.MAX_INTEGRITY
        c = CARGO_COLORS[self.order.cargo]
        self.box = Entity(parent=camera, model="cube", color=c, scale=(0.5, 0.4, 0.5),
                          position=(0.35, -0.4, 0.9))
        if self.order.cargo == "parcel":
            self.box.texture = self.T("cardboard")
        self.say(f"Груз взят: {self.order.cargo_name}. Неси в дом №{self.order.number}", 3)

    def drop_box(self):
        if self.box:
            destroy(self.box)
        self.box = None
        self.carrying = False

    def deliver(self):
        o = self.order
        pay = logic.payment(o.base_pay, o.integrity, o.elapsed, o.time_limit)
        self.money += pay
        self.delivered += 1
        extra = " Безупречно! +25%" if o.integrity >= 98 else ""
        late = " (с опозданием)" if o.elapsed > o.time_limit else ""
        self.drop_box()
        self.say(f"Доставлено! +${pay}{late}{extra}", 3.5)
        self.new_order()

    def fail_order(self):
        self.drop_box()
        self.money = max(0, self.money - 20)
        self.say("Груз уничтожен! Штраф $20", 3.5)
        self.new_order()

    # --------------------------------------------------------------- урон
    def hurt(self, amount):
        if not self.carrying or amount <= 0:
            return
        self.order.integrity = max(0.0, self.order.integrity - amount)
        self.flash = 0.25
        if self.order.integrity <= 0:
            self.fail_order()

    def on_dog_bite(self):
        if self.carrying:
            self.hurt(logic.dog_bite_damage(self.order.fragility))
            self.say("Собака толкнула тебя! Груз повреждён", 2)
        else:
            self.say("Собака тебя укусила!", 1.5)

    # ---------------------------------------------------------- взаимодействие
    def near_van(self):
        return distance_xz(self.player.position, self.van.position) < 6

    def near_door(self):
        h = self.houses[self.order.house_index]
        return distance_xz(self.player.position, h.door_pos) < 2.4

    def input(self, key):
        if key == "escape":
            application.quit()
        elif key == "e":
            if self.carrying and self.near_door():
                self.deliver()
            elif self.near_van():
                self.bones = 3
                if not self.carrying:
                    self.pick_up()
        elif key == "f":
            self.throw_bone()
        elif key == "r":
            self.player.position = SPAWN_POS
            self.last_pos = Vec3(*self.player.position)

    def throw_bone(self):
        if self.bones <= 0:
            self.say("Кости кончились. Пополни у фургона (E)", 2)
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
        if dt <= 0:
            return
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
        if not self.player.grounded:
            self.fall_speed = max(self.fall_speed, -vy)
        elif not self.was_grounded:
            if self.carrying:
                self.hurt(logic.landing_damage(self.fall_speed, self.order.fragility))
            self.fall_speed = 0.0
        self.was_grounded = self.player.grounded

        if self.carrying:
            o = self.order
            o.elapsed += dt
            fr = o.fragility
            self.hurt(logic.shake_damage(self.speed, dt, fr))
            for h in self.houses:
                z = h.narrow_zone
                if z and z[0] <= p.x <= z[1] and z[2] <= p.z <= z[3]:
                    if self.speed > logic.NARROW_SPEED:
                        self.say("Тесно! Груз бьётся о стены. Иди осторожно (C)", 0.4)
                    self.hurt(logic.narrow_damage(self.speed, dt, fr))
                for sp in h.sprinklers:
                    if sp.wets(p):
                        self.hurt(logic.water_damage(dt, fr))
                        if self.water_msg_cd <= 0:
                            self.say("Поливалка! Жди, пока выключится", 1.2)
                            self.water_msg_cd = 2.0
        self.water_msg_cd = max(0.0, self.water_msg_cd - dt)

        self._update_hud(dt)

    def _update_hud(self, dt):
        o = self.order
        self.info.text = f"Деньги: ${self.money}    Доставлено: {self.delivered}    Кости: {self.bones}"

        h = self.houses[o.house_index]
        dist = int(distance_xz(self.player.position, h.door_pos))
        side = "справа" if h.side > 0 else "слева"
        if self.carrying:
            left = o.time_limit - o.elapsed
            timer = f"{int(left // 60)}:{int(left % 60):02d}" if left >= 0 else f"просрочено +{int(-left)} с"
            self.order_text.text = f"Дом №{o.number} ({side}), {dist} м   Время: {timer}"
        else:
            self.order_text.text = f"Следующий заказ: {o.cargo_name}, дом №{o.number} ({side})"

        if self.carrying:
            frac = o.integrity / logic.MAX_INTEGRITY
            self.bar_bg.enabled = self.bar.enabled = True
            self.bar.scale_x = max(0.001, 0.5 * frac)
            if self.flash > 0:
                self.bar.color = color.red
            else:
                self.bar.color = color.lime if frac > 0.6 else (color.yellow if frac > 0.3 else color.orange)
            self.bar_text.text = f"Целостность груза: {int(o.integrity)}%"
        else:
            self.bar_bg.enabled = self.bar.enabled = False
            self.bar_text.text = ""
        self.flash = max(0.0, self.flash - dt)

        if self.carrying and self.near_door():
            self.hint.text = "E — вручить груз"
        elif self.near_van():
            self.hint.text = "E — пополнить кости" if self.carrying else f"E — взять груз ({o.cargo_name})"
        else:
            self.hint.text = ""

        if self.msg_t > 0:
            self.msg_t -= dt
            if self.msg_t <= 0:
                self.msg.text = ""
