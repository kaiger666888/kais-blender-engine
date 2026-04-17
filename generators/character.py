import json
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from camera_presets import CameraPreset, get_camera_angles
from config import CACHE_DIR, OUTPUT_DIR


# ── 体型预设 ──────────────────────────────────────────────

BODY_TYPE_PRESETS = {
    "slim": {"muscle": 0.2, "weight": 0.2},
    "average": {"muscle": 0.5, "weight": 0.5},
    "athletic": {"muscle": 0.8, "weight": 0.4},
    "heavy": {"muscle": 0.4, "weight": 0.8},
}

RACE_PRESETS = {
    "african": {"african": 1.0, "asian": 0.0, "caucasian": 0.0},
    "asian": {"african": 0.0, "asian": 1.0, "caucasian": 0.0},
    "caucasian": {"african": 0.0, "asian": 0.0, "caucasian": 1.0},
    "mixed": {"african": 0.33, "asian": 0.33, "caucasian": 0.33},
}

LIGHTING_PRESETS = {
    "studio": {
        "bg_color": (0.15, 0.15, 0.18),
        "lights": [
            {"type": "AREA", "location": (2, -2, 2.5), "energy": 800, "color": (1.0, 0.95, 0.9), "size": 2.0},
            {"type": "AREA", "location": (-1.5, -1.5, 1.8), "energy": 300, "color": (0.9, 0.95, 1.0), "size": 1.5},
            {"type": "AREA", "location": (0, 2, 2.5), "energy": 500, "color": (1.0, 1.0, 1.0), "size": 1.0},
        ],
    },
    "dramatic": {
        "bg_color": (0.02, 0.02, 0.03),
        "lights": [
            {"type": "AREA", "location": (3, -1, 2), "energy": 1200, "color": (1.0, 0.9, 0.7), "size": 1.5},
            {"type": "AREA", "location": (-2, -2, 1), "energy": 80, "color": (0.6, 0.7, 1.0), "size": 1.0},
        ],
    },
    "soft": {
        "bg_color": (0.6, 0.6, 0.65),
        "lights": [
            {"type": "AREA", "location": (0, -3, 2.5), "energy": 600, "color": (1.0, 1.0, 1.0), "size": 4.0},
        ],
    },
    "neon": {
        "bg_color": (0.02, 0.02, 0.05),
        "lights": [
            {"type": "AREA", "location": (3, 0, 2), "energy": 1000, "color": (1.0, 0.0, 0.8), "size": 1.5},
            {"type": "AREA", "location": (-3, 0, 2), "energy": 1000, "color": (0.0, 0.9, 1.0), "size": 1.5},
            {"type": "AREA", "location": (0, -2, 2.5), "energy": 300, "color": (1.0, 1.0, 1.0), "size": 2.0},
        ],
    },
}


class CharacterParams(BaseModel):
    """角色生成参数"""
    preset_name: str = Field(..., description="输出文件名，如 'hero_001'")
    gender: Literal["male", "female"] = "male"
    height: float = Field(1.75, ge=1.4, le=2.0)
    mass: float = Field(0.5, ge=0.0, le=1.0, description="肌肉量/体重 0-1")
    age: int = Field(25, ge=18, le=80)
    race: Literal["african", "asian", "caucasian", "mixed"] = "mixed"
    body_type: Literal["slim", "average", "athletic", "heavy"] = "average"
    muscle: float = Field(0.5, ge=0.0, le=1.0, description="肌肉量覆盖")
    weight: float = Field(0.5, ge=0.0, le=1.0, description="体重覆盖")
    style: Literal["realistic", "anime", "lowpoly"] = "realistic"
    camera_preset: CameraPreset = CameraPreset.STANDARD_8
    custom_angles: Optional[List[float]] = None
    resolution: int = 1024
    lighting_preset: Literal["studio", "dramatic", "soft", "neon"] = "studio"
    samples: int = Field(256, ge=32, le=2048, description="Cycles 采样数")
    transparent_bg: bool = False


def _build_macro_details(params: CharacterParams) -> dict:
    """将 API 参数映射为 MPFB2 macro_detail_dict"""
    gender_val = 1.0 if params.gender == "male" else 0.0
    age_val = min(1.0, max(0.0, (params.age - 18) / 62.0))
    height_val = min(1.0, max(0.0, (params.height - 1.4) / 0.6))

    # body_type 预设可被 muscle/weight 显式参数覆盖
    preset = BODY_TYPE_PRESETS[params.body_type]
    muscle = params.muscle if params.muscle != 0.5 else preset["muscle"]
    weight = params.weight if params.weight != 0.5 else preset["weight"]

    return {
        "race": RACE_PRESETS[params.race],
        "gender": gender_val,
        "age": age_val,
        "muscle": muscle,
        "weight": weight,
        "height": height_val,
        "proportions": 0.5,
        "cupsize": 0.5,
        "firmness": 0.5,
    }


