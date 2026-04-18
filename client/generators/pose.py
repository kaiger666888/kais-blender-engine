"""姿态渲染脚本生成器

通过 /run/script 发送 Blender Python 脚本到 Windows 端执行。
加载角色 .blend，设置骨骼姿态（FK 旋转 + IK 约束），渲染输出。
"""

import json
from typing import Dict, List, Optional, Tuple

from camera_presets import CameraPreset, get_camera_angles


# ── 默认路径（Windows 端）─────────────────────────────────
DEFAULT_OUTPUT_DIR = "D:/BlenderAgent/outputs"
DEFAULT_CACHE_DIR = "D:/BlenderAgent/cache"

# Mixamo 骨骼 IK 链默认配置（与 ik_presets.py 保持一致）
_DEFAULT_IK_CHAINS = {
    "mixamorig:LeftHand": 3,
    "mixamorig:RightHand": 3,
    "mixamorig:LeftFoot": 3,
    "mixamorig:RightFoot": 3,
    "mixamorig:LeftHandThumb2": 2,
    "mixamorig:RightHandThumb2": 2,
    "mixamorig:Head": 3,
}


def generate_pose_script(
    preset_name: str,
    bone_rotations: Optional[Dict[str, Tuple[float, float, float]]] = None,
    ik_targets: Optional[Dict[str, Tuple[float, float, float]]] = None,
    ik_chain_counts: Optional[Dict[str, int]] = None,
    action_name: Optional[str] = None,
    camera_preset: CameraPreset = CameraPreset.FRONT,
    custom_angles: Optional[list] = None,
    resolution: int = 1024,
    samples: int = 256,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    cache_dir: str = DEFAULT_CACHE_DIR,
) -> str:
    """生成姿态渲染脚本

    加载已绑定的角色 .blend，设置骨骼姿态（FK + IK），渲染输出。
    FK 和 IK 可同时使用：先应用 FK 旋转，再叠加 IK 约束。

    Args:
        preset_name: 角色名（对应 cache_dir/{preset_name}.blend）
        bone_rotations: FK 骨骼旋转字典 {bone_name: (rx, ry, rz)}
        ik_targets: IK 目标位置 {末端骨骼: (x, y, z)}
        ik_chain_counts: IK 链长度覆盖 {末端骨骼: chain_count}，默认使用内置配置
        action_name: 切换到指定 NLA action（与 bone_rotations 二选一）
        camera_preset: 相机预设
        custom_angles: 自定义相机角度
        resolution: 渲染分辨率
        samples: Cycles 采样数
        output_dir: 渲染输出目录
        cache_dir: .blend 文件目录
    """
    angles_json = json.dumps(get_camera_angles(camera_preset, custom_angles))
    bones_json = json.dumps(bone_rotations or {})
    ik_json = json.dumps(ik_targets or {})
    chains_json = json.dumps(ik_chain_counts or {})

    has_ik = bool(ik_targets)

    lines = [
        "import bpy",
        "import json",
        "import sys",
        "import os",
        "import math",
        "import mathutils",
        "",
        "# ── 加载角色包 ──────────────────────────────────────",
        'blend_path = r"' + cache_dir + "/" + preset_name + '.blend"',
        'print("Loading blend: " + blend_path)',
        "bpy.ops.wm.open_mainfile(filepath=blend_path)",
        "",
        "# ── 查找 Armature ──────────────────────────────────",
        "armature = None",
        "for obj in bpy.context.scene.objects:",
        "    if obj.type == 'ARMATURE':",
        "        armature = obj",
        "        break",
        "",
        "if armature is None:",
        '    print("ERROR: No armature found in blend file")',
        '    print("POSE_RENDER_COMPLETE")',
        "    print(json.dumps([]))",
        "",
        "else:",
        "    bpy.context.view_layer.objects.active = armature",
        "    bpy.ops.object.mode_set(mode='POSE')",
        "",
        "    # ── FK: 设置骨骼旋转 ────────────────────────────",
    ]

    # Action 切换
    if action_name:
        lines.append('    action_name = "' + action_name + '"')
        lines.extend([
            "    found_action = None",
            "    if armature.animation_data:",
            "        for act in bpy.data.actions:",
            '            if act.name == action_name or action_name.lower() in act.name.lower():',
            "                found_action = act",
            "                break",
            "    if found_action:",
            "        armature.animation_data.action = found_action",
            '        print("Switched to action: " + found_action.name)',
            "    else:",
            '        print("WARNING: Action not found, using bone rotations")',
        ])

    # FK 骨骼旋转
    lines.append("    bone_rotations = " + bones_json)
    lines.extend([
        "    for bone_name, rot in bone_rotations.items():",
        "        pose_bone = armature.pose.bones.get(bone_name)",
        "        if pose_bone:",
        "            pose_bone.rotation_mode = 'XYZ'",
        "            pose_bone.rotation_euler = rot",
        '            print("FK: " + bone_name + " -> " + str(rot))',
        "        else:",
        '            print("WARNING: Bone not found: " + bone_name)',
        "",
    ])

    # IK 约束设置（保留约束直到渲染结束，无需烘焙）
    if has_ik:
        lines.extend([
            "    # ── IK: 设置反向运动学约束 ────────────────────",
            "    ik_targets = " + ik_json,
            "    custom_chains = " + chains_json,
            "    default_chains = " + json.dumps(_DEFAULT_IK_CHAINS),
            "",
            "    for bone_name, target_pos in ik_targets.items():",
            "        pose_bone = armature.pose.bones.get(bone_name)",
            "        if pose_bone is None:",
            '            print("WARNING: IK bone not found: " + bone_name)',
            "            continue",
            "",
            "        # 创建 IK 目标空物体",
            "        empty_name = 'IK_' + bone_name.replace(':', '_')",
            "        empty = bpy.data.objects.new(empty_name, None)",
            "        bpy.context.scene.collection.objects.link(empty)",
            "        empty.empty_display_type = 'SPHERE'",
            "        empty.empty_display_size = 0.03",
            "        empty.location = mathutils.Vector(target_pos)",
            "",
            "        # 添加 IK 约束到末端骨骼",
            "        ik_constraint = pose_bone.constraints.new('IK')",
            "        ik_constraint.target = empty",
            "        chain_count = custom_chains.get(bone_name, default_chains.get(bone_name, 2))",
            "        ik_constraint.chain_count = chain_count",
            '        print("IK: " + bone_name + " -> " + str(target_pos) + " chain=" + str(chain_count))',
            "",
            "    # 退出 Pose Mode，触发 depsgraph 求解 IK",
            "    bpy.ops.object.mode_set(mode='OBJECT')",
            "    bpy.context.view_layer.update()",
            "    for _ in range(3):",
            "        bpy.context.evaluated_depsgraph_get().update()",
            '    print("IK solved.")',
            "",
        ])
    else:
        lines.extend([
            "    bpy.ops.object.mode_set(mode='OBJECT')",
            "",
        ])

    # ── 灯光、地面、相机、渲染（从原逻辑不变）─────────────────
    lines.extend([
        "    # ── 灯光 ──────────────────────────────────────────",
        '    if not any(l.type == "LIGHT" for l in bpy.context.scene.objects):',
        '        bpy.ops.object.light_add(type="AREA", location=(2, -2, 2.5))',
        "        lt = bpy.context.object",
        "        lt.data.energy = 800",
        "        lt.data.color = (1.0, 0.95, 0.9)",
        "        if hasattr(lt.data, 'size'):",
        "            lt.data.size = 2.0",
        "        bpy.ops.object.light_add(type='AREA', location=(-1.5, -1.5, 1.8))",
        "        lt2 = bpy.context.object",
        "        lt2.data.energy = 300",
        "        lt2.data.color = (0.9, 0.95, 1.0)",
        "        if hasattr(lt2.data, 'size'):",
        "            lt2.data.size = 1.5",
        "",
        "    # ── 地面 ──────────────────────────────────────────",
        '    if not any(o.name == "Ground" for o in bpy.context.scene.objects):',
        "        bpy.ops.mesh.primitive_plane_add(size=6, location=(0, 0, 0))",
        "        ground = bpy.context.object",
        '        ground.name = "Ground"',
        "        ground_mat = bpy.data.materials.new(name='ShadowCatcher')",
        "        ground_mat.use_nodes = True",
        "        ground_mat.node_tree.nodes['Principled BSDF'].inputs['Alpha'].default_value = 0.0",
        "        try:",
        "            ground.is_shadow_catcher = True",
        "        except (AttributeError, Exception):",
        "            try:",
        "                ground.cycles.is_shadow_catcher = True",
        "            except (AttributeError, Exception):",
        "                pass",
        "        ground.data.materials.append(ground_mat)",
        "",
        "    # ── 相机（动态取景） ──────────────────────────────",
        "    bbox_min = None",
        "    bbox_max = None",
        "    for obj in bpy.context.scene.objects:",
        "        if obj.type == 'MESH':",
        "            for corner in obj.bound_box:",
        "                world = obj.matrix_world @ mathutils.Vector(corner)",
        "                if bbox_min is None:",
        "                    bbox_min = mathutils.Vector(world)",
        "                    bbox_max = mathutils.Vector(world)",
        "                for ax in range(3):",
        "                    if world[ax] < bbox_min[ax]: bbox_min[ax] = world[ax]",
        "                    if world[ax] > bbox_max[ax]: bbox_max[ax] = world[ax]",
        "",
        "    if bbox_min is not None:",
        "        center = (bbox_min + bbox_max) / 2",
        "        size = (bbox_max - bbox_min).length",
        "        print('Character bbox center: ' + str(center) + ' size: ' + str(size))",
        "    else:",
        "        center = mathutils.Vector((0, 0, 0.9))",
        "        size = 1.8",
        "        print('WARNING: No mesh found, using default framing')",
        "",
        '    camera = None',
        '    for obj in bpy.context.scene.objects:',
        '        if obj.type == "CAMERA":',
        '            camera = obj',
        '            break',
        '    if camera is None:',
        '        cam_data = bpy.data.cameras.new(name="Camera")',
        '        camera = bpy.data.objects.new("Camera", cam_data)',
        '        bpy.context.scene.collection.objects.link(camera)',
        "    bpy.context.scene.camera = camera",
        "",
        "    # ── 渲染设置 ──────────────────────────────────────",
        "    scene = bpy.context.scene",
        "    scene.render.engine = 'CYCLES'",
        "    scene.cycles.device = 'GPU'",
        "    scene.render.resolution_x = " + str(resolution),
        "    scene.render.resolution_y = " + str(resolution),
        "    scene.render.resolution_percentage = 100",
        "    scene.cycles.samples = " + str(samples),
        "    scene.cycles.use_denoising = True",
        "    try:",
        "        scene.cycles.denoiser = 'OPTIX'",
        "    except Exception:",
        "        pass",
        "    scene.cycles.max_bounces = 12",
        "    try:",
        "        scene.view_settings.view_transform = 'AgX'",
        "    except Exception:",
        "        pass",
        "    try:",
        "        prefs = bpy.context.preferences.addons['cycles'].preferences",
        "        prefs.get_devices()",
        "        prefs.compute_device_type = 'OPTIX'",
        "        for d in prefs.devices:",
        "            d.use = d.type != 'CPU'",
        "        bpy.ops.wm.save_userpref()",
        "    except Exception:",
        "        pass",
        "",
        "    # ── 多角度渲染 ────────────────────────────────────",
        "    angles = " + angles_json,
        "    output_paths = []",
        "    dist = size * 1.8",
        "",
        "    for i, cfg in enumerate(angles):",
        "        orig_loc = cfg['location']",
        "        dx, dy, dz = orig_loc[0], orig_loc[1], orig_loc[2] - 0.9",
        "        camera.location = (center.x + dx * dist / 1.8,",
        "                           center.y + dy * dist / 1.8,",
        "                           center.z + dz * dist / 1.8)",
        "        direction = (mathutils.Vector(camera.location) - center).normalized()",
        "        rot_x = math.atan2(direction.z, math.sqrt(direction.x**2 + direction.y**2))",
        "        rot_z = math.atan2(direction.x, direction.y)",
        "        camera.rotation_euler = (rot_x, 0, rot_z)",
        "        angle_name = cfg.get('name', 'angle_' + str(i))",
        '        filepath = r"' + output_dir + "/" + preset_name + '_" + angle_name + ".png"',
        "        scene.render.filepath = filepath",
        "        bpy.ops.render.render(write_still=True)",
        "        output_paths.append(filepath)",
        '        print("Rendered: " + filepath)',
        "",
        '    print("POSE_RENDER_COMPLETE")',
        "    print(json.dumps(output_paths))",
    ])
    return "\n".join(lines)
