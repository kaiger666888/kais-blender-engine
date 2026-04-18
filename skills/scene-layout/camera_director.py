"""电影级相机导演

三分法、180° 对话轴线、视线引导、景深控制。
生成符合电影工业标准的相机配置。"""

import math
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field


@dataclass
class CameraRig:
    """相机配置"""
    name: str
    location: Tuple[float, float, float]  # (x, y, z)
    look_at: Tuple[float, float, float]    # (x, y, z)
    focal_length: float = 50.0            # mm
    f_stop: float = 2.8                   # 光圈
    resolution: Tuple[int, int] = (1280, 720)
    label: str = ""


@dataclass
class SubjectInfo:
    """拍摄主体信息"""
    name: str
    position: Tuple[float, float, float]  # 世界坐标
    height: float = 1.8                   # 角色高度
    eye_height: float = 1.65              # 眼睛高度


# ── 预设相机参数 ──────────────────────────────────────────────

SHOT_PRESETS = {
    "extreme_wide": {
        "focal_length": 18,
        "distance_factor": 5.0,
        "height_offset": 1.5,
        "label": "Extreme Wide Shot",
    },
    "wide": {
        "focal_length": 28,
        "distance_factor": 3.5,
        "height_offset": 1.0,
        "label": "Wide Shot",
    },
    "medium": {
        "focal_length": 50,
        "distance_factor": 2.0,
        "height_offset": 0.5,
        "label": "Medium Shot",
    },
    "closeup": {
        "focal_length": 85,
        "distance_factor": 1.2,
        "height_offset": 0.3,
        "label": "Close-up",
    },
    "extreme_closeup": {
        "focal_length": 135,
        "distance_factor": 0.8,
        "height_offset": 0.15,
        "label": "Extreme Close-up",
    },
    "otw_over_shoulder": {
        "focal_length": 85,
        "distance_factor": 1.0,
        "height_offset": 0.2,
        "label": "Over-the-Shoulder",
    },
}


def compute_thirds_grid(
    subject: SubjectInfo,
    camera_elevation: float = 0.0,
) -> Tuple[float, float, float]:
    """
    三分法构图：将主体放在画面九宫格的交叉点上。
    
    Returns: (camera_x, camera_y, camera_z) 相机世界坐标
    """
    sx, sy, sz = subject.position
    eye_z = sz + subject.eye_height
    
    # 默认放在左下交叉点（从相机视角看）
    # 相机偏右偏前，使主体在画面左三分之一
    cam_x = sx + 1.5
    cam_y = sy - 2.0
    cam_z = eye_z + camera_elevation
    
    return (cam_x, cam_y, cam_z)


def enforce_180_degree_rule(
    subject_a: SubjectInfo,
    subject_b: SubjectInfo,
    camera_offset: Tuple[float, float] = (0, -3.0),
) -> CameraRig:
    """
    180° 轴线规则：双人对话时，相机始终在两人连线的同一侧。
    
    Args:
        subject_a, subject_b: 对话双方
        camera_offset: 相机相对于轴线的偏移 (x_offset, y_offset)
    
    Returns:
        符合 180° 规则的 CameraRig
    """
    ax, ay, az = subject_a.position
    bx, by, bz = subject_b.position
    
    # 两人连线的中点
    mid_x = (ax + bx) / 2
    mid_y = (ay + by) / 2
    mid_z = (az + bz) / 2 + min(subject_a.eye_height, subject_b.eye_height) * 0.8
    
    # 轴线法向量（垂直于连线）
    line_dx = bx - ax
    line_dy = by - ay
    line_len = math.sqrt(line_dx**2 + line_dy**2) or 1.0
    
    # 法向量方向（垂直于连线，偏前）
    normal_x = -line_dy / line_len
    normal_y = line_dx / line_len
    
    # 相机位置：中点 + 法向量偏移
    cam_x = mid_x + normal_x * abs(camera_offset[1]) + camera_offset[0]
    cam_y = mid_y + normal_y * abs(camera_offset[1])
    cam_z = mid_z + 0.3
    
    return CameraRig(
        name="dialogue_otw",
        location=(cam_x, cam_y, cam_z),
        look_at=(mid_x, mid_y, mid_z),
        focal_length=85,
        f_stop=2.0,
        label="180° Rule Dialogue Shot",
    )


