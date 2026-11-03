"""Экран планирования маршрута: карта улицы сверху, клики по домам задают порядок объезда."""
from __future__ import annotations

from ursina import Button, Color, Entity, Mesh, Text, Vec2, Vec3, camera, color, destroy, mouse

from . import logic
from .world import Z_MAX, Z_MIN

MAP_CX = -0.5
MAP_Y0, MAP_Y1 = -0.36, 0.38


def map_y(z: float) -> float:
    return MAP_Y0 + (z - Z_MIN) / (Z_MAX - Z_MIN) * (MAP_Y1 - MAP_Y0)


class Planner(Entity):
    def __init__(self, game):
        super().__init__(parent=camera.ui, enabled=False)
        self.game = game
        self.stops: list[int] = []
        self.route: list[int] = []
        self.line = None
        self.on_confirm = None
        self.on_cancel = None
        self._saved_sens = None

    # ------------------------------------------------------------ открыть/закрыть
    def open(self, stops, on_confirm, on_cancel):
        self.stops = list(stops)
        self.route = []
        self.on_confirm = on_confirm
        self.on_cancel = on_cancel
        self._clear()
        self._build()
        self.enabled = True
        self._saved_sens = self.game.player.mouse_sensitivity
        self.game.player.mouse_sensitivity = Vec2(0, 0)
        mouse.locked = False
        mouse.visible = True
        self.refresh()

    def close(self):
        self.enabled = False
        self.game.player.mouse_sensitivity = self._saved_sens or Vec2(40, 40)
        mouse.locked = True

    def _clear(self):
        for c in list(self.children):
            destroy(c)
        self.line = None

    # ------------------------------------------------------------------- UI
    def _build(self):
        g = self.game
        Entity(parent=self, model="quad", color=Color(0.04, 0.05, 0.08, 0.93),
               scale=(1.75, 0.95), z=1)
        Text(parent=self, text="Планирование маршрута: нажимай дома в том порядке, в каком поедешь",
             origin=(-0.5, 0.5), position=(-0.82, 0.45), scale=1.1)
        # улица
        Entity(parent=self, model="quad", color=color.hex("#555a63"),
               scale=(0.07, MAP_Y1 - MAP_Y0 + 0.04), position=(MAP_CX, (MAP_Y0 + MAP_Y1) / 2), z=0.5)
        vy = map_y(g.van.z)
        Entity(parent=self, model="quad", color=color.white, scale=(0.05, 0.03),
               position=(MAP_CX, vy), z=-0.02)
        Text(parent=self, text="фургон", origin=(0, 0), position=(MAP_CX, vy - 0.035), scale=0.7)

        self.buttons = {}
        self.order_labels = {}
        for i in self.stops:
            h = g.houses[i]
            x = MAP_CX + h.side * 0.17
            y = map_y(h.z)
            b = Button(parent=self, text=f"{h.number}", position=(x, y), scale=(0.1, 0.06),
                       color=color.hex(h.color_hex), text_color=color.black)
            b.on_click = lambda i=i: self.pick(i)
            self.buttons[i] = b
            lab = Text(parent=self, text="", origin=(0, 0),
                       position=(x + h.side * 0.085, y), scale=1.3, color=color.yellow)
            self.order_labels[i] = lab

        self.route_text = Text(parent=self, text="", origin=(-0.5, 0.5), position=(-0.05, 0.36), scale=1.0)
        self.stats_text = Text(parent=self, text="", origin=(-0.5, 0.5), position=(-0.05, 0.02), scale=1.0)
        self.bay_text = Text(parent=self, text="", origin=(-0.5, 0.5), position=(-0.05, -0.16), scale=0.9)

        reset = Button(parent=self, text="Сбросить", position=(0.2, -0.39), scale=(0.2, 0.05))
        reset.on_click = self.reset
        self.go_btn = Button(parent=self, text="Поехали (Enter)", position=(0.5, -0.39), scale=(0.28, 0.05),
                             color=color.hex("#2e7d32"))
        self.go_btn.on_click = self.confirm
        Text(parent=self, text="Backspace: убрать последний   Esc: отмена", origin=(-0.5, 0.5),
             position=(-0.05, -0.31), scale=0.8, color=color.light_gray)

    # ------------------------------------------------------------- действия
    def pick(self, i):
        if i in self.route or i not in self.stops:
            return
        self.route.append(i)
        self.refresh()

    def reset(self):
        self.route = []
        self.refresh()

    def undo(self):
        if self.route:
            self.route.pop()
            self.refresh()

    def complete(self) -> bool:
        return len(self.route) == len(self.stops) and bool(self.stops)

    def confirm(self):
        if not self.complete():
            return
        route = list(self.route)
        self.close()
        if self.on_confirm:
            self.on_confirm(route)

    def cancel(self):
        self.close()
        if self.on_cancel:
            self.on_cancel()

    def input(self, key):
        if not self.enabled:
            return
        if key == "enter":
            self.confirm()
        elif key == "backspace":
            self.undo()
        elif key == "escape":
            self.cancel()

    # ------------------------------------------------------------ обновление
    def refresh(self):
        g = self.game
        for i, b in self.buttons.items():
            used = i in self.route
            b.alpha = 0.35 if used else 1.0
            self.order_labels[i].text = str(self.route.index(i) + 1) if used else ""

        lines = ["Маршрут:"]
        for n, i in enumerate(self.route, 1):
            lines.append(f"  {n}. дом {g.houses[i].label}")
        self.route_text.text = "\n".join(lines)

        if self.line:
            destroy(self.line)
            self.line = None
        if self.route:
            pts = [Vec3(MAP_CX, map_y(g.van.z), -0.03)]
            for i in self.route:
                h = g.houses[i]
                pts.append(Vec3(MAP_CX + h.side * 0.17, map_y(h.z), -0.03))
            self.line = Entity(parent=self, model=Mesh(vertices=pts, mode="line", thickness=4),
                               color=color.yellow)

        if self.complete():
            zs = [g.houses[i].z for i in self.route]
            length = logic.route_length(zs, g.van.z)
            digs = logic.dig_estimate(self.route, g.bay.lanes, g.house_of)
            obstacles = sum(len(g.houses[i].obstacles) for i in self.route)
            limit = logic.route_time_limit(length, len(self.route), obstacles)
            self.stats_text.text = (f"Длина пути: {int(length)} м\n"
                                    f"Время на маршрут: {limit // 60}:{limit % 60:02d}\n"
                                    f"Придётся вынимать мешающие посылки: {digs} шт.")
            self.go_btn.color = color.hex("#2e7d32")
        else:
            left = len(self.stops) - len(self.route)
            self.stats_text.text = f"Выбери ещё домов: {left}"
            self.go_btn.color = color.hex("#555555")

        self.bay_text.text = "В фургоне (сначала у двери, потом вглубь):\n" + g.bay_description()
