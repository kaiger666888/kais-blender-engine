"""骨骼绑定与姿态渲染脚本生成器

通过 /run/script 发送 Blender Python 脚本到 Windows 端执行。
核心功能:
  - generate_rigged_character_script(): 生成带骨骼绑定的角色包 (.blend)
  - generate_pose_script(): 加载角色包并渲染指定姿态
"""

import json
from typing import Dict, Optional, Tuple

from camera_presets import CameraPreset, get_camera_angles


# ── 默认路径（Windows 端）─────────────────────────────────
DEFAULT_OUTPUT_DIR = "D:/BlenderAgent/outputs"
DEFAULT_CACHE_DIR = "D:/BlenderAgent/cache"
DEFAULT_RIG_FILE = "rig.default.json"
DEFAULT_WEIGHTS_FILE = "weights.default.json"
DEFAULT_RIG_SYSTEM = "standard"


def generate_rigged_character_script(
    preset_name: str,
    macro_details: dict,
    rig_file: str = DEFAULT_RIG_FILE,
    weights_file: str = DEFAULT_WEIGHTS_FILE,
    rig_system: str = DEFAULT_RIG_SYSTEM,
    cache_dir: str = DEFAULT_CACHE_DIR,
) -> str:
    """生成带骨骼绑定的角色 .blend 文件

    Args:
        preset_name: 角色名，用于文件命名
        macro_details: MPFB2 macro_detail_dict（体型参数）
        rig_file: 骨骼 JSON 文件名（rig.default.json 或 rig.mixamo.json）
        weights_file: 权重文件名
        rig_system: 骨骼系统目录名
        cache_dir: .blend 保存目录
    """
    macro_json = json.dumps(macro_details)

    lines = [
        "import bpy",
        "import json",
        "import sys",
        "import os",
        "",
        "# 清理场景",
        "bpy.ops.object.select_all(action='SELECT')",
        "bpy.ops.object.delete(use_global=False)",
        "",
        "# ── MPFB2 初始化 ────────────────────────────────────",
        "mpfb_found = False",
        "mpfb_addons_path = None",
        "for ver in ['5.1', '5.0', '4.0']:",
        "    mpfb_path = os.path.join(os.path.expanduser('~'), 'AppData', 'Roaming', 'Blender Foundation', 'Blender', ver, 'scripts', 'addons')",
        "    if os.path.isdir(mpfb_path):",
        "        if os.path.isdir(os.path.join(mpfb_path, 'mpfb')):",
        "            mpfb_addons_path = mpfb_path",
        "            sys.path.insert(0, mpfb_path)",
        "            mpfb_found = True",
        '            print("Found mpfb in: " + mpfb_path)',
        "            break",
        "",
        "rigged = False",
        "if mpfb_found:",
        "    try:",
        "        _orig_ext_path_user = getattr(bpy.utils, 'extension_path_user', None)",
        "        if _orig_ext_path_user is not None:",
        "            def _safe_ext_path_user(pkg, path='', repo=None):",
        "                try:",
        "                    return _orig_ext_path_user(pkg, path=path, repo=repo)",
        "                except (ValueError, Exception):",
        "                    user_base = os.path.join(os.path.expanduser('~'), 'AppData', 'Roaming', 'Blender Foundation', 'Blender')",
        "                    if os.path.isdir(user_base):",
        "                        for d in sorted(os.listdir(user_base), reverse=True):",
        "                            ext_dir = os.path.join(user_base, d, 'extensions', pkg)",
        "                            if os.path.isdir(ext_dir):",
        "                                return os.path.join(ext_dir, path) if path else ext_dir",
        "                    fallback = os.path.join(os.path.expanduser('~'), 'AppData', 'Roaming', 'Blender Foundation', 'mpfb_user')",
        "                    return os.path.join(fallback, path) if path else fallback",
        "            bpy.utils.extension_path_user = _safe_ext_path_user",
        "",
        "        import mpfb",
        "        if mpfb.MPFB_CONTEXTUAL_INFORMATION is None:",
        "            import addon_utils",
        "            addon_utils.enable('mpfb', default_set=True)",
        "        if mpfb.MPFB_CONTEXTUAL_INFORMATION is None:",
        "            mpfb.MPFB_CONTEXTUAL_INFORMATION = {",
        '                "__package_short__": "mpfb",',
        '                "__package__": "mpfb",',
        '                "__package_path__": os.path.join(mpfb_addons_path, "mpfb"),',
        "            }",
        "",
        "        from mpfb.services.humanservice import HumanService",
        "        from mpfb.services.materialservice import MaterialService",
        "        from mpfb.services.rigservice import RigService",
        "        from mpfb.entities.rig import Rig",
        "",
        '        print("MPFB2 loaded, creating rigged character...")',
        "",
        "        # 创建 basemesh",
        "        macro_details = " + macro_json,
        "        basemesh = HumanService.create_human(feet_on_ground=True, scale=0.1, macro_detail_dict=macro_details)",
        "        try:",
        "            MaterialService.assign_default_skin(basemesh)",
        "        except Exception:",
        "            pass",
        "",
        "        # 加载骨骼",
        '        rig_json_path = os.path.join(mpfb_addons_path, "mpfb", "data", "rigs", "' + rig_system + '", "' + rig_file + '")',
        '        print("Loading rig from: " + rig_json_path)',
        "        rig = Rig.from_json_file_and_basemesh(rig_json_path, basemesh)",
        "        armature = rig.get_armature_object()",
        '        print("Rig loaded, armature: " + armature.name)',
        "",
        "        # 加载权重",
        '        weights_path = os.path.join(mpfb_addons_path, "mpfb", "data", "rigs", "' + rig_system + '", "' + weights_file + '")',
        '        print("Loading weights from: " + weights_path)',
        "        RigService.load_weights(rig, weights_path)",
        '        print("Weights loaded")',
        "",
        "        # 保存角色包",
        '        blend_path = r"' + cache_dir + "/" + preset_name + '.blend"',
        "        bpy.ops.wm.save_as_mainfile(filepath=blend_path)",
        '        print("Rigged character saved to: " + blend_path)',
        "        rigged = True",
        "",
        "    except Exception as e:",
        "        import traceback",
        '        print("Rigging failed: " + str(e))',
        "        traceback.print_exc()",
        "",
        "if not rigged:",
        '    print("ERROR: Rigging failed, no output")',
        "",
        'print("RIGGED_CHARACTER_COMPLETE")',
    ]
    return "\n".join(lines)


