import json
from typing import List, Literal

from pydantic import BaseModel, Field

from camera_presets import CameraPreset, get_camera_angles


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


def generate_scene_script(
    params: SceneParams,
    output_dir: str = "D:/BlenderAgent/outputs",
    cache_dir: str = "D:/BlenderAgent/cache",
) -> str:
    """生成场景脚本 - 程序化场景建模

    Args:
        params: 场景参数
        output_dir: Windows 端渲染输出目录
        cache_dir: Windows 端缓存目录
    """

    angles_config = get_camera_angles(params.camera_preset)
    angles_json = json.dumps(angles_config)

    style = _STYLE_CONFIGS.get(params.style, _STYLE_CONFIGS["modern"])
    bg_color = style["bg_color"]
    light_color = style["light_color"]

    script_lines = [
        "import bpy",
        "import json",
        "",
        "# 清理",
        "bpy.ops.object.select_all(action='SELECT')",
        "bpy.ops.object.delete(use_global=False)",
        "",
        "scene = bpy.context.scene",
        "",
        "# 创建基础房间",
        f'room_size = {{"small": 4, "medium": 8, "large": 15}}["{params.room_size}"]',
        "",
        "# 地板",
        "bpy.ops.mesh.primitive_plane_add(size=room_size, location=(0, 0, 0))",
        "floor = bpy.context.object",
        'floor.name = "Floor"',
        "",
        "# 墙壁（4 面）",
        "for i in range(4):",
        "    angle = i * 1.57",
        "    x = (room_size / 2) * (1 if i == 0 else -1 if i == 2 else 0)",
        "    y = (room_size / 2) * (1 if i == 1 else -1 if i == 3 else 0)",
        "    bpy.ops.mesh.primitive_plane_add(size=room_size, location=(x, y, room_size / 2))",
        "    wall = bpy.context.object",
        "    wall.rotation_euler = (0, 1.57, angle)",
        '    wall.name = "Wall_" + str(i)',
        "",
        "# 添加指定物体",
        f"objects = {params.objects}",
        "for i, obj_type in enumerate(objects):",
        "    loc = ((i - 1) * 2, 0, 1)",
        '    if obj_type == "desk":',
        "        bpy.ops.mesh.primitive_cube_add(size=1.5, location=loc, scale=(1, 0.6, 0.8))",
        '    elif obj_type == "chair":',
        "        bpy.ops.mesh.primitive_cube_add(size=0.6, location=(loc[0], loc[1] + 1, 0.4))",
        '    elif obj_type == "window":',
        "        bpy.ops.mesh.primitive_plane_add(size=2, location=(0, -room_size / 2 + 0.1, 2))",
        "        win = bpy.context.object",
        "        win.rotation_euler = (1.57, 0, 0)",
        '        mat = bpy.data.materials.new(name="WindowLight")',
        "        mat.use_nodes = True",
        "        nodes = mat.node_tree.nodes",
        "        links = mat.node_tree.links",
        "        for n in nodes:",
        "            nodes.remove(n)",
        "        em_node = nodes.new(type='ShaderNodeEmission')",
        "        em_node.inputs[0].default_value = (0.8, 0.9, 1.0, 1)",
        "        em_node.inputs[1].default_value = 5",
        "        out_node = nodes.new(type='ShaderNodeOutputMaterial')",
        "        links.new(em_node.outputs[0], out_node.inputs[0])",
        "        win.data.materials.append(mat)",
        "",
        "# 光照",
        f'if "{params.lighting}" == "neon":',
        "    bpy.ops.object.light_add(type='AREA', location=(0, 0, 3))",
        "    light = bpy.context.object",
        "    light.data.energy = 1000",
        f"    light.data.color = {light_color}",
        "else:",
        "    bpy.ops.object.light_add(type='SUN', location=(5, 5, 10))",
        "    light = bpy.context.object",
        "    light.data.energy = 3",
        "",
        "# 世界背景",
        'world = bpy.data.worlds.new(name="World")',
        "scene.world = world",
        "world.use_nodes = True",
        "bg = world.node_tree.nodes['Background']",
        f"bg.inputs[0].default_value = {bg_color} + (1,)",
        "bg.inputs[1].default_value = 1",
        "",
        "# 相机",
        'cam_data = bpy.data.cameras.new(name="Camera")',
        'camera = bpy.data.objects.new("Camera", cam_data)',
        "scene.collection.objects.link(camera)",
        "scene.camera = camera",
        "",
        "# 渲染设置",
        "scene.render.engine = 'CYCLES'",
        "scene.cycles.device = 'GPU'",
        "scene.render.resolution_x = 1920",
        "scene.render.resolution_y = 1080",
        "",
        "# 多角度渲染",
        f"angles = {angles_json}",
        "output_paths = []",
        "",
        "for i, cfg in enumerate(angles):",
        "    camera.location = cfg['location']",
        "    camera.rotation_euler = cfg['rotation']",
        f'    filepath = r"{output_dir}/{params.preset_name}_scene_" + str(i) + ".png"',
        "    scene.render.filepath = filepath",
        "    bpy.ops.render.render(write_still=True)",
        "    output_paths.append(filepath)",
        "",
        f'bpy.ops.wm.save_as_mainfile(filepath=r"{cache_dir}/{params.preset_name}_scene.blend")',
        "print(json.dumps(output_paths))",
    ]
    return "\n".join(script_lines)
