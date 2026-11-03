"""Генерирует процедурные текстуры в assets/textures/. Запуск: python tools/make_textures.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from game.textures import generate_all  # noqa: E402

if __name__ == "__main__":
    generate_all(ROOT / "assets" / "textures")
    print("Готово:", ROOT / "assets" / "textures")
