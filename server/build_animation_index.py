"""扫描 Mixamo 动画资源目录，生成 animation_index.json"""

import json
from datetime import datetime
from pathlib import Path

from config import CHARACTERS_DIR, MOTIONS_DIR, ANIMATION_INDEX_PATH


def _scan_directory(directory: Path) -> list[dict]:
    """扫描目录中的 FBX 文件，返回元数据列表"""
    results = []
    if not directory.exists():
        return results
    for f in sorted(directory.glob("*.fbx")):
        stat = f.stat()
        results.append({
            "name": f.stem,
            "filename": f.name,
            "path": str(f),
            "size": stat.st_size,
            "modified": stat.st_mtime,
        })
    return results


def build_index() -> dict:
    """扫描动画资源目录，返回索引数据"""
    characters = _scan_directory(CHARACTERS_DIR)
    motions = _scan_directory(MOTIONS_DIR)

    index = {
        "generated_at": datetime.now().isoformat(),
        "characters": characters,
        "motions": motions,
        "stats": {
            "total_characters": len(characters),
            "total_motions": len(motions),
        },
    }

    with open(ANIMATION_INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)

    print(f"索引已生成: {len(characters)} 角色, {len(motions)} 动画")
    return index


if __name__ == "__main__":
    build_index()
