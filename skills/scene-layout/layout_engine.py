"""场景布局引擎 — 主入口

编排所有子模块，将场景描述转化为可执行的 Blender 脚本。
灵感来源：INFERACT (SIGGRAPH 2024) + SceneCraft (2024) + AnimateScene (2025)
"""

from typing import Dict, List, Optional
from dataclasses import dataclass, field

from furniture_db import FURNITURE_DB, get_furniture, FurnitureDef
from contact_analyzer import AnimationContactMap, analyze_animation_bones
from spatial_solver import AABB, aabb_overlap, compute_placement_offset
from camera_director import CameraRig, SubjectInfo, SHOT_PRESETS, generate_multi_shot_script
from generators.scene_script import SceneRequest, generate_full_scene_script


@dataclass
class LayoutResult:
    """布局结果"""
    success: bool
    blender_script: str
    warnings: List[str] = field(default_factory=list)
    contact_analysis: Optional[AnimationContactMap] = None


class SceneComposer:
    """场景布局编排器"""
    
    def __init__(self, base_scene: str = r"D:\BlenderAgent\cache\full_scene.blend"):
        self.base_scene = base_scene
        self._contact_cache: Dict[str, AnimationContactMap] = {}
    
    def compose(
        self,
        characters: List[Dict] = None,
        furniture: List[str] = None,
        hdri: str = "",
        camera_shots: List[str] = None,
        output_dir: str = r"D:\BlenderAgent\outputs",
        dialogue_mode: bool = False,
    ) -> LayoutResult:
        """
        编排完整场景
        
        Args:
            characters: [{"animation": "sitting_while_laughing", "position": "on:sofa"}]
            furniture: ["sofa_02", "Television_01", ...]
            hdri: HDRI 文件名
            camera_shots: ["wide", "medium", "closeup"]
            output_dir: 输出目录
            dialogue_mode: 双人对话模式（180° 轴线）
        """
        warnings = []
        
        if characters is None:
            characters = []
        if furniture is None:
            furniture = []
        if camera_shots is None:
            camera_shots = ["wide", "medium", "closeup"]
        
        # 验证家具
        for fname in furniture:
            fdef = get_furniture(fname)
            if not fdef:
                warnings.append(f"Furniture '{fname}' not in database, will use default placement")
        
        # 验证动画
        for char in characters:
            anim = char.get("animation", "")
            target = char.get("position", "")
            if target.startswith("on:") and target[3:] not in FURNITURE_DB:
                warnings.append(f"Target furniture '{target[3:]}' not in database")
        
        # 构建 SceneRequest
        request = SceneRequest(
            characters=characters,
            furniture=furniture,
            hdri=hdri,
            camera_shots=camera_shots,
            output_dir=output_dir,
        )
        
        # 生成脚本
        script = generate_full_scene_script(request)
        
        return LayoutResult(
            success=True,
            blender_script=script,
            warnings=warnings,
        )
    
    def compose_living_room(
        self,
        character_animation: str = r"D:\BlenderAgent\animations\motions\sitting_while_laughing_inplace_withskin.fbx",
        position: str = "on:sofa",
        hdri: str = "studio_small_03_4k",
    ) -> LayoutResult:
        """
        快速生成客厅场景
        
        预设：沙发 + 电视 + 盆栽 + 灯笼
        """
        return self.compose(
            characters=[{
                "animation": character_animation,
                "position": position,
                "clearance": 0.05,
            }],
            furniture=["sofa_02", "Television_01", "potted_plant_04", "Lantern_01"],
            hdri=hdri,
        )
    
    def compose_dialogue(
        self,
        character_a_anim: str,
        character_b_anim: str,
        furniture_a: str = "on:sofa",
        furniture_b: str = "",
    ) -> LayoutResult:
        """
        生成双人对话场景（180° 轴线）
        """
        return self.compose(
            characters=[
                {"animation": character_a_anim, "position": furniture_a},
                {"animation": character_b_anim, "position": furniture_b},
            ],
            camera_shots=["wide", "otw_over_shoulder", "closeup"],
            dialogue_mode=True,
        )