def generate_character_script(params: CharacterParams) -> str:
    """生成 Blender Python 脚本 - 使用 MPFB2 HumanService API"""

    angles_config = get_camera_angles(params.camera_preset, params.custom_angles)
    angles_json = json.dumps(angles_config)
    macro_json = json.dumps(_build_macro_details(params))
    lighting = LIGHTING_PRESETS[params.lighting_preset]
    lights_json = json.dumps(lighting["lights"])
    bg_color = lighting["bg_color"]

    script_lines = [
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
        "character_obj = None",
        "use_mpfb = False",
        "if mpfb_found:",
        "    try:",
        "        # Blender 5.x 兼容: monkey-patch extension_path_user",
        "        # MPFB2 的 locationservice 在模块加载时调用此函数",
        "        # Blender 5.x 对非 extension 包会抛 ValueError",
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
        "        from mpfb.services.humanservice import HumanService",
        "        from mpfb.services.materialservice import MaterialService",
        "        use_mpfb = True",
        '        print("MPFB2 loaded")',
        "    except Exception as e:",
        "        import traceback",
        '        print("MPFB2 import failed: " + str(e))',
        "        traceback.print_exc()",
        "",
        "# ── 角色生成 ──────────────────────────────────────",
        "if use_mpfb:",
        "    try:",
        "        macro_details = " + macro_json,
        "        basemesh = HumanService.create_human(feet_on_ground=True, scale=0.1, macro_detail_dict=macro_details)",
        "        character_obj = basemesh",
        '        print("MPFB2 character created")',
        "        try:",
        "            MaterialService.assign_default_skin(basemesh)",
        "        except Exception:",
        "            pass",
        "    except Exception as e:",
        '        print("MPFB2 create error: " + str(e))',
        "        use_mpfb = False",
        "",
        "if not use_mpfb or character_obj is None:",
        '    print("Fallback to primitives")',
        "    bpy.ops.mesh.primitive_cylinder_add(radius=0.3, depth=1.7, location=(0, 0, 0.85))",
        "    body = bpy.context.object",
        '    body.name = "Body"',
        "    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.25, location=(0, 0, 1.9))",
        "    head = bpy.context.object",
        '    head.name = "Head"',
        "    bpy.ops.object.select_all(action='DESELECT')",
        "    body.select_set(True)",
        "    head.select_set(True)",
        "    bpy.context.view_layer.objects.active = body",
        "    bpy.ops.object.join()",
        "    character_obj = bpy.context.object",
        "",
        "# ── 地面（阴影捕捉）──────────────────────────────",
        "bpy.ops.mesh.primitive_plane_add(size=6, location=(0, 0, 0))",
        "ground = bpy.context.object",
        'ground.name = "Ground"',
        "ground_mat = bpy.data.materials.new(name='ShadowCatcher')",
        "ground_mat.use_nodes = True",
        "ground_mat.node_tree.nodes['Principled BSDF'].inputs['Alpha'].default_value = 0.0",
        "ground_mat.blend_method = 'OPAQUE' if hasattr(ground_mat, 'blend_method') else None",
        "try:",
        "    ground.is_shadow_catcher = True",
        "except (AttributeError, Exception):",
        "    try:",
        "        ground.cycles.is_shadow_catcher = True",
        "    except (AttributeError, Exception):",
        "        pass",
        "ground.data.materials.append(ground_mat)",
        "",
        "# ── 专业灯光 ──────────────────────────────────────",
        f"bg_color = {bg_color}",
        "lights_config = " + lights_json,
        "for lc in lights_config:",
        "    bpy.ops.object.light_add(type=lc['type'], location=lc['location'])",
        "    lt = bpy.context.object",
        "    lt.data.energy = lc['energy']",
        "    lt.data.color = lc['color']",
        "    if hasattr(lt.data, 'size'):",
        "        lt.data.size = lc.get('size', 1.0)",
        "",
        "# 世界背景",
        "world = bpy.data.worlds.new(name='World')",
        "bpy.context.scene.world = world",
        "world.use_nodes = True",
        "bg_node = world.node_tree.nodes['Background']",
        "bg_node.inputs[0].default_value = bg_color + (1,)",
        "bg_node.inputs[1].default_value = 1",
        "",
        "# ── 相机 ──────────────────────────────────────────",
        'cam_data = bpy.data.cameras.new(name="Camera")',
        'camera = bpy.data.objects.new("Camera", cam_data)',
        "bpy.context.scene.collection.objects.link(camera)",
        "bpy.context.scene.camera = camera",
        "",
        "# ── 渲染设置 ──────────────────────────────────────",
        "scene = bpy.context.scene",
        "scene.render.engine = 'CYCLES'",
        "scene.cycles.device = 'GPU'",
        f"scene.render.resolution_x = {params.resolution}",
        f"scene.render.resolution_y = {params.resolution}",
        "scene.render.resolution_percentage = 100",
        f"scene.cycles.samples = {params.samples}",
        f"scene.render.film_transparent = {str(params.transparent_bg)}",
        "",
        "# 降噪 + 色调映射",
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
        "# 光路弹射",
        "scene.cycles.max_bounces = 12",
        "scene.cycles.diffuse_bounces = 8",
        "scene.cycles.glossy_bounces = 8",
        "",
        "# GPU",
        "try:",
        "    prefs = bpy.context.preferences.addons['cycles'].preferences",
        "    prefs.get_devices()",
        "    for d in prefs.devices:",
        '        if "NVIDIA" in d.name or "RTX" in d.name:',
        "            d.use = True",
        "except Exception:",
        "    pass",
        "",
        "# ── 多角度渲染 ────────────────────────────────────",
        f"angles = {angles_json}",
        "output_paths = []",
        "",
        "for i, cfg in enumerate(angles):",
        "    camera.location = cfg['location']",
        "    camera.rotation_euler = cfg['rotation']",
        "    angle_name = cfg.get('name', 'angle_' + str(i))",
        f'    filepath = r"{OUTPUT_DIR}/{params.preset_name}_" + angle_name + ".png"',
        "    scene.render.filepath = filepath",
        "    bpy.ops.render.render(write_still=True)",
        "    output_paths.append(filepath)",
        '    print("Rendered: " + filepath)',
        "",
        "# 保存 blend",
        f'bpy.ops.wm.save_as_mainfile(filepath=r"{CACHE_DIR}/{params.preset_name}.blend")',
        "",
        'print("CHARACTER_GENERATION_COMPLETE")',
        "print(json.dumps(output_paths))",
    ]
    return "\n".join(script_lines)
