"""动画接触点分析器

从 Mixamo 动画 FBX 的骨骼 transform 中提取每帧的接触点，
推断角色的支撑类型（sit/stand/grasp）和需要的家具类型。

原理：Mixamo 动画将姿态 bake 在骨骼的世界坐标 transform 中，
通过分析每帧各骨骼的 z 坐标高度和位移变化，推断接触关系。
"""

import json
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field


@dataclass
class ContactPoint:
    """单帧接触点"""
    bone_name: str
    bone_world_z: float       # 骨骼世界 z 坐标
    bone_world_y: float       # 骨骼世界 y 坐标
    bone_world_x: float       # 骨骼世界 x 坐标
    contact_type: str         # support / ground / grasp / free
    object_hint: str          # 推断的家具类型（sofa / table / floor）


@dataclass
class ContactFrame:
    """单帧的所有接触点"""
    frame: int
    contacts: List[ContactPoint] = field(default_factory=list)
    primary_support_z: float = 0.0   # 主要支撑面 z 坐标
    primary_support_type: str = "ground"


@dataclass
class AnimationContactMap:
    """整个动画的接触分析结果"""
    animation_name: str
    total_frames: int
    contact_frames: List[ContactFrame] = field(default_factory=list)
    inferred_pose: str = "standing"   # standing / sitting / kneeling / lying
    primary_contact_bone: str = ""
    required_furniture: str = ""   # 推荐的家具类型


# ── Mixamo 骨骼分组 ──────────────────────────────────────────────

BONE_GROUPS = {
    "support": ["mixamorig:Hips"],
    "legs": [
        "mixamorig:LeftUpLeg", "mixamorig:RightUpLeg",
        "mixamorig:LeftLeg", "mixamorig:RightLeg",
        "mixamorig:LeftFoot", "mixamorig:RightFoot",
        "mixamorig:LeftToeBase", "mixamorig:RightToeBase",
    ],
    "torso": [
        "mixamorig:Spine", "mixamorig:Spine1", "mixamorig:Spine2",
        "mixamorig:Neck",
    ],
    "arms": [
        "mixamorig:LeftArm", "mixamorig:RightArm",
        "mixamorig:LeftForeArm", "mixamorig:RightForeArm",
        "mixamorig:LeftHand", "mixamorig:RightHand",
    ],
    "head": ["mixamorig:Head"],
}


def infer_contact_type(
    bone_name: str,
    bone_world_z: float,
    foot_z: float,
    hip_z: float,
    knee_z: float,
) -> Tuple[str, str]:
    """
    根据骨骼位置推断接触类型和家具提示
    
    Returns: (contact_type, object_hint)
    """
    if bone_name in BONE_GROUPS["legs"]:
        if bone_name in ("mixamorig:LeftFoot", "mixamorig:RightFoot",
                         "mixamorig:LeftToeBase", "mixamorig:RightToeBase"):
            if bone_world_z <= foot_z + 0.05:
                return ("ground", "floor")
        if bone_name in ("mixamorig:LeftKnee", "mixamorig:RightKnee"):
            if knee_z > hip_z * 0.7:
                return ("support", "chair")
            return ("support", "floor")
        if bone_name in ("mixamorig:LeftUpLeg", "mixamorig:RightUpLeg"):
            if bone_world_z > hip_z * 0.9:
                return ("support", "chair")  # 腿抬高 = 坐姿
            return ("free", "")
    
    if bone_name == "mixamorig:Hips":
        if hip_z < knee_z + 0.10:
            return ("support", "sofa")  # 臀部低于膝盖 = 坐姿
        return ("support", "floor")
    
    if bone_name in BONE_GROUPS["arms"]:
        if bone_name in ("mixamorig:LeftHand", "mixamorig:RightHand"):
            if bone_world_z > hip_z * 0.5:
                return ("grasp", "table")
        return ("free", "")
    
    return ("free", "")


