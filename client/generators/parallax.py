"""
视差场景渲染脚本生成器

将分层PNG（前景/中景/背景）构建为 Blender 视差场景，
生成可通过 BlenderAgentClient.run_sync() 执行的 Python 脚本。

遵循 kais-blender-engine generators 模式。
"""

from typing import List, Literal, Optional, Tuple
from pydantic import BaseModel, Field


class LayerConfig(BaseModel):
    """单个图层配置"""
    name: str = Field(..., description="图层名: foreground / midground / background / distant")
    image_path: str = Field(..., description="Windows端图片路径，如 D:/BlenderAgent/cache/parallax/foreground.png")
    z_depth: float = Field(..., description="Z轴深度(米)，负值=前方，正值=后方")


class ParallaxParams(BaseModel):
    """视差场景渲染参数"""
    preset_name: str = Field(..., description="输出文件名前缀")

    # 图层
    layers: List[LayerConfig] = Field(..., description="图层列表，按Z从近到远排序")

    # 摄像机
    camera_preset: Literal["scroll_left", "scroll_right", "push_in", "dolly_zoom", "orbit", "static"] = "scroll_left"
    camera_focal_length: float = Field(35.0, description="焦距(mm)")
    camera_distance: float = Field(2.0, description="摄像机Y轴距离")

    # 动画
    duration: float = Field(6.0, description="动画时长(秒)")
    fps: int = Field(24, description="帧率")
    move_range: float = Field(3.0, description="平移范围(米)")

    # 渲染
    output_format: Literal["video", "frames", "both"] = "video"
    resolution: Tuple[int, int] = Field((1080, 1920), description="(宽, 高)，默认9:16竖屏")
    engine: Literal["BLENDER_EEVEE", "BLENDER_WORKBENCH", "CYCLES"] = "BLENDER_EEVEE"
    samples: int = Field(64, description="Cycles采样数(Eevee忽略)")

    # 灯光
    light_energy: float = Field(2.0, description="太阳光强度")

    # 输出
    output_dir: str = Field("D:/BlenderAgent/cache/parallax", description="输出目录")


