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
    """生成 Blender Python 脚本 - 使用 MPFB2 HumanService API 程序化角色建模"""

    angles_config = get_camera_angles(params.camera_preset, params.custom_angles)
    angles_json = json.dumps(angles_config)

    # 计算 MPFB macro_detail 值
    gender_val = 0.5 + params.mass * 0.5 if params.gender == "male" else 0.5 - params.mass * 0.5
    age_val = min(1.0, max(0.0, (params.age - 18) / 62.0))
    height_val = min(1.0, max(0.0, (params.height - 1.4) / 0.6))

    # 种族默认 universal（均匀混合）
    macro_json = json.dumps({
        "race": {"african": 0.33, "asian": 0.33, "caucasian": 0.33},
        "gender": gender_val,
        "age": age_val,
        "muscle": 0.3 + params.mass * 0.7,
        "weight": 0.3 + params.mass * 0.4,
        "height": height_val,
        "proportions": 0.5,
        "cupsize": 0.5,
        "firmness": 0.5,
    })

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
        "# 手动添加 mpfb 模块路径（兼容 4.0/5.1 addons 目录）",
        "mpfb_found = False",
        "for ver in ['5.1', '5.0', '4.0']:",
        "    mpfb_path = os.path.join(os.path.expanduser('~'), 'AppData', 'Roaming', 'Blender Foundation', 'Blender', ver, 'scripts', 'addons')",
        "    if os.path.isdir(mpfb_path):",
        "        sys.path.insert(0, mpfb_path)",
        "        if os.path.isdir(os.path.join(mpfb_path, 'mpfb')):",
        "            mpfb_found = True",
        '            print("Found mpfb in: " + mpfb_path)',
        "            break",
        "",
        "# 使用 MPFB2 HumanService API 创建角色",
        "character_obj = None",
        "use_mpfb = False",
        "if mpfb_found:",
        "    try:",
        "        import mpfb",
        "        # 在 headless 模式下手动注册 MPFB",
        "        if mpfb.MPFB_CONTEXTUAL_INFORMATION is None:",
        "            mpfb.MPFB_CONTEXTUAL_INFORMATION = {",
        '                "__package_short__": "mpfb",',
        '                "__package__": "mpfb",',
        '                "__package_path__": os.path.join(sys.path[0], "mpfb"),',
        "            }",
        "            mpfb.register()",
        '            print("MPFB register() called in headless mode")',
        "        from mpfb.services.HumanService import HumanService",
        "        from mpfb.services.MaterialService import MaterialService",
        "        use_mpfb = True",
        '        print("MPFB2 模块加载成功")',
        "    except Exception as e:",
        '        print("MPFB2 import 失败: " + str(e))',
        '        import traceback; traceback.print_exc()',
        "",
        "if use_mpfb:",
        "    try:",
        "        macro_details = " + macro_json,
        "",
        "        basemesh = HumanService.create_human(",
        "            feet_on_ground=True,",
        "            scale=0.1,",
        "            macro_detail_dict=macro_details",
        "        )",
        "        character_obj = basemesh",
        '        print("MPFB2 角色生成成功: " + str(type(basemesh)))',
        "",
        "        try:",
        "            MaterialService.assign_default_skin(basemesh)",
        '            print("默认皮肤已应用")',
        "        except Exception as e:",
        '            print("皮肤跳过: " + str(e))',
        "",
        "    except Exception as e:",
        '        print("MPFB2_CREATE_ERROR: " + str(e))',
        '        import traceback; traceback.print_exc()',
        "        use_mpfb = False",
        "",
        "if not use_mpfb or character_obj is None:",
        '    print("使用几何体降级方案")',
        "    bpy.ops.mesh.primitive_cylinder_add(radius=0.3, depth=1.7, location=(0, 0, 0.85))",
        "    body = bpy.context.object",
        '    body.name = "Body"',
        "",
        "    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.25, location=(0, 0, 1.9))",
        "    head = bpy.context.object",
        '    head.name = "Head"',
        "",
        "    bpy.ops.object.select_all(action='DESELECT')",
        "    body.select_set(True)",
        "    head.select_set(True)",
        "    bpy.context.view_layer.objects.active = body",
        "    bpy.ops.object.join()",
        "    character_obj = bpy.context.object",
        "",
        "# 创建相机",
        'cam_data = bpy.data.cameras.new(name="Camera")',
        'camera = bpy.data.objects.new("Camera", cam_data)',
        "bpy.context.scene.collection.objects.link(camera)",
        "bpy.context.scene.camera = camera",
        "",
        "# 渲染设置",
        "scene = bpy.context.scene",
        "scene.render.engine = 'CYCLES'",
        "scene.cycles.device = 'GPU'",
        f"scene.render.resolution_x = {params.resolution}",
        f"scene.render.resolution_y = {params.resolution}",
        "scene.render.resolution_percentage = 100",
        "",
        "# 启用 GPU",
        "try:",
        "    prefs = bpy.context.preferences.addons['cycles'].preferences",
        "    prefs.get_devices()",
        "    for d in prefs.devices:",
        '        if "NVIDIA" in d.name or "RTX" in d.name:',
        "            d.use = True",
        '            print("启用 GPU: " + d.name)',
        "except:",
        "    pass",
        "",
        "# 多角度渲染",
        f"angles = {angles_json}",
        "output_paths = []",
        "",
        "for i, cfg in enumerate(angles):",
        "    camera.location = cfg['location']",
        "    camera.rotation_euler = cfg['rotation']",
        "",
        "    angle_name = cfg.get('name', 'angle_' + str(i))",
        f'    filepath = r"{OUTPUT_DIR}/{params.preset_name}_" + angle_name + ".png"',
        "    scene.render.filepath = filepath",
        "",
        "    bpy.ops.render.render(write_still=True)",
        "    output_paths.append(filepath)",
        '    print("渲染完成: " + filepath)',
        "",
        "# 保存 blend 文件",
        f'bpy.ops.wm.save_as_mainfile(filepath=r"{CACHE_DIR}/{params.preset_name}.blend")',
        "",
        'print("CHARACTER_GENERATION_COMPLETE")',
        "print(json.dumps(output_paths))",
    ]
    return "\n".join(script_lines)
