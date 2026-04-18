"""家具交互区域数据库

定义每个 Poly Haven 模型的交互区域（sit_area, surface_z, reach_area 等）。
用于 spatial_solver 将角色精确放置到家具的正确位置。

数据来源：实际 Blender 测量 + Poly Haven 模型文档。
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class InteractionZone:
    """家具的交互区域定义"""
    # 座面/使用面的 3D 范围
    z_min: float = 0.0          # 表面最低 z
    z_max: float = 0.0          # 表面最高 z
    y_min: float = 0.0          # 前后范围
    y_max: float = 0.0
    x_min: float = 0.0          # 左右范围
    x_max: float = 0.0

    # 物理属性
    backrest_z: float = 0.0     # 靠背顶部 z（用于坐姿上身参考）
    armrest_height: float = 0.0  # 扶手高度 z
    clearance_default: float = 0.05  # 默认 clearance（米）

    # 支撑类型
    support_type: str = "sit"   # sit / stand / lean / surface


@dataclass
class FurnitureDef:
    """家具完整定义"""
    name: str
    display_name: str
    blend_path: str             # D:\BlenderAgent\assets\polyhaven\models\...\xxx_2k.blend
    components: List[str] = field(default_factory=list)  # 子 mesh 名称关键词
    category: str = "furniture"  # furniture / lighting / plant / prop
    interaction: InteractionZone = field(default_factory=InteractionZone)

    def get_seat_center(self) -> Tuple[float, float, float]:
        """返回座面中心坐标 (x, y, z)"""
        iz = (self.interaction.z_min + self.interaction.z_max) / 2
        iy = (self.interaction.y_min + self.interaction.y_max) / 2
        ix = (self.interaction.x_min + self.interaction.x_max) / 2
        return (ix, iy, iz)


# ══════════════════════════════════════════════════════════════
# 家具数据库（基于实际 Blender 测量数据）
# ══════════════════════════════════════════════════════════════

FURNITURE_DB: Dict[str, FurnitureDef] = {
    # ── 沙发 ──────────────────────────────────────────────────────
    "sofa_02": FurnitureDef(
        name="sofa_02",
        display_name="Sofa",
        blend_path=r"D:\BlenderAgent\assets\polyhaven\models\sofa_02\sofa_02_2k.blend",
        components=["sofa_02_Base", "sofa_02_Seat"],
        category="furniture",
        interaction=InteractionZone(
            z_min=0.71, z_max=0.87,   # Seat 放在 Base 顶部后: 0.71 + 0.16
            y_min=-0.31, y_max=0.22,
            x_min=-0.85, x_max=0.85,
            backrest_z=1.10,
            armrest_height=0.85,
            clearance_default=0.05,
            support_type="sit",
        ),
    ),

    # ── 电视 ──────────────────────────────────────────────────────
    "Television_01": FurnitureDef(
        name="Television_01",
        display_name="Television",
        blend_path=r"D:\BlenderAgent\assets\polyhaven\models\Television_01\Television_01_2k.blend",
        components=["Television_01"],
        category="electronics",
        interaction=InteractionZone(
            z_min=0.0, z_max=0.46,
            y_min=-0.75, y_max=-0.20,
            x_min=-2.34, x_max=-1.67,
            backrest_z=0.46,
            clearance_default=0.02,
            support_type="surface",
        ),
    ),

    # ── 盆栽 ──────────────────────────────────────────────────────
    "potted_plant_04": FurnitureDef(
        name="potted_plant_04",
        display_name="Potted Plant",
        blend_path=r"D:\BlenderAgent\assets\polyhaven\models\potted_plant_04\potted_plant_04_2k.blend",
        components=["potted_plant_04_pot", "potted_plant_04_plant", "potted_plant_04_ground", "potted_plant_04_dirt"],
        category="plant",
        interaction=InteractionZone(
            z_min=0.0, z_max=0.16,   # 花盆高度
            y_min=0.71, y_max=0.89,
            x_min=1.11, x_max=1.29,
            backrest_z=0.27,
            clearance_default=0.01,
            support_type="surface",
        ),
    ),

    # ── 灯笼 ──────────────────────────────────────────────────────
    "Lantern_01": FurnitureDef(
        name="Lantern_01",
        display_name="Lantern",
        blend_path=r"D:\BlenderAgent\assets\polyhaven\models\Lantern_01\Lantern_01_2k.blend",
        components=["Lantern_01", "Lantern_01_glass"],
        category="lighting",
        interaction=InteractionZone(
            z_min=0.0, z_max=0.29,
            y_min=-0.85, y_max=-0.75,
            x_min=1.44, x_max=1.56,
            backrest_z=0.29,
            clearance_default=0.01,
            support_type="surface",
        ),
    ),

    # ── 书本装饰 ──────────────────────────────────────────────────
    "decorative_book_set_01": FurnitureDef(
        name="decorative_book_set_01",
        display_name="Book Set",
        blend_path=r"D:\BlenderAgent\assets\polyhaven\models\decorative_book_set_01\decorative_book_set_01_2k.blend",
        components=["decorative_book_set_01"],
        category="prop",
        interaction=InteractionZone(
            z_min=0.60, z_max=0.69,  # 书本堆叠高度
            y_min=-0.35, y_max=-0.25,
            x_min=-0.81, x_max=-0.79,
            backrest_z=0.69,
            clearance_default=0.01,
            support_type="surface",
        ),
    ),

    # ── 大理石半身像 ──────────────────────────────────────────────
    "marble_bust_01": FurnitureDef(
        name="marble_bust_01",
        display_name="Marble Bust",
        blend_path=r"D:\BlenderAgent\assets\polyhaven\models\marble_bust_01\marble_bust_01_2k.blend",
        components=["marble_bust_01"],
        category="decorative",
        interaction=InteractionZone(
            z_min=0.0, z_max=0.60,
            y_min=-0.15, y_max=0.15,
            x_min=-0.25, x_max=0.25,
            backrest_z=0.60,
            clearance_default=0.01,
            support_type="surface",
        ),
    ),

    # ── 植物：蕨类 ──────────────────────────────────────────────────
    "fern_02": FurnitureDef(
        name="fern_02",
        display_name="Fern",
        blend_path=r"D:\BlenderAgent\assets\polyhaven\models\fern_02\fern_02_2k.blend",
        components=["fern_02"],
        category="plant",
        interaction=InteractionZone(
            z_min=0.0, z_max=0.30,
            y_min=0.0, y_max=0.0,
            x_min=0.0, x_max=0.0,
            clearance_default=0.01,
            support_type="surface",
        ),
    ),
}


def get_furniture(name: str) -> Optional[FurnitureDef]:
    """按名称查找家具定义"""
    return FURNITURE_DB.get(name)


def list_furniture(category: str = "") -> List[FurnitureDef]:
    """列出所有家具，可按类别过滤"""
    items = list(FURNITURE_DB.values())
    if category:
        items = [f for f in items if f.category == category]
    return items


def get_suitable_furniture(contact_type: str) -> List[FurnitureDef]:
    """根据接触类型推荐合适的家具"""
    suitable = {
        "sit": ["sofa_02"],
        "ground": [],  # 地面不需要家具
        "surface": ["Television_01", "decorative_book_set_01", "marble_bust_01"],
    }
    names = suitable.get(contact_type, [])
    return [FURNITURE_DB[n] for n in names if n in FURNITURE_DB]
