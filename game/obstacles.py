"""Препятствия у домов: собака и поливалка (узкий проход описан в world.py)."""
from __future__ import annotations

import math
import random

from ursina import Color, Entity, Vec3, color, distance_xz, time


def yaw_to(dx: float, dz: float) -> float:
    return math.degrees(math.atan2(dx, dz))


class Dog(Entity):
    WALK = 2.0
    CHASE = 5.8       # игрок идёт 5.0, а бежит 8.0
    NOTICE = 9.0      # дистанция, с которой собака замечает игрока
    EAT_TIME = 6.0

    game = None       # выставляется из Game

    def __init__(self, yard):
        """yard = (xmin, xmax, zmin, zmax) в мировых координатах."""
        xmin, xmax, zmin, zmax = yard
        super().__init__(position=Vec3((xmin + xmax) / 2, 0, (zmin + zmax) / 2))
        self.yard = yard
        brown = color.hex("#8a5a2b")
        light = color.hex("#a5703a")
        Entity(parent=self, model="cube", color=brown, scale=(0.45, 0.5, 1.0), y=0.6)
        self.head = Entity(parent=self, model="cube", color=light,
                           scale=(0.38, 0.38, 0.38), position=(0, 0.85, 0.62))
        Entity(parent=self.head, model="cube", color=color.black,
               scale=(0.5, 0.35, 0.45), position=(0, -0.1, 0.55))
        for sx in (-0.15, 0.15):
            Entity(parent=self, model="cube", color=brown,
                   scale=(0.1, 0.25, 0.1), position=(sx, 1.1, 0.55))
        Entity(parent=self, model="cube", color=brown,
               scale=(0.1, 0.1, 0.4), position=(0, 0.85, -0.65), rotation_x=-30)
        for lx in (-0.15, 0.15):
            for lz in (-0.35, 0.35):
                Entity(parent=self, model="cube", color=brown,
                       scale=(0.12, 0.4, 0.12), position=(lx, 0.2, lz))
        self.state = "patrol"
        self.timer = 0.0
        self.bite_cd = 0.0
        self.stun = 0.0
        self.target = self._random_point()

    # -- помощники
    def _random_point(self) -> Vec3:
        xmin, xmax, zmin, zmax = self.yard
        return Vec3(random.uniform(xmin, xmax), 0, random.uniform(zmin, zmax))

    def inside(self, p, margin: float = 0.5) -> bool:
        xmin, xmax, zmin, zmax = self.yard
        return (xmin - margin <= p.x <= xmax + margin) and (zmin - margin <= p.z <= zmax + margin)

    def _move_to(self, target, speed: float, dt: float) -> bool:
        dx, dz = target.x - self.x, target.z - self.z
        dist = math.hypot(dx, dz)
        if dist < 0.1:
            return True
        step = min(dist, speed * dt)
        self.x += dx / dist * step
        self.z += dz / dist * step
        self.rotation_y = yaw_to(dx, dz)
        xmin, xmax, zmin, zmax = self.yard
        self.x = max(xmin, min(xmax, self.x))
        self.z = max(zmin, min(zmax, self.z))
        return False

    def distract(self, pos) -> None:
        """Игрок бросил кость: собака бежит к ней и ест."""
        if not self.inside(pos, 1.0):
            return
        xmin, xmax, zmin, zmax = self.yard
        self.target = Vec3(max(xmin, min(xmax, pos.x)), 0, max(zmin, min(zmax, pos.z)))
        self.state = "fetch"

    # -- логика
    def update(self):
        if self.game is None:
            return
        dt = min(time.dt, 0.05)
        self.bite_cd = max(0.0, self.bite_cd - dt)

        if self.state == "eat":
            self.timer -= dt
            self.head.rotation_x = 25 + math.sin(self.timer * 10) * 12  # клюёт кость
            if self.timer <= 0:
                self.head.rotation_x = 0
                self.state = "patrol"
                self.target = self._random_point()
            return
        if self.state == "fetch":
            if self._move_to(self.target, self.CHASE, dt):
                self.state = "eat"
                self.timer = self.EAT_TIME
            return
        if self.stun > 0:
            self.stun -= dt
            return

        p = self.game.player.position
        d = distance_xz(self.position, p)
        in_yard = self.inside(p)
        if self.state != "chase" and in_yard and d < self.NOTICE:
            self.state = "chase"
            self.game.say("Гав! Собака заметила тебя! Брось кость (F)", 2.5)
        elif self.state == "chase" and (not in_yard or d > self.NOTICE + 5):
            self.state = "patrol"
            self.target = self._random_point()

        if self.state == "chase":
            self._move_to(p, self.CHASE, dt)
            if d < 1.4 and self.bite_cd <= 0:
                self.bite_cd = 2.5
                self.stun = 1.2
                self.game.on_dog_bite()
        else:
            if self._move_to(self.target, self.WALK, dt):
                self.target = self._random_point()


class Sprinkler(Entity):
    RADIUS = 2.8
    ON_TIME = 3.5
    OFF_TIME = 3.0

    def __init__(self, pos):
        super().__init__(position=Vec3(pos.x, 0, pos.z))
        Entity(parent=self, model="cube", color=color.gray, scale=(0.3, 0.25, 0.3), y=0.12)
        water = Color(0.45, 0.65, 1.0, 0.7)
        self.jet = Entity(parent=self, model="cube", color=water,
                          scale=(0.14, 1.8, 0.14), y=1.0)
        self.puddle = Entity(parent=self, model="cube",
                             color=Color(0.3, 0.5, 1.0, 0.35),
                             scale=(self.RADIUS * 2, 0.03, self.RADIUS * 2), y=0.04)
        self.t = random.uniform(0, self.ON_TIME + self.OFF_TIME)
        self.active = False

    def update(self):
        self.t = (self.t + time.dt) % (self.ON_TIME + self.OFF_TIME)
        self.active = self.t < self.ON_TIME
        self.jet.enabled = self.active
        self.puddle.enabled = self.active
        if self.active:
            self.jet.rotation_y += 400 * time.dt
            self.jet.scale_y = 1.6 + math.sin(self.t * 14) * 0.3

    def wets(self, p) -> bool:
        return self.active and distance_xz(self.position, p) < self.RADIUS