def compute_shot_camera(
    shot_type: str,
    subject: SubjectInfo,
    scene_center: Tuple[float, float, float],
    angle_deg: float = -45.0,
) -> CameraRig:
    """
    计算单镜头相机位置
    
    Args:
        shot_type: 预设类型 (wide/medium/closeup/...)
        subject: 主要拍摄对象
        scene_center: 场景中心
        angle_deg: 相机相对于正面的角度（-45 = 右前方）
    """
    preset = SHOT_PRESETS.get(shot_type, SHOT_PRESETS["medium"])
    
    sx, sy, sz = subject.position
    target_z = sz + subject.eye_height * 0.7  # 看向胸部偏上
    
    dist = subject.height * preset["distance_factor"]
    angle_rad = math.radians(angle_deg)
    
    cam_x = sx + dist * math.sin(angle_rad)
    cam_y = sy + dist * math.cos(angle_rad)
    cam_z = target_z + preset["height_offset"]
    
    return CameraRig(
        name=shot_type,
        location=(cam_x, cam_y, cam_z),
        look_at=(sx, sy, target_z),
        focal_length=preset["focal_length"],
        f_stop=2.8,
        label=preset["label"],
    )


def generate_camera_block(rig: CameraRig, cam_name: str = "Camera") -> str:
    """
    生成 Blender Python 代码块：设置相机
    
    Args:
        rig: CameraRig 配置
        cam_name: 相机对象名称
    
    Returns:
        Blender Python 代码片段
    """
    return f"""
# Camera: {rig.label}
cam_data = bpy.data.cameras.get('{cam_name}')
if not cam_data:
    cam_data = bpy.data.cameras.new('{cam_name}')
    cam_data.sensor_fit = 'AUTO'
cam = bpy.data.objects.get('{cam_name}')
if not cam:
    cam = bpy.data.objects.new('{cam_name}', cam_data)
    bpy.context.scene.collection.objects.link(cam)
bpy.context.scene.camera = cam

cam.location = ({rig.location[0]:.4f}, {rig.location[1]:.4f}, {rig.location[2]:.4f})

# look-at via track_quat
direction = mathutils.Vector({rig.look_at}) - cam.location
cam.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()

cam_data.lens = {rig.focal_length}
cam_data.dof.use_dof = True
cam_data.dof.aperture_fstop = {rig.f_stop}
"""


def generate_multi_shot_script(
    subjects: List[SubjectInfo],
    scene_center: Tuple[float, float, float],
    shot_types: List[str] = None,
    dialogue_mode: bool = False,
    output_prefix: str = "shot",
) -> str:
    """
    生成完整的多镜头渲染脚本
    
    Args:
        subjects: 拍摄主体列表
        scene_center: 场景中心
        shot_types: 镜头类型列表
        dialogue_mode: 是否启用 180° 轴线模式（双人对话）
        output_prefix: 输出文件名前缀
    """
    if shot_types is None:
        shot_types = ["wide", "medium", "closeup"]
    
    if dialogue_mode and len(subjects) >= 2:
        # 180° 轴线对话镜头
        rigs = []
        for i, st in enumerate(shot_types):
            preset = SHOT_PRESETS.get(st, SHOT_PRESETS["medium"])
            a, b = subjects[0], subjects[1]
            mid = (
                (a.position[0] + b.position[0]) / 2,
                (a.position[1] + b.position[1]) / 2,
                (a.position[2] + b.position[2]) / 2 + 0.3,
            )
            rigs.append(CameraRig(
                name=f"dialogue_{st}",
                location=(
                    mid[0] + (1.5 if i % 2 == 0 else -1.5),
                    mid[1] - preset["distance_factor"] * 1.5,
                    mid[2] + preset["height_offset"],
                ),
                look_at=(a.position[0], a.position[1], a.position[2] + a.eye_height * 0.7),
                focal_length=preset["focal_length"],
                label=f"Dialogue {preset['label']}",
            ))
    else:
        rigs = [
            compute_shot_camera(st, subjects[0], scene_center)
            for st in shot_types
        ]
    
    lines = [
        "import bpy, mathutils",
        "",
        "scene = bpy.context.scene",
        "scene.render.engine = 'CYCLES'",
        "scene.cycles.device = 'GPU'",
        "scene.render.resolution_x = 1280",
        "scene.render.resolution_y = 720",
        "scene.cycles.samples = 128",
        "",
    ]
    
    for i, rig in enumerate(rigs):
        cam_name = f"ShotCamera_{i}"
        lines.append(f"# === Shot {i+1}: {rig.label} ===")
        lines.append(generate_camera_block(rig, cam_name).strip())
        lines.append(f"scene.render.filepath = r'D:\\BlenderAgent\\outputs\\{output_prefix}_{rig.name}.png'")
        lines.append("bpy.ops.render.render(write_still=True)")
        lines.append("")
    
    return "\n".join(lines)
