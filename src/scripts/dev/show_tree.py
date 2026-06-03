"""Generate project tree for boss-job-hunter."""
from pathlib import Path

root = Path(__file__).resolve().parent.parent.parent
exclude_dirs = {".venv", "__pycache__", ".browser-data", "browser_profile",
                "sessions", "data", ".git", ".pytest_cache", "node_modules",
                ".github", ".mypy_cache", ".ruff_cache", ".gitattributes"}
exclude_files = {".pre-commit-config.yaml", ".gitignore"}

def build_tree(path, prefix=""):
    items = sorted(path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
    items = [i for i in items if i.name not in exclude_dirs and i.name[0] != "."]
    lines = []
    for i, item in enumerate(items):
        is_last = (i == len(items) - 1)
        node = "└── " if is_last else "├── "
        connector = "    " if is_last else "│   "
        if item.is_dir():
            lines.append(f"{prefix}{node}{item.name}/")
            lines.extend(build_tree(item, prefix + connector))
        elif item.suffix in (".py", ".md", ".yaml", ".yml", ".toml",
                             ".json", ".txt", ".bat", ".cfg", ".ini"):
            lines.append(f"{prefix}{node}{item.name}")
    return lines

print("boss-job-hunter/")
for line in build_tree(root):
    print(line)
