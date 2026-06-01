"""检查 Camoufox 是否可用。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:
    __import__("camoufox")
    __import__("camoufox.addons")
    print("Camoufox: ✅ 可用")
except ImportError as e:
    print(f"Camoufox: ❌ 不可用 — {e}")