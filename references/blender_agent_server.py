# blender_agent_server.py
# 运行在 Windows 高配机上，暴露 HTTP API 给 Linux OpenClaw 调用

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from typing import List, Literal, Optional, Dict
import subprocess
import json
import tempfile
import shutil
from pathlib import Path
import hashlib
import time
from enum import Enum

app = FastAPI(title="Blender Agent Server - Programmatic Modeling & Rendering")

# 配置 — 根据实际安装路径修改
BLENDER_EXE = r"C:\Program Files\Blender Foundation\Blender 4.0\blender.exe"
WORK_DIR = Path("D:/BlenderAgent")
CACHE_DIR = WORK_DIR / "cache"
OUTPUT_DIR = WORK_DIR / "outputs"
TEMPLATE_DIR = WORK_DIR / "templates"

for d in [WORK_DIR, CACHE_DIR, OUTPUT_DIR, TEMPLATE_DIR]:
    d.mkdir(parents=True, exist_ok=True)


class CameraPreset(str, Enum):
    FRONT = "front"
    THREE_QUARTER = "three_quarter"
    SIDE = "side"
    BACK = "back"
    TOP = "top"
    ISOMETRIC = "isometric"
    CLOSEUP_FACE = "closeup_face"
    FULL_BODY = "full_body"
    STANDARD_8 = "standard_8"
    STANDARD_4 = "standard_4"
    PORTRAIT_3 = "portrait_3"


class CharacterParams(BaseModel):
    preset_name: str = Field(..., description="输出文件名")
    gender: Literal["male", "female"] = "male"
    height: float = Field(1.75, ge=1.4, le=2.0)
    mass: float = Field(0.5, ge=0.0, le=1.0, description="肌肉量 0-1")
    age: int = Field(25, ge=18, le=80)
    style: Literal["realistic", "anime", "lowpoly"] = "realistic"
    camera_preset: CameraPreset = CameraPreset.STANDARD_8
    custom_angles: Optional[List[float]] = None
    resolution: int = 1024


class SceneParams(BaseModel):
    preset_name: str
    scene_type: Literal["interior", "exterior", "studio", "abstract"]
    room_size: Literal["small", "medium", "large"] = "medium"
    style: Literal["modern", "cyberpunk", "minimal", "natural"] = "modern"
    objects: List[str] = []
    lighting: Literal["soft", "dramatic", "neon", "daylight"] = "soft"
    camera_preset: CameraPreset = CameraPreset.ISOMETRIC


def get_camera_angles(preset: CameraPreset, custom: Optional[List[float]] = None) -> List[Dict]:
    if custom:
        return [{"angle": a, "location": (0, -3, 1.6), "rotation": (1.1, 0, a)} for a in custom]

    presets = {
        CameraPreset.FRONT: [{"location": (0, -3, 1.6), "rotation": (1.4, 0, 0)}],
        CameraPreset.THREE_QUARTER: [{"location": (2, -2.5, 1.6), "rotation": (1.4, 0, 0.8)}],
        CameraPreset.SIDE: [{"location": (3, 0, 1.6), "rotation": (1.4, 0, 1.57)}],
        CameraPreset.BACK: [{"location": (0, 3, 1.6), "rotation": (1.4, 0, 3.14)}],
        CameraPreset.TOP: [{"location": (0, 0, 4), "rotation": (0, 0, 0)}],
        CameraPreset.ISOMETRIC: [{"location": (3, -3, 3), "rotation": (0.9, 0, 0.78)}],
        CameraPreset.CLOSEUP_FACE: [{"location": (0, -0.8, 1.7), "rotation": (1.4, 0, 0)}],
        CameraPreset.FULL_BODY: [{"location": (0, -4, 1.2), "rotation": (1.3, 0, 0)}],
        CameraPreset.STANDARD_8: [
            {"location": (0, -3, 1.6), "rotation": (1.4, 0, a), "name": f"angle_{int(a*57.3)}"}
            for a in [0, 0.78, 1.57, 2.36, 3.14, 3.92, 4.71, 5.5]
        ],
        CameraPreset.STANDARD_4: [
            {"location": (0, -3, 1.6), "rotation": (1.4, 0, a)}
            for a in [0, 1.57, 3.14, 4.71]
        ],
        CameraPreset.PORTRAIT_3: [
            {"location": (0, -3, 1.6), "rotation": (1.4, 0, 0), "name": "front"},
            {"location": (2, -2.5, 1.6), "rotation": (1.4, 0, 0.78), "name": "three_quarter"},
            {"location": (3, 0, 1.6), "rotation": (1.4, 0, 1.57), "name": "side"}
        ]
    }
    return presets.get(preset, presets[CameraPreset.STANDARD_8])


