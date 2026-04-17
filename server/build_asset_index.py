"""
MPFB2 素材索引生成器

扫描 MPFB2 packs JSON + 数据目录，合并元数据，提取语义标签，输出统一索引。
用法: python build_asset_index.py
"""
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from config import ASSET_INDEX_PATH, MPFB_DATA_DIR

# 素材类型 → 数据子目录名 映射
ASSET_TYPES = {
    "skins": "skins",
    "hair": "hair",
    "clothes": "clothes",
    "eyes": "eyes",
    "eyebrows": "eyebrows",
    "eyelashes": "eyelashes",
    "teeth": "teeth",
    "tongue": "tongue",
    "poses": "poses",
    "proxymeshes": "proxymeshes",
}

# MPFB2 pack JSON 中 type 字段到我们索引类型的映射
PACK_TYPE_MAP = {
    "skin": "skins",
    "hair": "hair",
    "clothes": "clothes",
    "eyes": "eyes",
    "eyebrows": "eyebrows",
    "eyelashes": "eyelashes",
    "teeth": "teeth",
    "tongue": "tongue",
    "pose": "poses",
    "proxy": "proxymeshes",
    "proxymeshes": "proxymeshes",
}

# 标签提取关键词 → 标签值
TAG_PATTERNS = [
    # gender
    (r"\bfemale\b", "female"),
    (r"\bmale\b", "male"),
    # age
    (r"\byoung\b", "young"),
    (r"\bmiddleage\b", "middleage"),
    (r"\bold\b", "old"),
    (r"\bteen\b", "teen"),
    # ethnicity
    (r"\bafrican\b", "african"),
    (r"\basian\b", "asian"),
    (r"\bcaucasian\b", "caucasian"),
    (r"\bindian\b", "indian"),
    (r"\beurasian\b", "eurasian"),
    (r"\blatin\b", "latin"),
    # hair style
    (r"\bafro\b", "afro"),
    (r"\bbob\b", "bob"),
    (r"\bbrai[dt]\b", "braid"),
    (r"\bcurly\b", "curly"),
    (r"\blong\b", "long"),
    (r"\bponytail\b", "ponytail"),
    (r"\bshort\b", "short"),
    (r"\bstraight\b", "straight"),
    (r"\bwavy\b", "wavy"),
    (r"\bun[t]?ied\b", "untied"),
    (r"\bbun\b", "bun"),
    (r"\bfringe\b", "fringe"),
    (r"\bbangs?\b", "bangs"),
    # clothing type
    (r"\bdress\b", "dress"),
    (r"\bshirt\b", "shirt"),
    (r"\bpants?\b", "pants"),
    (r"\bskirt\b", "skirt"),
    (r"\bsuit\b", "suit"),
    (r"\bshoes?\b", "shoes"),
    (r"\bboot[s]?\b", "boots"),
    (r"\bunderwear\b", "underwear"),
    (r"\bbra\b", "bra"),
    (r"\bpantie[s]?\b", "panties"),
    (r"\bbikini\b", "bikini"),
    (r"\bgloves?\b", "gloves"),
    (r"\bhat\b", "hat"),
    (r"\bhelmet\b", "helmet"),
    (r"\bmask\b", "mask"),
    (r"\bglasses\b", "glasses"),
    (r"\bgoggle\b", "goggles"),
    (r"\bsock[s]?\b", "socks"),
    (r"\bstocking[s]?\b", "stockings"),
    (r"\bcape?\b", "cape"),
    (r"\brobe\b", "robe"),
    (r"\bjacket\b", "jacket"),
    (r"\bcoat\b", "coat"),
    (r"\btank\b", "tank_top"),
    (r"\bsweater\b", "sweater"),
    (r"\bhood\b", "hood"),
    # body parts
    (r"\bhorn[s]?\b", "horns"),
    (r"\btail[s]?\b", "tails"),
    (r"\bwing[s]?\b", "wings"),
    (r"\bbeard\b", "beard"),
    (r"\bmoustache\b", "moustache"),
    (r"\bnail[s]?\b", "nails"),
    (r"\bantler[s]?\b", "antlers"),
    # misc
    (r"\bcasual\b", "casual"),
    (r"\belegant\b", "elegant"),
    (r"\bsport[s]?\b", "sport"),
    (r"\bformal\b", "formal"),
    (r"\bfantasy\b", "fantasy"),
    (r"\bsci-?fi\b", "scifi"),
    (r"\bmedieval\b", "medieval"),
    (r"\btattoo\b", "tattoo"),
    (r"\bgenitals?\b", "genitals"),
    (r"\bspecial_suit\b", "special_suit"),
]


