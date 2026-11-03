"""Запуск: python main.py   (флаг --lit включает освещение)"""
import sys

from ursina import Ursina, Sky, Entity, Color, DirectionalLight, AmbientLight, Vec3, scene, color, window

from game.game import Game

app = Ursina(title="Доставка", borderless=False)
window.exit_button.visible = False
window.fps_counter.enabled = True

Sky()
scene.fog_color = color.hex("#b8d4e8")
scene.fog_density = (40, 130)

if "--lit" in sys.argv:
    try:
        from ursina.shaders import lit_with_shadows_shader
        Entity.default_shader = lit_with_shadows_shader
        sun = DirectionalLight()
        sun.look_at(Vec3(1, -1.5, 0.6))
        AmbientLight(color=Color(0.55, 0.55, 0.6, 1))
    except Exception as exc:  # шейдеры зависят от видеокарты
        print("Освещение недоступно:", exc)

game = Game()

if __name__ == "__main__":
    app.run()