def analyze_animation_bones(
    bone_data: Dict[str, Dict[int, Dict[str, float]]],
    animation_name: str = "",
) -> AnimationContactMap:
    """
    分析动画骨骼数据，推断接触点
    
    Args:
        bone_data: {bone_name: {frame: {"x": ..., "y": ..., "z": ...}}}
        animation_name: 动画名称
    
    Returns:
        AnimationContactMap 接触分析结果
    """
    if not bone_data:
        return AnimationContactMap(animation_name=animation_name, total_frames=0)
    
    frames = sorted(set(
        frame for bone in bone_data.values() for frame in bone.keys()
    ))
    total_frames = max(frames) if frames else 1
    
    # 提取关键骨骼位置
    hip_data = bone_data.get("mixamorig:Hips", {})
    foot_data = bone_data.get("mixamorig:RightFoot", bone_data.get("mixamorig:LeftFoot", {}))
    knee_data = bone_data.get("mixamorig:RightKnee", bone_data.get("mixamorig:LeftKnee", {}))
    
    result = AnimationContactMap(
        animation_name=animation_name,
        total_frames=total_frames,
    )
    
    for frame_idx in frames:
        frame_num = frame_idx
        
        # 获取该帧关键骨骼 z 坐标
        hip_z = hip_data.get(frame_num, {}).get("z", 1.0)
        foot_z = foot_data.get(frame_num, {}).get("z", 0.0)
        knee_z = knee_data.get(frame_num, {}).get("z", 0.5)
        
        contacts = []
        for bone_name, frames_data in bone_data.items():
            if frame_num not in frames_data:
                continue
            
            bz = frames_data[frame_num]["z"]
            by = frames_data[frame_num]["y"]
            bx = frames_data[frame_num]["x"]
            
            contact_type, hint = infer_contact_type(bone_name, bz, foot_z, hip_z, knee_z)
            
            if contact_type != "free":
                contacts.append(ContactPoint(
                    bone_name=bone_name,
                    bone_world_z=bz,
                    bone_world_y=by,
                    bone_world_x=bx,
                    contact_type=contact_type,
                    object_hint=hint,
                ))
        
        if contacts:
            frame = ContactFrame(frame=frame_num, contacts=contacts)
            # 找最低支撑点
            supports = [c for c in contacts if c.contact_type in ("support", "ground")]
            if supports:
                primary = min(supports, key=lambda c: c.bone_world_z)
                frame.primary_support_z = primary.bone_world_z
                frame.primary_support_type = primary.contact_type
            result.contact_frames.append(frame)
    
    # 推断整体姿态
    if result.contact_frames:
        mid_frame = result.contact_frames[len(result.contact_frames) // 2]
        if mid_frame:
            supports = [c for c in mid_frame.contacts if c.contact_type == "support"]
            if supports:
                lowest = min(supports, key=lambda c: c.bone_world_z)
                result.primary_contact_bone = lowest.bone_name
                if lowest.bone_world_z < 0.5:
                    result.inferred_pose = "lying"
                elif "sofa" in " ".join(c.object_hint for c in supports):
                    result.inferred_pose = "sitting"
                else:
                    result.inferred_pose = "kneeling"
    
    return result


def extract_contact_data_from_blender_script() -> str:
    """
    生成 Blender Python 脚本：导入动画 FBX 并提取所有骨骼的帧数据。
    输出 JSON 格式的 bone_data 供 analyze_animation_bones 使用。
    
    Returns:
        可发送到 /run/script 的 Python 脚本
    """
    script_lines = [
        "import bpy, json, sys",
        "",
        "# 导入动画 FBX",
        "existing = set(id(o) for o in bpy.context.scene.objects)",
        "bpy.ops.import_scene.fbx(filepath=r'ANIMATION_FBX_PATH', use_anim=True)",
        "",
        "arm = None",
        "for obj in bpy.context.scene.objects:",
        "    if obj.type == 'ARMATURE':",
        "        arm = obj",
        "        break",
        "",
        "if arm is None:",
        "    print('ERROR: No armature found')",
        "    sys.exit(1)",
        "",
        "# 收集所有帧",
        "act = arm.animation_data.action if arm.animation_data else None",
        "if act is None:",
        "    print('ERROR: No action')",
        "    sys.exit(1)",
        "",
        "f_start = int(act.frame_range[0])",
        "f_end = int(act.frame_range[1])",
        "bone_data = {}",
        "",
        "for frame in range(f_start, f_end + 1):",
        "    bpy.context.scene.frame_set(frame)",
        "    bpy.context.view_layer.update()",
        "    for pb in arm.pose.bones:",
        "        local = pb.bone.matrix_local.to_translation()",
        "        world = arm.matrix_world @ local",
        "        if pb.name not in bone_data:",
        "            bone_data[pb.name] = {}",
        "        bone_data[pb.name][frame] = {",
        "            'x': round(world.x, 4),",
        "            'y': round(world.y, 4),",
        "            'z': round(world.z, 4),",
        "        }",
        "",
        "# 输出 JSON",
        "print(json.dumps(bone_data))",
    ]
    return "\n".join(script_lines)
