import json
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from camera_presets import CameraPreset, get_camera_angles
from config import CACHE_DIR, OUTPUT_DIR


class CharacterParams(BaseModel):
    """角色生成参数"""
    preset_name: str = Field(..., description="输出文件名，如 'hero_001'")
    gender: Literal["male", "female"] = "male"
    height: float = Field(1.75, ge=1.4, le=2.0)
    mass: float = Field(0.5, ge=0.0, le=1.0, description="肌肉量/体重 0-1")
    age: int = Field(25, ge=18, le=80)
    style: Literal["realistic", "anime", "lowpoly"] = "realistic"
    camera_preset: CameraPreset = CameraPreset.STANDARD_8
    custom_angles: Optional[List[float]] = None
    resolution: int = 1024


def generate_character_script(params: CharacterParams) -> str:
    """生成 Blender Python 脚本 - 程序化角色建模"""

    angles_config = get_camera_angles(params.camera_preset, params.custom_angles)
    angles_json = json.dumps(angles_config)

    script = f'''\
import bpy
import json
import sys

# 清理场景
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)

# 尝试 MB-Lab 生成（如果安装），否则用基础几何体
character_obj = None
try:
    bpy.ops.mblab.character_create()
    obj = bpy.context.object

    try:
        bpy.context.scene.mblab_character_gender = "{params.gender}"
        if obj.data.shape_keys:
            keys = obj.data.shape_keys.key_blocks
            if "Expressions_mass" in keys:
                keys["Expressions_mass"].value = {params.mass}
            if "Expressions_height" in keys:
                keys["Expressions_height"].value = {(params.height - 1.7) / 0.3}
    except Exception as e:
        print(f"MB-Lab 参数设置警告: {{e}}")

    try:
        bpy.ops.mblab.finalize_character()
        character_obj = bpy.context.object
    except Exception:
        character_obj = obj

    print("MB-Lab 角色生成成功")

except Exception as e:
    print(f"MB-Lab 失败，使用基础几何体: {{e}}")
    # 降级方案：程序化生成基础人形
    bpy.ops.mesh.primitive_cylinder_add(radius=0.3, depth=1.7, location=(0, 0, 0.85))
    body = bpy.context.object
    body.name = "Body"

    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.25, location=(0, 0, 1.9))
    head = bpy.context.object
    head.name = "Head"

    bpy.ops.object.select_all(action='DESELECT')
    body.select_set(True)
    head.select_set(True)
    bpy.context.view_layer.objects.active = body
    bpy.ops.object.join()
    character_obj = bpy.context.object

# 创建相机
cam_data = bpy.data.cameras.new(name="Camera")
camera = bpy.data.objects.new("Camera", cam_data)
bpy.context.scene.collection.objects.link(camera)
bpy.context.scene.camera = camera

# 渲染设置
scene = bpy.context.scene
scene.render.engine = 'CYCLES'
scene.cycles.device = 'GPU'
scene.render.resolution_x = {params.resolution}
scene.render.resolution_y = {params.resolution}
scene.render.resolution_percentage = 100

# 启用 GPU（CUDA / OptiX）
prefs = bpy.context.preferences.addons['cycles'].preferences
prefs.get_devices()
for d in prefs.devices:
    if "NVIDIA" in d.name or "RTX" in d.name:
        d.use = True
        print(f"启用 GPU: {{d.name}}")

# 多角度渲染
angles = json.loads(r\\'\\'\\'{angles_json}\\'\\'\\'')
output_paths = []

for i, cfg in enumerate(angles):
    camera.location = cfg['location']
    camera.rotation_euler = cfg['rotation']

    angle_name = cfg.get('name', f"angle_{{i}}")
    filepath = r"{OUTPUT_DIR}/{params.preset_name}_{{angle_name}}.png"
    scene.render.filepath = filepath

    bpy.ops.render.render(write_still=True)
    output_paths.append(filepath)
    print(f"渲染完成: {{filepath}}")

# 保存 blend 文件
bpy.ops.wm.save_as_mainfile(filepath=r"{CACHE_DIR}/{params.preset_name}.blend")

print("CHARACTER_GENERATION_COMPLETE")
print(json.dumps(output_paths))
'''
    return script