def generate_pose_script(
    preset_name: str,
    bone_rotations: Optional[Dict[str, Tuple[float, float, float]]] = None,
    action_name: Optional[str] = None,
    camera_preset: CameraPreset = CameraPreset.FRONT,
    custom_angles: Optional[list] = None,
    resolution: int = 1024,
    samples: int = 256,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    cache_dir: str = DEFAULT_CACHE_DIR,
) -> str:
    """生成姿态渲染脚本

    加载已绑定的角色 .blend，设置骨骼姿态，渲染输出。

    Args:
        preset_name: 角色名（对应 cache_dir/{preset_name}.blend）
        bone_rotations: 骨骼旋转字典 {bone_name: (rx, ry, rz)}
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

    lines = [
        "import bpy",
        "import json",
        "import sys",
        "import os",
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
        "    # 空结果",
        "    print(json.dumps([]))",
        "",
        "else:",
        "    # 确保处于 pose mode",
        "    bpy.context.view_layer.objects.active = armature",
        "    bpy.ops.object.mode_set(mode='POSE')",
        "",
        "    # ── 设置骨骼旋转 ──────────────────────────────────",
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

    # 骨骼旋转设置
    lines.append("    bone_rotations = " + bones_json)
    lines.extend([
        "    for bone_name, rot in bone_rotations.items():",
        "        pose_bone = armature.pose.bones.get(bone_name)",
        "        if pose_bone:",
        "            pose_bone.rotation_mode = 'XYZ'",
        "            pose_bone.rotation_euler = rot",
        '            print("Set bone: " + bone_name + " -> " + str(rot))',
        "        else:",
        '            print("WARNING: Bone not found: " + bone_name)',
        "",
        "    bpy.ops.object.mode_set(mode='OBJECT')",
        "",
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
        "    # ── 相机 ──────────────────────────────────────────",
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
        "        for d in prefs.devices:",
        '            if "NVIDIA" in d.name or "RTX" in d.name:',
        "                d.use = True",
        "    except Exception:",
        "        pass",
        "",
        "    # ── 多角度渲染 ────────────────────────────────────",
        "    angles = " + angles_json,
        "    output_paths = []",
        "",
        "    for i, cfg in enumerate(angles):",
        "        camera.location = cfg['location']",
        "        camera.rotation_euler = cfg['rotation']",
        "        angle_name = cfg.get('name', 'angle_' + str(i))",
        '        filepath = r"' + output_dir + "/" + preset_name + '_" + angle_name + ".png"',
        "        scene.render.filepath = filepath",
        "        bpy.ops.render.render(write_still=True)",
        "        output_paths.append(filepath)",
        '        print("Rendered: " + filepath)',
        "",
        '    print("POSE_RENDER_COMPLETE")',
        "    print(json.dumps(output_paths))",
    ]
    return "\n".join(lines)