def generate_character_script(params: CharacterParams) -> str:
    angles_config = get_camera_angles(params.camera_preset, params.custom_angles)
    angles_json = json.dumps(angles_config)

    return f'''
import bpy, json, sys

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)

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
        print(f"MB-Lab parameter warning: {{e}}")
    try:
        bpy.ops.mblab.finalize_character()
        character_obj = bpy.context.object
    except:
        character_obj = obj
    print("MB-Lab character generated")
except Exception as e:
    print(f"MB-Lab failed, using geometry fallback: {{e}}")
    bpy.ops.mesh.primitive_cylinder_add(radius=0.3, depth=1.7, location=(0, 0, 0.85))
    body = bpy.context.object
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.25, location=(0, 0, 1.9))
    head = bpy.context.object
    bpy.ops.object.select_all(action='DESELECT')
    body.select_set(True)
    head.select_set(True)
    bpy.context.view_layer.objects.active = body
    bpy.ops.object.join()
    character_obj = bpy.context.object

cam_data = bpy.data.cameras.new(name="Camera")
camera = bpy.data.objects.new("Camera", cam_data)
bpy.context.scene.collection.objects.link(camera)
bpy.context.scene.camera = camera

scene = bpy.context.scene
scene.render.engine = 'CYCLES'
scene.cycles.device = 'GPU'
scene.render.resolution_x = {params.resolution}
scene.render.resolution_y = {params.resolution}
scene.render.resolution_percentage = 100

try:
    prefs = bpy.context.preferences.addons['cycles'].preferences
    prefs.get_devices()
    for d in prefs.devices:
        if "NVIDIA" in d.name or "RTX" in d.name:
            d.use = True
except:
    pass

angles = json.loads(r\'\'\'{angles_json}\'\'\')
output_paths = []
for i, cfg in enumerate(angles):
    camera.location = cfg['location']
    camera.rotation_euler = cfg['rotation']
    angle_name = cfg.get('name', f"angle_{{i}}")
    filepath = r"{OUTPUT_DIR}/{params.preset_name}_{{angle_name}}.png"
    scene.render.filepath = filepath
    bpy.ops.render.render(write_still=True)
    output_paths.append(filepath)

bpy.ops.wm.save_as_mainfile(filepath=r"{CACHE_DIR}/{params.preset_name}.blend")
print(json.dumps(output_paths))
'''


