"""场景渲染脚本生成器

组合 Poly Haven 场景资产（HDRI + 3D模型 + PBR纹理）+ Mixamo 角色动画，
生成完整的 Blender Python 渲染脚本。
"""

import json
from typing import Dict, List, Literal, Optional, Tuple

from pydantic import BaseModel, Field


# ── 默认路径（Windows 端）─────────────────────────────────
DEFAULT_ASSETS_DIR = "D:/BlenderAgent/assets"


class ModelPlacement(BaseModel):
    """场景中的模型放置"""
    name: str = Field(..., description="模型目录名，如 'sofa_02', 'potted_plant_01'")
    location: Tuple[float, float, float] = (0, 0, 0)
    rotation: Tuple[float, float, float] = (0, 0, 0)
    scale: float = 1.0


class SceneParams(BaseModel):
    """场景渲染参数"""
    scene_name: str = Field(..., description="输出文件名前缀")

    # 环境光照
    hdri: Optional[str] = Field(None, description="HDRI 名（不含扩展名），如 'studio_small_03_4k'")
    hdri_strength: float = Field(1.0, ge=0, description="HDRI 强度")

    # 场景模型
    models: List[ModelPlacement] = Field(default_factory=list, description="要放置的 3D 模型列表")

    # 地面
    ground_size: float = Field(20.0, description="地面尺寸（米）")
    ground_texture: Optional[str] = Field(None, description="地面 PBR 纹理目录名，如 'wood_floor_01'")

    # 角色动画（可选）
    character: Optional[str] = Field(None, description="角色 FBX 文件名")
    motions: List[str] = Field(default_factory=list, description="动画 FBX 文件名列表")
    character_scale: float = 1.0

    # 相机
    camera_preset: Literal["front", "side", "three_quarter", "follow", "orbit"] = "three_quarter"
    camera_location: Optional[Tuple[float, float, float]] = Field(None, description="自定义相机位置")
    camera_target: Optional[Tuple[float, float, float]] = Field(None, description="相机看向的目标点")

    # 渲染
    output_format: Literal["frames", "video", "both"] = "frames"
    resolution: int = 1024
    samples: int = Field(256, ge=32, le=2048)
    fps: int = 24
    transparent_bg: bool = False


