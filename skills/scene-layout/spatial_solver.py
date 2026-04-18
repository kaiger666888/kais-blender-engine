"""空间求解器

AABB 碰撞检测 + 物理约束放置。
确保角色放置在表面上时不与场景物体相交。"""

import math
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field


@dataclass
class AABB:
    """轴对齐包围盒"""
    x_min: float
    y_min: float
    z_min: float
    x_max: float
    y_max: float
    z_max: float
    
    @property
    def size(self) -> Tuple[float, float, float]:
        return (self.x_max - self.x_min, self.y_max - self.y_min, self.z_max - self.z_min)
    
    @property
    def center(self) -> Tuple[float, float, float]:
        return (
            (self.x_min + self.x_max) / 2,
            (self.y_min + self.y_max) / 2,
            (self.z_min + self.z_max) / 2,
        )
    
    @property
    def top_z(self) -> float:
        return self.z_max
    
    @property
    def bottom_z(self) -> float:
        return self.z_min
    
    @property
    def height(self) -> float:
        return self.z_max - self.z_min


def aabb_overlap(a: AABB, b: AABB, margin: float = 0.0) -> bool:
    """检测两个 AABB 是否重叠（可设 margin）"""
    overlap = (
        a.x_min - margin < b.x_max and a.x_max + margin > b.x_min and
        a.y_min - margin < b.y_max and a.y_max + margin > b.y_min and
        a.z_min - margin < b.z_max and a.z_max + margin > b.z_min
    )
    return overlap


def aabb_overlap_volume(a: AABB, b: AABB, margin: float = 0.0) -> float:
    """计算重叠体积（近似）"""
    if not aabb_overlap(a, b, margin):
        return 0.0
    ox = max(0, min(a.x_max, b.x_max) - max(a.x_min, b.x_min) + margin * 2)
    oy = max(0, min(a.y_max, b.y_max) - max(a.y_min, b.y_min)) + margin * 2
    oz = max(0, min(a.z_max, b.z_max) - max(a.z_min, b.z_min)) + margin * 2
    return ox * oy * oz


def check_penetration(
    char_aabb: AABB,
    obstacle_aabbs: List[AABB],
    margin: float = 0.02,
) -> List[Dict]:
    """
    检测角色与障碍物的穿透情况
    
    Returns:
        [{"obstacle": str, "overlap_volume": float, "direction": str}]
    """
    penetrations = []
    for obs in obstacle_aabbs:
        vol = aabb_overlap_volume(char_aabb, obs, margin)
        if vol > 0.001:
            # 判断穿透方向
            dx = (obs.center[0] - char_aabb.center[0])
            dy = (obs.center[1] - char_aabb.center[1])
            dz = (obs.center[2] - char_aabb.center[2])
            max_d = max(abs(dx), abs(dy), abs(dz))
            if abs(dx) == max_d:
                direction = "x"
            elif abs(dy) == max_d:
                direction = "y"
            else:
                direction = "z"
            penetrations.append({
                "overlap_volume": round(vol, 4),
                "direction": direction,
                "delta": round(max_d, 4),
            })
    return penetrations


def compute_placement_offset(
    char_contact_z: float,
    target_surface_z: float,
    char_aabb: AABB,
    obstacle_aabbs: List[AABB],
    clearance: float = 0.05,
    penetration_threshold: float = 0.001,
) -> Tuple[float, float, List[Dict]]:
    """
    计算角色放置偏移量，确保：
    1. 接触点 z = surface_z + clearance
    2. 不与障碍物穿透
    
    Returns: (delta_z, delta_y, penetration_list)
    """
    # 基础偏移：接触点对齐表面
    delta_z = target_surface_z + clearance - char_contact_z
    
    # 临时应用偏移，检查穿透
    test_aabb = AABB(
        x_min=char_aabb.x_min, x_max=char_aabb.x_max,
        y_min=char_aabb.y_min, y_max=char_aabb.y_max,
        z_min=char_aabb.z_min + delta_z, z_max=char_aabb.z_max + delta_z,
    )
    
    penetrations = check_penetration(test_aabb, obstacle_aabbs, margin=clearance)
    
    return delta_z, 0.0, penetrations


def resolve_penetration(
    delta_z: float,
    char_aabb: AABB,
    penetrations: List[Dict],
    clearance: float = 0.05,
    max_iterations: int = 20,
    step: float = 0.02,
) -> Tuple[float, bool]:
    """
    通过迭代调整解决穿透问题
    
    Returns: (final_delta_z, resolved)
    """
    current_dz = delta_z
    
    for i in range(max_iterations):
        test_aabb = AABB(
            x_min=char_aabb.x_min, x_max=char_aabb.x_max,
            y_min=char_aabb.y_min, y_max=char_aabb.y_max,
            z_min=char_aabb.z_min + current_dz,
            z_max=char_aabb.z_max + current_dz,
        )
        
        # 检查是否还有穿透
        has_penetration = False
        for p in penetrations:
            vol = aabb_overlap_volume(test_aabb, p.get("_aabb", test_aabb), clearance)
            if vol > penetration_threshold:
                has_penetration = True
                break
        
        if not has_penetration:
            return current_dz, True
        
        # 向上调整
        current_dz += step
    
    return current_dz, False


def find_safe_y_position(
    char_aabb: AABB,
    obstacle_aabbs: List[AABB],
    target_y: float,
    margin: float = 0.05,
) -> float:
    """在 x-z 平面上找到不碰撞的 y 位置"""
    # 检查目标 y 是否碰撞
    test_aabb = AABB(
        x_min=char_aabb.x_min - margin, x_max=char_aabb.x_max + margin,
        y_min=char_aabb.y_min, y_max=char_aabb.y_max,
        z_min=char_aabb.z_min, z_max=char_aabb.z_max,
    )
    test_aabb.y_min = target_y - margin
    test_aabb.y_max = target_y + margin
    
    for obs in obstacle_aabbs:
        if aabb_overlap(test_aabb, obs):
            # 向前后搜索安全位置
            for dy in [0.1, -0.1, 0.2, -0.2, 0.3, -0.3, 0.5, -0.5]:
                test_aabb.y_min = target_y + dy - margin
                test_aabb.y_max = target_y + dy + margin
                safe = True
                for obs2 in obstacle_aabbs:
                    if aabb_overlap(test_aabb, obs2):
                        safe = False
                        break
                if safe:
                    return target_y + dy
    
    return target_y  # fallback
