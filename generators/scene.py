import json
from typing import List, Literal

from pydantic import BaseModel, Field

from camera_presets import CameraPreset, get_camera_angles
from config import CACHE_DIR, OUTPUT_DIR


class SceneParams(BaseModel):
    """场景生成参数"""
    preset_name: str
    scene_type: Literal["interior", "exterior", "studio", "abstract"]
    room_size: Literal["small", "medium", "large"] = "medium"
    style: Literal["modern", "cyberpunk", "minimal", "natural"] = "modern"
    objects: List[str] = []
    lighting: Literal["soft", "dramatic", "neon", "daylight"] = "soft"
    camera_preset: CameraPreset = CameraPreset.ISOMETRIC


_STYLE_CONFIGS = {
    "cyberpunk": {"bg_color": (0.05, 0.05, 0.1), "light_color": (1.0, 0.2, 0.8)},
    "minimal": {"bg_color": (0.95, 0.95, 0.95), "light_color": (1.0, 1.0, 1.0)},
    "natural": {"bg_color": (0.9, 0.95, 1.0), "light_color": (1.0, 0.95, 0.8)},
    "modern": {"bg_color": (0.9, 0.9, 0.9), "light_color": (1.0, 1.0, 1.0)},
}


def generate_scene_script(params: SceneParams) -> str:
    """生成场景脚本 - 程序化场景建模"""

    angles_config = get_camera_angles(params.camera_preset)
    angles_json = json.dumps(angles_config)

    style = _STYLE_CONFIGS.get(params.style, _STYLE_CONFIGS["modern"])
    bg_color = style["bg_color"]
    light_color = style["light_color"]

    script = f'''\
import bpy
import json

# 清理
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)

scene = bpy.context.scene

# 创建基础房间
room_size = {{"small": 4, "medium": 8, "large": 15}}["{params.room_size}"]

# 地板
bpy.ops.mesh.primitive_plane_add(size=room_size, location=(0, 0, 0))
floor = bpy.context.object
floor.name = "Floor"

# 墙壁（4 面）
for i in range(4):
    angle = i * 1.57
    x = (room_size / 2) * (1 if i == 0 else -1 if i == 2 else 0)
    y = (room_size / 2) * (1 if i == 1 else -1 if i == 3 else 0)
    bpy.ops.mesh.primitive_plane_add(size=room_size, location=(x, y, room_size / 2))
    wall = bpy.context.object
    wall.rotation_euler = (0, 1.57, angle)
    wall.name = f"Wall_{{i}}"

# 添加指定物体
objects = {params.objects}
for i, obj_type in enumerate(objects):
    loc = ((i - 1) * 2, 0, 1)
    if obj_type == "desk":
        bpy.ops.mesh.primitive_cube_add(size=1.5, location=loc, scale=(1, 0.6, 0.8))
    elif obj_type == "chair":
        bpy.ops.mesh.primitive_cube_add(size=0.6, location=(loc[0], loc[1] + 1, 0.4))
    elif obj_type == "window":
        bpy.ops.mesh.primitive_plane_add(size=2, location=(0, -room_size / 2 + 0.1, 2))
        win = bpy.context.object
        win.rotation_euler = (1.57, 0, 0)
        mat = bpy.data.materials.new(name="WindowLight")
        mat.use_nodes = True
        mat.node_tree.nodes["Emission"].inputs[0].default_value = (0.8, 0.9, 1.0, 1)
        mat.node_tree.nodes["Emission"].inputs[1].default_value = 5
        win.data.materials.append(mat)

# 光照
if "{params.lighting}" == "neon":
    bpy.ops.object.light_add(type='AREA', location=(0, 0, 3))
    light = bpy.context.object
    light.data.energy = 1000
    light.data.color = {light_color}
else:
    bpy.ops.object.light_add(type='SUN', location=(5, 5, 10))
    light = bpy.context.object
    light.data.energy = 3

# 世界背景
world = bpy.data.worlds.new(name="World")
scene.world = world
world.use_nodes = True
bg = world.node_tree.nodes['Background']
bg.inputs[0].default_value = {bg_color} + (1,)
bg.inputs[1].default_value = 1

# 相机
cam_data = bpy.data.cameras.new(name="Camera")
camera = bpy.data.objects.new("Camera", cam_data)
scene.collection.objects.link(camera)
scene.camera = camera

# 渲染设置
scene.render.engine = 'CYCLES'
scene.cycles.device = 'GPU'
scene.render.resolution_x = 1920
scene.render.resolution_y = 1080

# 多角度渲染
angles = {angles_json}
output_paths = []

for i, cfg in enumerate(angles):
    camera.location = cfg['location']
    camera.rotation_euler = cfg['rotation']
    filepath = r"{OUTPUT_DIR}/{params.preset_name}_scene_{{i}}.png"
    scene.render.filepath = filepath
    bpy.ops.render.render(write_still=True)
    output_paths.append(filepath)

bpy.ops.wm.save_as_mainfile(filepath=r"{CACHE_DIR}/{params.preset_name}_scene.blend")
print(json.dumps(output_paths))
'''
    return script