def extract_tags(name: str, description: str = "") -> list[str]:
    """从素材名称和描述中提取语义标签"""
    text = f"{name} {description}".lower().replace("_", " ")
    tags = []
    for pattern, tag in TAG_PATTERNS:
        if re.search(pattern, text) and tag not in tags:
            tags.append(tag)
    return tags


def resolve_type(pack_type: str) -> str | None:
    """将 pack JSON 中的 type 字段映射到索引类型"""
    return PACK_TYPE_MAP.get(pack_type)


def scan_data_dirs() -> dict[str, set[str]]:
    """扫描 MPFB2 数据目录，返回每个类型下实际存在的素材名称"""
    found = {}
    for type_name, subdir in ASSET_TYPES.items():
        type_dir = MPFB_DATA_DIR / subdir
        names = set()
        if type_dir.is_dir():
            for item in sorted(type_dir.iterdir()):
                if item.is_dir():
                    names.add(item.name)
        found[type_name] = names
    return found


def load_pack_metadata() -> dict[str, dict]:
    """加载所有 pack JSON 文件，返回 {asset_name: {meta fields...}}"""
    packs_dir = MPFB_DATA_DIR / "packs"
    if not packs_dir.is_dir():
        return {}

    merged = {}
    for pack_file in sorted(packs_dir.glob("*.json")):
        pack_name = pack_file.stem
        try:
            with open(pack_file, "r", encoding="utf-8") as f:
                pack_data = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue

        for asset_name, meta in pack_data.items():
            if asset_name in merged:
                # 保留更详细的描述
                existing_desc = merged[asset_name].get("description", "")
                new_desc = meta.get("description", "")
                if len(new_desc) > len(existing_desc):
                    merged[asset_name]["description"] = new_desc
            else:
                merged[asset_name] = {
                    "author": meta.get("author", ""),
                    "description": meta.get("description", ""),
                    "license": meta.get("license", ""),
                    "pack": pack_name,
                    "pack_type": meta.get("type", ""),
                    "source": meta.get("source", ""),
                    "thumbnail": meta.get("thumbnail", ""),
                }
    return merged


def build_index() -> dict:
    """构建完整素材索引"""
    pack_meta = load_pack_metadata()
    disk_assets = scan_data_dirs()

    assets_by_type = {t: [] for t in ASSET_TYPES}

    for type_name, names_on_disk in disk_assets.items():
        for name in sorted(names_on_disk):
            meta = pack_meta.get(name, {})
            # 尝试从 pack_type 推断索引类型（pack 的 type 可能与目录不同）
            pack_resolved = resolve_type(meta.get("pack_type", "")) if meta else None

            entry = {
                "name": name,
                "author": meta.get("author", ""),
                "description": meta.get("description", ""),
                "license": meta.get("license", ""),
                "tags": extract_tags(name, meta.get("description", "")),
            }
            if meta.get("pack"):
                entry["pack"] = meta["pack"]
            if meta.get("thumbnail"):
                entry["thumbnail"] = meta["thumbnail"]

            assets_by_type[type_name].append(entry)

    # 统计
    stats = {t: len(items) for t, items in assets_by_type.items()}

    # 也统计 pack 中有但磁盘上没有的（不应出现，但记录一下）
    orphan_count = 0
    for asset_name, meta in pack_meta.items():
        resolved = resolve_type(meta.get("pack_type", ""))
        if resolved and resolved in disk_assets:
            if asset_name not in disk_assets[resolved]:
                orphan_count += 1

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mpfb_data_dir": str(MPFB_DATA_DIR),
        "stats": stats,
        "total_assets": sum(stats.values()),
        "orphan_pack_entries": orphan_count,
        "assets": assets_by_type,
    }


def main():
    if not MPFB_DATA_DIR.is_dir():
        print(f"ERROR: MPFB data directory not found: {MPFB_DATA_DIR}")
        return 1

    print(f"Scanning MPFB2 assets from: {MPFB_DATA_DIR}")
    index = build_index()

    with open(ASSET_INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

    print(f"Index written to: {ASSET_INDEX_PATH}")
    print(f"Total assets: {index['total_assets']}")
    for type_name, count in index["stats"].items():
        print(f"  {type_name}: {count}")

    # 打印几个标签示例
    for type_name in ["skins", "hair"]:
        items = index["assets"].get(type_name, [])
        if items:
            sample = items[0]
            print(f"\n  Example ({type_name}): {sample['name']}")
            print(f"    tags: {sample['tags']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