def generate_scene_script(
    params: SceneParams,
    output_dir: str = "D:/BlenderAgent/outputs",
    assets_dir: str = DEFAULT_ASSETS_DIR,
    characters_dir: str = "D:/BlenderAgent/animations/characters",
    motions_dir: str = "D:/BlenderAgent/animations/motions",
) -> str:
    """生成场景渲染 Blender Python 脚本

    工作流：
    1. 清理场景
    2. HDRI 环境光（可选）
    3. 地面 + PBR 纹理（可选）
    4. 追加 Poly Haven 3D 模型
    5. 导入 Mixamo 角色 + 动画（可选）
    6. 相机 + 渲染设置
    7. 渲染输出
    """
    models_json = json.dumps([m.model_dump() for m in params.models])
    has_character = bool(params.character)
    has_motions = bool(params.motions)
    has_hdri = bool(params.hdri)
    has_ground_texture = bool(params.ground_texture)
    has_custom_camera = bool(params.camera_location)
    has_follow = params.camera_preset in ("follow",) and has_character
    has_orbit = params.camera_preset in ("orbit",)

    lines = [
        "import bpy",
        "import json",
        "import math",
        "import mathutils",
        "import os",
        "",
        "# ── 参数 ──────────────────────────────────────────",
        f"scene_name = {json.dumps(params.scene_name)}",
        f"output_dir = r'{output_dir}'",
        f"assets_dir = r'{assets_dir}'",
        f"resolution = {params.resolution}",
        f"samples = {params.samples}",
        f"fps = {params.fps}",
        f"transparent_bg = {str(params.transparent_bg)}",
        f"ground_size = {params.ground_size}",
        f"hdri_strength = {params.hdri_strength}",
        f"output_format = {json.dumps(params.output_format)}",
        "",
        "# ── 清理场景 ──────────────────────────────────────",
        "bpy.ops.object.select_all(action='SELECT')",
        "bpy.ops.object.delete(use_global=False)",
        "for block in bpy.data.meshes:",
        "    if block.users == 0: bpy.data.meshes.remove(block)",
        "for block in bpy.data.armatures:",
        "    if block.users == 0: bpy.data.armatures.remove(block)",
        "for block in bpy.data.actions:",
        "    if block.users == 0: bpy.data.actions.remove(block)",
        "for block in bpy.data.cameras:",
        "    if block.users == 0: bpy.data.cameras.remove(block)",
        "for block in bpy.data.lights:",
        "    if block.users == 0: bpy.data.lights.remove(block)",
        "for block in bpy.data.materials:",
        "    if block.users == 0: bpy.data.materials.remove(block)",
        "",
    ]

    # ── HDRI 环境光 ──────────────────────────────────────
    if has_hdri:
        lines.extend([
            "# ── HDRI 环境光 ────────────────────────────────",
            f"hdri_path = r'{assets_dir}/polyhaven/hdris/{params.hdri}.hdr'",
            "if os.path.isfile(hdri_path):",
            "    world = bpy.data.worlds.new(name='HDRI_World')",
            "    bpy.context.scene.world = world",
            "    world.use_nodes = True",
            "    nodes = world.node_tree.nodes",
            "    links = world.node_tree.links",
            "    nodes.clear()",
            "    env_tex = nodes.new('ShaderNodeTexEnvironment')",
            "    env_tex.image = bpy.data.images.load(hdri_path)",
            "    env_tex.location = (-300, 0)",
            "    bg = nodes.new('ShaderNodeBackground')",
            "    bg.inputs['Strength'].default_value = hdri_strength",
            "    bg.location = (0, 0)",
            "    out = nodes.new('ShaderNodeOutputWorld')",
            "    out.location = (300, 0)",
            "    links.new(env_tex.outputs['Color'], bg.inputs['Color'])",
            "    links.new(bg.outputs['Background'], out.inputs['Surface'])",
            "    print('HDRI loaded: ' + hdri_path)",
            "else:",
            "    print('WARN: HDRI not found: ' + hdri_path)",
            "",
        ])
    else:
        lines.extend([
            "# ── 默认灯光（无 HDRI 时）───────────────────────",
            "world = bpy.data.worlds.new(name='World')",
            "bpy.context.scene.world = world",
            "world.use_nodes = True",
            "bg_node = world.node_tree.nodes['Background']",
            "bg_node.inputs[0].default_value = (0.15, 0.15, 0.18, 1)",
            "bg_node.inputs[1].default_value = 1",
            "",
            "for lc in [",
            "    {'type': 'AREA', 'location': (2, -2, 2.5), 'energy': 800, 'color': (1.0, 0.95, 0.9), 'size': 2.0},",
            "    {'type': 'AREA', 'location': (-1.5, -1.5, 1.8), 'energy': 300, 'color': (0.9, 0.95, 1.0), 'size': 1.5},",
            "    {'type': 'AREA', 'location': (0, 2, 2.5), 'energy': 500, 'color': (1.0, 1.0, 1.0), 'size': 1.0},",
            "]:",
            "    bpy.ops.object.light_add(type=lc['type'], location=lc['location'])",
            "    lt = bpy.context.object",
            "    lt.data.energy = lc['energy']",
            "    lt.data.color = lc['color']",
            "    if hasattr(lt.data, 'size'):",
            "        lt.data.size = lc.get('size', 1.0)",
            "",
        ])

    # ── 地面 ──────────────────────────────────────────────
    lines.extend([
        "# ── 地面 ──────────────────────────────────────────",
        "bpy.ops.mesh.primitive_plane_add(size=ground_size, location=(0, 0, 0))",
        "ground = bpy.context.object",
        "ground.name = 'Ground'",
    ])

    if has_ground_texture:
        tex_name = params.ground_texture
        lines.extend([
            f"ground_tex_dir = r'{assets_dir}/polyhaven/textures/{tex_name}'",
            "ground_mat = bpy.data.materials.new(name='GroundPBR')",
            "ground_mat.use_nodes = True",
            "bsdf = ground_mat.node_tree.nodes['Principled BSDF']",
            "nodes = ground_mat.node_tree.nodes",
            "links = ground_mat.node_tree.links",
            "",
            "# 加载各通道纹理",
            "tex_maps = {",
            "    'Base Color': '_albedo_2k.jpg',",
            "    'Roughness': '_rough_2k.jpg',",
            "    'Ambient Occlusion': '_ao_2k.jpg',",
            "    'Normal': '_nor_gl_2k.jpg',",
            "}",
            "for socket_name, suffix in tex_maps.items():",
            "    # 查找匹配的纹理文件",
            "    import glob",
            "    pattern = os.path.join(ground_tex_dir, f'{os.path.basename(ground_tex_dir)}{suffix}')",
            "    matches = glob.glob(pattern)",
            "    if not matches:",
            "        continue",
            "    tex_path = matches[0]",
            "    tex_node = nodes.new('ShaderNodeTexImage')",
            "    tex_node.image = bpy.data.images.load(tex_path)",
            "    tex_node.location = (-600, nodes.location[1] if hasattr(nodes, 'location') else -300)",
            "    if socket_name == 'Normal':",
            "        normal_map = nodes.new('ShaderNodeNormalMap')",
            "        links.new(tex_node.outputs['Color'], normal_map.inputs['Color'])",
            "        links.new(normal_map.outputs['Normal'], bsdf.inputs['Normal'])",
            "    else:",
            "        links.new(tex_node.outputs['Color'], bsdf.inputs[socket_name])",
            "ground.data.materials.append(ground_mat)",
            "print('Ground texture applied: " + tex_name + "')",
        ])
    else:
        lines.extend([
            "ground_mat = bpy.data.materials.new(name='ShadowCatcher')",
            "ground_mat.use_nodes = True",
            "ground_mat.node_tree.nodes['Principled BSDF'].inputs['Alpha'].default_value = 0.0",
            "try:",
            "    ground.is_shadow_catcher = True",
            "except (AttributeError, Exception):",
            "    try:",
            "        ground.cycles.is_shadow_catcher = True",
            "    except (AttributeError, Exception):",
            "        pass",
            "ground.data.materials.append(ground_mat)",
        ])
    lines.append("")

    # ── 追加 Poly Haven 3D 模型 ──────────────────────────
    lines.extend([
        "# ── 追加 3D 模型 ─────────────────────────────────",
        "models_config = " + models_json,
        "for mc in models_config:",
        "    model_name = mc['name']",
        f"    model_dir = r'{assets_dir}/polyhaven/models/' + model_name",
        "    # 查找 .blend 文件",
        "    blend_file = None",
        "    if os.path.isdir(model_dir):",
        "        for f in os.listdir(model_dir):",
        "            if f.endswith('.blend'):",
        "                blend_file = os.path.join(model_dir, f)",
        "                break",
        "    if not blend_file or not os.path.isfile(blend_file):",
        "        print('WARN: Model .blend not found: ' + model_name)",
        "        continue",
        "",
        "    # 追加加载所有 objects",
        "    imported_objs = []",
        "    with bpy.data.libraries.load(blend_file) as (data_from, data_to):",
        "        data_to.objects = list(data_from.objects)",
        "    for obj in data_to.objects:",
        "        if obj is not None:",
        "            bpy.context.scene.collection.objects.link(obj)",
        "            imported_objs.append(obj)",
        "",
        "    if not imported_objs:",
        "        print('WARN: No objects imported from: ' + model_name)",
        "        continue",
        "",
        "    # 计算模型组的中心和包围盒",
        "    bbox_min = mathutils.Vector((float('inf'),) * 3)",
        "    bbox_max = mathutils.Vector((float('-inf'),) * 3)",
        "    for obj in imported_objs:",
        "        for corner in obj.bound_box:",
        "            world_pt = obj.matrix_world @ mathutils.Vector(corner)",
        "            for ax in range(3):",
        "                if world_pt[ax] < bbox_min[ax]: bbox_min[ax] = world_pt[ax]",
        "                if world_pt[ax] > bbox_max[ax]: bbox_max[ax] = world_pt[ax]",
        "",
        "    # 计算模型底部 Y 偏移（使模型站在地面上）",
        "    bottom_y = bbox_min.z",
        "    group_center = (bbox_min + bbox_max) / 2",
        "",
        "    loc = mathutils.Vector(mc['location'])",
        "    rot = mathutils.Euler(mc['rotation'])",
        "    scale = mc['scale']",
        "",
        "    for obj in imported_objs:",
        "        obj.location = (",
        "            loc.x + (obj.location.x - group_center.x) * scale,",
        "            loc.y + (obj.location.y - group_center.y) * scale,",
        "            loc.z + (obj.location.z - bottom_y) * scale,  # 底部对齐地面",
        "        )",
        "        obj.rotation_euler = (",
        "            obj.rotation_euler[0] + rot.x,",
        "            obj.rotation_euler[1] + rot.y,",
        "            obj.rotation_euler[2] + rot.z,",
        "        )",
        "        obj.scale = (obj.scale[0] * scale, obj.scale[1] * scale, obj.scale[2] * scale)",
        "",
        "    print(f'Model loaded: {model_name} ({len(imported_objs)} objects)')",
        "",
    ])

    # ── 角色导入 ──────────────────────────────────────────
    if has_character:
        lines.extend([
            "# ── 导入角色 ──────────────────────────────────",
            f"char_path = r'{characters_dir}/{params.character}'",
            "if not os.path.isfile(char_path):",
            "    raise FileNotFoundError('角色文件不存在: ' + char_path)",
            "",
            "bpy.ops.import_scene.fbx(",
            "    filepath=char_path,",
            "    use_anim=True,",
            "    automatic_bone_orientation=True,",
            "    ignore_leaf_bones=True,",
            f"    global_scale={params.character_scale},",
            ")",
            "",
            "char_armature = None",
            "char_meshes = []",
            "for obj in bpy.context.selected_objects:",
            "    if obj.type == 'ARMATURE':",
            "        char_armature = obj",
            "    elif obj.type == 'MESH':",
            "        char_meshes.append(obj)",
            "",
            "if char_armature is None:",
            "    raise RuntimeError('角色 FBX 中未找到 Armature')",
            "print('角色已导入: ' + char_armature.name)",
            "",
        ])

    # ── 相机 ──────────────────────────────────────────────
    lines.extend([
        "# ── 相机 ──────────────────────────────────────────",
        "cam_data = bpy.data.cameras.new(name='SceneCamera')",
        "camera = bpy.data.objects.new('SceneCamera', cam_data)",
        "bpy.context.scene.collection.objects.link(camera)",
        "bpy.context.scene.camera = camera",
        "",
    ])

    if has_custom_camera:
        lines.extend([
            f"camera.location = {json.dumps(params.camera_location)}",
        ])
        if params.camera_target:
            lines.extend([
                f"target = mathutils.Vector({json.dumps(params.camera_target)})",
                "direction = (mathutils.Vector(camera.location) - target).normalized()",
                "camera.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()",
            ])
        else:
            lines.append("camera.rotation_euler = (1.1, 0, 0)")
    else:
        # 动态取景：计算场景包围盒中心
        lines.extend([
            "# 动态取景",
            "scene_bbox_min = None",
            "scene_bbox_max = None",
            "for obj in bpy.context.scene.objects:",
            "    if obj.type == 'MESH':",
            "        for corner in obj.bound_box:",
            "            world = obj.matrix_world @ mathutils.Vector(corner)",
            "            if scene_bbox_min is None:",
            "                scene_bbox_min = mathutils.Vector(world)",
            "                scene_bbox_max = mathutils.Vector(world)",
            "            for ax in range(3):",
            "                if world[ax] < scene_bbox_min[ax]: scene_bbox_min[ax] = world[ax]",
            "                if world[ax] > scene_bbox_max[ax]: scene_bbox_max[ax] = world[ax]",
            "",
            "if scene_bbox_min is not None:",
            "    center = (scene_bbox_min + scene_bbox_max) / 2",
            "    scene_size = (scene_bbox_max - scene_bbox_min).length",
            "else:",
            "    center = mathutils.Vector((0, 0, 0.9))",
            "    scene_size = 1.8",
            "print(f'Scene center: {center}, size: {scene_size}')",
            "",
            "# 预设相机位置",
            "cam_presets = {",
            "    'front': (0, -3, 1.5),",
            "    'side': (3, 0, 1.5),",
            "    'three_quarter': (2.1, -2.1, 1.5),",
            "}",
            f"preset = {json.dumps(params.camera_preset)}",
            "base_offset = cam_presets.get(preset, (2.1, -2.1, 1.5))",
            "dist = max(scene_size * 0.8, 2.0)",
            "camera.location = (center.x + base_offset[0] * dist / 3,",
            "                   center.y + base_offset[1] * dist / 3,",
            "                   center.z + base_offset[2] * dist / 3)",
            "direction = (mathutils.Vector(camera.location) - center).normalized()",
            "camera.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()",
            "",
        ])

    # ── 渲染设置 ──────────────────────────────────────────
    lines.extend([
        "# ── 渲染设置 ──────────────────────────────────────",
        "scene = bpy.context.scene",
        "scene.render.engine = 'CYCLES'",
        "scene.cycles.device = 'GPU'",
        f"scene.render.resolution_x = {params.resolution}",
        f"scene.render.resolution_y = {params.resolution}",
        "scene.render.resolution_percentage = 100",
        f"scene.render.fps = {params.fps}",
        f"scene.cycles.samples = {params.samples}",
        f"scene.render.film_transparent = {str(params.transparent_bg)}",
        "",
        "scene.cycles.use_denoising = True",
        "try:",
        "    scene.cycles.denoiser = 'OPTIX'",
        "except Exception:",
        "    pass",
        "try:",
        "    scene.view_settings.view_transform = 'AgX'",
        "except Exception:",
        "    pass",
        "",
        "scene.cycles.max_bounces = 12",
        "scene.cycles.diffuse_bounces = 8",
        "scene.cycles.glossy_bounces = 8",
        "",
        "# GPU",
        "try:",
        "    prefs = bpy.context.preferences.addons['cycles'].preferences",
        "    prefs.get_devices()",
        "    prefs.compute_device_type = 'OPTIX'",
        "    for d in prefs.devices:",
        "        d.use = d.type != 'CPU'",
        "    bpy.ops.wm.save_userpref()",
        "except Exception:",
        "    pass",
        "",
    ])

    # ── 动画处理 + 渲染 ──────────────────────────────────
    if has_motions and has_character:
        lines.extend([
            "# ── 动画处理 + 渲染 ────────────────────────────",
            "motions = " + json.dumps(params.motions),
            "output_paths = []",
            "",
            "for motion_idx, motion_file in enumerate(motions):",
            f"    motion_path = r'{motions_dir}/' + motion_file",
            "    if not os.path.isfile(motion_path):",
            "        print('WARN: 动画文件不存在，跳过: ' + motion_path)",
            "        continue",
            "",
            "    bpy.ops.import_scene.fbx(",
            "        filepath=motion_path,",
            "        use_anim=True,",
            "        automatic_bone_orientation=True,",
            "        ignore_leaf_bones=True,",
            "    )",
            "",
            "    motion_armature = None",
            "    motion_action = None",
            "    imported_objects = list(bpy.context.selected_objects)",
            "    for obj in imported_objects:",
            "        if obj.type == 'ARMATURE':",
            "            motion_armature = obj",
            "            if obj.animation_data and obj.animation_data.action:",
            "                motion_action = obj.animation_data.action",
            "            break",
            "",
            "    if motion_action is None:",
            "        print('WARN: 未找到动画 Action: ' + motion_file)",
            "        for obj in imported_objects:",
            "            bpy.data.objects.remove(obj, do_unlink=True)",
            "        continue",
            "",
            "    motion_name = os.path.splitext(motion_file)[0]",
            "    new_action = motion_action.copy()",
            "    new_action.name = f'{char_armature.name}_{motion_name}'",
            "    if not char_armature.animation_data:",
            "        char_armature.animation_data_create()",
            "    char_armature.animation_data.action = new_action",
            "",
            "    frame_start = int(motion_action.frame_range[0])",
            "    frame_end = int(motion_action.frame_range[1])",
            "    scene.frame_start = frame_start",
            "    scene.frame_end = frame_end",
            "",
            "    # 清理动画临时对象",
            "    for obj in imported_objects:",
            "        if obj != char_armature and obj not in char_meshes:",
            "            bpy.data.objects.remove(obj, do_unlink=True)",
            "    if motion_action.users == 0:",
            "        bpy.data.actions.remove(motion_action)",
            "",
            "    # 渲染帧序列",
            "    if output_format in ('frames', 'both'):",
            f"        frames_dir = os.path.join(r'{output_dir}', scene_name + '_' + motion_name)",
            "        os.makedirs(frames_dir, exist_ok=True)",
            "        scene.render.image_settings.file_format = 'PNG'",
            "        scene.render.image_settings.color_mode = 'RGBA'",
            "        scene.render.filepath = os.path.join(frames_dir, '')",
        ])

        if has_follow:
            lines.extend([
                "        # 跟随模式",
                "        hips_bone = None",
                "        for bone in char_armature.pose.bones:",
                "            if 'Hips' in bone.name:",
                "                hips_bone = bone",
                "                break",
                "        base_cam = mathutils.Vector(camera.location)",
                "        for frame in range(frame_start, frame_end + 1):",
                "            scene.frame_set(frame)",
                "            if hips_bone:",
                "                hips_pos = char_armature.matrix_world @ hips_bone.head",
                "                camera.location = (hips_pos.x + base_cam.x, hips_pos.y + base_cam.y - 3, base_cam.z)",
                "            filepath = os.path.join(frames_dir, f'{{:04d}}.png'.format(frame))",
                "            scene.render.filepath = filepath",
                "            bpy.ops.render.render(write_still=True)",
            ])
        elif has_orbit:
            lines.extend([
                "        # 轨道模式",
                "        total = frame_end - frame_start",
                "        for fi, frame in enumerate(range(frame_start, frame_end + 1)):",
                "            scene.frame_set(frame)",
                "            angle = (fi / max(total, 1)) * 2 * math.pi",
                "            radius = 3.0",
                "            camera.location = (radius * math.sin(angle), -radius * math.cos(angle), 1.5)",
                "            camera.rotation_euler = (1.1, 0, angle)",
                "            filepath = os.path.join(frames_dir, f'{{:04d}}.png'.format(frame))",
                "            scene.render.filepath = filepath",
                "            bpy.ops.render.render(write_still=True)",
            ])
        else:
            lines.append("        bpy.ops.render.render(animation=True)")

        lines.extend([
            "        output_paths.append(frames_dir)",
            "        print(f'Frames rendered: {frames_dir}')",
            "",
            "    # 渲染视频",
            "    if output_format in ('video', 'both'):",
            f"        video_path = os.path.join(r'{output_dir}', scene_name + '_' + motion_name + '.mp4')",
            "        scene.render.image_settings.file_format = 'FFMPEG'",
            "        scene.render.ffmpeg.format = 'MPEG4'",
            "        scene.render.ffmpeg.codec = 'H264'",
            "        scene.render.ffmpeg.video_bitrate = 6000",
            "        scene.render.ffmpeg.gopsize = 12",
            "        scene.render.filepath = video_path",
            "        bpy.ops.render.render(animation=True)",
            "        output_paths.append(video_path)",
            "        print(f'Video rendered: {video_path}')",
            "",
            "    # 清除当前 Action",
            "    if char_armature.animation_data:",
            "        char_armature.animation_data.action = None",
            "",
        ])
    else:
        # 无动画：渲染单帧或多角度
        lines.extend([
            "# ── 渲染单帧 ────────────────────────────────────",
            "output_paths = []",
            "scene.render.image_settings.file_format = 'PNG'",
            "scene.render.image_settings.color_mode = 'RGBA'",
            "",
        ])

        if not has_custom_camera and params.camera_preset not in ("follow", "orbit"):
            # 多角度渲染：front, three_quarter, side
            lines.extend([
                "# 多角度渲染",
                "render_angles = {",
                "    'front': (0, -3, 1.5),",
                "    'three_quarter': (2.1, -2.1, 1.5),",
                "    'side': (3, 0, 1.5),",
                "}",
                f"default_angle = {json.dumps(params.camera_preset)}",
                "angles_to_render = {default_angle: render_angles.get(default_angle, (2.1, -2.1, 1.5))}",
                "",
                "for angle_name, offset in angles_to_render.items():",
                "    if scene_bbox_min is not None:",
                "        dist = max(scene_size * 0.8, 2.0)",
                "    else:",
                "        dist = 3.0",
                "    camera.location = (center.x + offset[0] * dist / 3,",
                "                       center.y + offset[1] * dist / 3,",
                "                       center.z + offset[2] * dist / 3)",
                "    direction = (mathutils.Vector(camera.location) - center).normalized()",
                "    camera.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()",
                "    filepath = os.path.join(output_dir, f'{scene_name}_{angle_name}.png')",
                "    scene.render.filepath = filepath",
                "    bpy.ops.render.render(write_still=True)",
                "    output_paths.append(filepath)",
                "    print(f'Rendered: {filepath}')",
            ])
        else:
            lines.extend([
                "filepath = os.path.join(output_dir, scene_name + '.png')",
                "scene.render.filepath = filepath",
                "bpy.ops.render.render(write_still=True)",
                "output_paths.append(filepath)",
                "print('Rendered: ' + filepath)",
            ])

    lines.extend([
        "",
        "print('SCENE_RENDER_COMPLETE')",
        "print(json.dumps(output_paths))",
    ])

    return "\n".join(lines)