def generate_scene_script(params: SceneParams) -> str:
    angles_config = get_camera_angles(params.camera_preset)
    angles_json = json.dumps(angles_config)

    style_configs = {
        "cyberpunk": {"bg_color": (0.05, 0.05, 0.1), "light_color": (1.0, 0.2, 0.8)},
        "natural": {"bg_color": (0.9, 0.95, 1.0), "light_color": (1.0, 0.95, 0.8)},
        "modern": {"bg_color": (0.9, 0.9, 0.9), "light_color": (1.0, 1.0, 1.0)}
    }
    style = style_configs.get(params.style, style_configs["modern"])

    return f'''
import bpy, bmesh, json

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)

scene = bpy.context.scene
room_size = {{"small": 4, "medium": 8, "large": 15}}["{params.room_size}"]

bpy.ops.mesh.primitive_plane_add(size=room_size, location=(0, 0, 0))
floor = bpy.context.object; floor.name = "Floor"

for i in range(4):
    angle = i * 1.57
    x = (room_size/2) * (1 if i == 0 else -1 if i == 2 else 0)
    y = (room_size/2) * (1 if i == 1 else -1 if i == 3 else 0)
    bpy.ops.mesh.primitive_plane_add(size=room_size, location=(x, y, room_size/2))
    wall = bpy.context.object
    wall.rotation_euler = (0, 1.57, angle)
    wall.name = f"Wall_{{i}}"

objects = {params.objects}
for i, obj_type in enumerate(objects):
    loc = ((i-1)*2, 0, 1)
    if obj_type == "desk":
        bpy.ops.mesh.primitive_cube_add(size=1.5, location=loc, scale=(1, 0.6, 0.8))
    elif obj_type == "chair":
        bpy.ops.mesh.primitive_cube_add(size=0.6, location=(loc[0], loc[1]+1, 0.4))

if "{params.lighting}" == "neon":
    bpy.ops.object.light_add(type='AREA', location=(0, 0, 3))
    light = bpy.context.object; light.data.energy = 1000
    light.data.color = {style['light_color']}
else:
    bpy.ops.object.light_add(type='SUN', location=(5, 5, 10))
    light = bpy.context.object; light.data.energy = 3

world = bpy.data.worlds.new(name="World")
scene.world = world
world.use_nodes = True
bg = world.node_tree.nodes['Background']
bg.inputs[0].default_value = {style['bg_color']} + (1,)
bg.inputs[1].default_value = 1

cam_data = bpy.data.cameras.new(name="Camera")
camera = bpy.data.objects.new("Camera", cam_data)
scene.collection.objects.link(camera)
scene.camera = camera

scene.render.engine = 'CYCLES'
scene.cycles.device = 'GPU'
scene.render.resolution_x = 1920
scene.render.resolution_y = 1080

angles = json.loads(r\'\'\'{angles_json}\'\'\')
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


@app.post("/generate/character")
async def generate_character(params: CharacterParams, background_tasks: BackgroundTasks):
    try:
        script = generate_character_script(params)
        script_file = CACHE_DIR / f"gen_{params.preset_name}_{int(time.time())}.py"
        script_file.write_text(script, encoding="utf-8")

        result = subprocess.run(
            [BLENDER_EXE, "-b", "--python", str(script_file)],
            capture_output=True, text=True, timeout=300
        )

        output_files = sorted(OUTPUT_DIR.glob(f"{params.preset_name}_*.png"))
        if not output_files:
            raise HTTPException(500, f"渲染失败: {result.stderr[-1000:]}")

        background_tasks.add_task(lambda: script_file.unlink() if script_file.exists() else None)

        return {
            "status": "success",
            "preset_name": params.preset_name,
            "outputs": [str(f) for f in output_files],
            "blend_file": str(CACHE_DIR / f"{params.preset_name}.blend"),
            "count": len(output_files)
        }
    except subprocess.TimeoutExpired:
        raise HTTPException(504, "渲染超时（超过5分钟）")
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/generate/scene")
async def generate_scene(params: SceneParams):
    try:
        script = generate_scene_script(params)
        script_file = CACHE_DIR / f"scene_{params.preset_name}.py"
        script_file.write_text(script, encoding="utf-8")

        result = subprocess.run(
            [BLENDER_EXE, "-b", "--python", str(script_file)],
            capture_output=True, text=True, timeout=300
        )

        output_files = sorted(OUTPUT_DIR.glob(f"{params.preset_name}_scene_*.png"))

        return {
            "status": "success",
            "outputs": [str(f) for f in output_files],
            "blend_file": str(CACHE_DIR / f"{params.preset_name}_scene.blend")
        }
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/outputs/{filename}")
def get_output(filename: str):
    file_path = OUTPUT_DIR / filename
    if not file_path.exists():
        raise HTTPException(404, "文件不存在")
    return FileResponse(file_path)


@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "blender_path": BLENDER_EXE,
        "cache_dir": str(CACHE_DIR),
        "output_dir": str(OUTPUT_DIR)
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