def generate_parallax_script(params: ParallaxParams) -> str:
    """生成 Blender Python 渲染脚本"""

    layers_json = [l.model_dump() for l in params.layers]

    return f'''
import bpy
import os
import math

# ====== 视差场景配置 ======
LAYERS = {layers_json}
PRESET_NAME = "{params.preset_name}"
CAMERA_PRESET = "{params.camera_preset}"
FOCAL_LENGTH = {params.camera_focal_length}
CAM_DISTANCE = {params.camera_distance}
DURATION = {params.duration}
FPS = {params.fps}
MOVE_RANGE = {params.move_range}
RESOLUTION = {params.resolution}
ENGINE = "{params.engine}"
SAMPLES = {params.samples}
LIGHT_ENERGY = {params.light_energy}
OUTPUT_DIR = "{params.output_dir}"
OUTPUT_FORMAT = "{params.output_format}"
TOTAL_FRAMES = int(DURATION * FPS)

# ====== 清理场景 ======
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)

# ====== 场景设置 ======
scene = bpy.context.scene
scene.render.resolution_x = RESOLUTION[0]
scene.render.resolution_y = RESOLUTION[1]
scene.render.engine = ENGINE
scene.render.fps = FPS
scene.frame_start = 1
scene.frame_end = TOTAL_FRAMES
if ENGINE == "CYCLES":
    scene.cycles.samples = SAMPLES

# ====== 摄像机 ======
cam_data = bpy.data.cameras.new("ParallaxCam")
cam_data.lens = FOCAL_LENGTH
cam_data.sensor_fit = 'AUTO'
cam_obj = bpy.data.objects.new("Camera", cam_data)
bpy.context.scene.collection.objects.link(cam_obj)
scene.camera = cam_obj

# ====== 创建图层平面 ======
for layer in LAYERS:
    name = layer["name"]
    z = layer["z_depth"]
    img_path = layer["image_path"]

    # 缩放补偿：远处层放大以保持视觉一致
    scale = 1.0 + (abs(z) / FOCAL_LENGTH)

    bpy.ops.mesh.primitive_plane_add(size=20.0, location=(0, z, 0))
    plane = bpy.context.active_object
    plane.name = f"Layer_{{name}}"
    plane.scale = (scale, 1.0, 1.0)

    if os.path.exists(img_path):
        mat = bpy.data.materials.new(name=f"Mat_{{name}}")
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes["Principled BSDF"]

        tex_node = mat.node_tree.nodes.new('ShaderNodeTexImage')
        tex_node.image = bpy.data.images.load(img_path)
        tex_node.image.colorspace_settings.name = 'sRGB'

        mat.blend_method = 'BLEND'
        mat.node_tree.links.new(tex_node.outputs['Color'], bsdf.inputs['Base Color'])
        mat.node_tree.links.new(tex_node.outputs['Alpha'], bsdf.inputs['Alpha'])

        plane.data.materials.append(mat)
        print(f"✅ Layer {{name}}: {{img_path}} (Z={{z}}m, scale={{scale:.3f}})")
    else:
        print(f"⚠️  Layer {{name}}: file not found {{img_path}}")

# ====== 摄像机动画 ======
cam = bpy.data.objects["Camera"]

if CAMERA_PRESET == "scroll_left":
    cam.location = (-MOVE_RANGE, -CAM_DISTANCE, 0.0)
    cam.keyframe_insert(data_path="location", frame=1)
    cam.location = (MOVE_RANGE, -CAM_DISTANCE, 0.0)
    cam.keyframe_insert(data_path="location", frame=TOTAL_FRAMES)
elif CAMERA_PRESET == "scroll_right":
    cam.location = (MOVE_RANGE, -CAM_DISTANCE, 0.0)
    cam.keyframe_insert(data_path="location", frame=1)
    cam.location = (-MOVE_RANGE, -CAM_DISTANCE, 0.0)
    cam.keyframe_insert(data_path="location", frame=TOTAL_FRAMES)
elif CAMERA_PRESET == "push_in":
    cam.location = (0.0, -(CAM_DISTANCE + 3), 0.0)
    cam.keyframe_insert(data_path="location", frame=1)
    cam.location = (0.0, -CAM_DISTANCE, 0.0)
    cam.keyframe_insert(data_path="location", frame=TOTAL_FRAMES)
elif CAMERA_PRESET == "dolly_zoom":
    cam.location = (0.0, -(CAM_DISTANCE + 3), 0.0)
    cam.keyframe_insert(data_path="location", frame=1)
    cam.location = (0.0, -max(CAM_DISTANCE - 1, 0.5), 0.0)
    cam.keyframe_insert(data_path="location", frame=TOTAL_FRAMES)
    cam_data = cam.data
    cam_data.lens = 85.0
    cam_data.keyframe_insert(data_path="lens", frame=1)
    cam_data.lens = 24.0
    cam_data.keyframe_insert(data_path="lens", frame=TOTAL_FRAMES)
elif CAMERA_PRESET == "orbit":
    for i in range(1, TOTAL_FRAMES + 1):
        angle = (i / TOTAL_FRAMES) * math.pi / 2
        r = CAM_DISTANCE + 3
        cam.location = (r * math.sin(angle), r * math.cos(angle), 1.0)
        cam.keyframe_insert(data_path="location", frame=i)
        direction = -cam.location
        cam.rotation_euler = (0, 0, math.atan2(direction.x, direction.y))
        cam.keyframe_insert(data_path="rotation_euler", frame=i)
elif CAMERA_PRESET == "static":
    cam.location = (0.0, -CAM_DISTANCE, 0.0)

# F-Curve 缓入缓出（Blender 5.1+ 默认已是BEZIER，直接设置handle类型）
if cam.animation_data and cam.animation_data.action:
    try:
        for channel in cam.animation_data.action.channels:
            if hasattr(channel, 'fcurves'):
                for fc in channel.fcurves:
                    for kf in fc.keyframe_points:
                        kf.interpolation = 'BEZIER'
                        kf.handle_left_type = 'AUTO_CLAMPED'
                        kf.handle_right_type = 'AUTO_CLAMPED'
    except Exception:
        pass  # Blender 5.1+ fcurves API已变更，默认BEZIER足够

# ====== 灯光 ======
light_data = bpy.data.lights.new(name="ParallaxLight", type='SUN')
light_data.energy = LIGHT_ENERGY
light_obj = bpy.data.objects.new("SunLight", light_data)
light_obj.location = (0, 0, 10)
bpy.context.scene.collection.objects.link(light_obj)

# ====== 渲染 ======
os.makedirs(OUTPUT_DIR, exist_ok=True)

if OUTPUT_FORMAT in ("video", "both"):
    frames_dir = os.path.join(OUTPUT_DIR, f"{{PRESET_NAME}}_frames")
    scene.render.filepath = frames_dir + "/"
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGBA'
    bpy.ops.render.render(animation=True)
    print(f"✅ Frames: {{frames_dir}}/")
    # 尝试用ffmpeg合成视频
    try:
        import subprocess
        video_path = os.path.join(OUTPUT_DIR, f"{{PRESET_NAME}}.mp4")
        w, h = RESOLUTION
        cmd = f'ffmpeg -y -framerate {{FPS}} -i "{{frames_dir}}/%04d.png" -c:v libx264 -pix_fmt yuv420p -s {{w}}x{{h}} "{{video_path}}"'
        subprocess.run(cmd, shell=True, capture_output=True)
        if os.path.exists(video_path):
            print(f"✅ Video: {{video_path}}")
        else:
            print(f"⚠️  ffmpeg not available, frames saved to {{frames_dir}}/")
    except Exception:
        print(f"⚠️  ffmpeg合成失败，帧序列已保存: {{frames_dir}}/")

if OUTPUT_FORMAT in ("frames",):
    frames_dir = os.path.join(OUTPUT_DIR, f"{{PRESET_NAME}}_frames")
    scene.render.filepath = frames_dir + "/"
    scene.render.image_settings.file_format = 'PNG'
    bpy.ops.render.render(animation=True)
    print(f"✅ Frames: {{frames_dir}}/")

# 保存 .blend
blend_path = os.path.join(OUTPUT_DIR, f"{{PRESET_NAME}}.blend")
bpy.ops.wm.save_as_mainfile(filepath=blend_path)
print(f"✅ Blend: {{blend_path}}")

print("🎉 Parallax scene complete!")
'''
