"""端到端测试：Mixamo FBX → 动画应用 → 渲染全流程

覆盖完整管线：
  1. 角色 FBX 导入（骨骼 + 网格）
  2. 动画 FBX 导入 + Action 提取
  3. Action 复制到角色骨骼
  4. 动态取景（bounding box 相机）
  5. 灯光 + 地面
  6. EEVEE 渲染（验证可用性）
  7. Cycles 渲染（诊断 headless 纯色问题）
  8. 输出验证（文件存在 / 非零 / 非纯色）

用法:
    blender -b -P scripts/test_e2e_mixamo.py
    blender -b -P scripts/test_e2e_mixamo.py -- --motion Walking.fbx
"""

import bpy
import gpu
import json
import math
import mathutils
import os
import sys
import time
from pathlib import Path

# ── 配置 ────────────────────────────────────────────────
CHARACTERS_DIR = Path(r"D:/BlenderAgent/animations/characters")
MOTIONS_DIR = Path(r"D:/BlenderAgent/animations/motions")
OUTPUT_DIR = Path(r"D:/BlenderAgent/outputs/e2e_test")

DEFAULT_CHARACTER = "x_bot_tpose.fbx"
DEFAULT_MOTION = None  # 自动取第一个
RESOLUTION = 512
CYCLES_SAMPLES = 64  # 快速验证用低采样


def parse_args():
    """解析 -- 之后的自定义参数"""
    args = {"character": DEFAULT_CHARACTER, "motion": DEFAULT_MOTION}
    if "--" in sys.argv:
        custom = sys.argv[sys.argv.index("--") + 1:]
        i = 0
        while i < len(custom):
            if custom[i] == "--character" and i + 1 < len(custom):
                args["character"] = custom[i + 1]
                i += 2
            elif custom[i] == "--motion" and i + 1 < len(custom):
                args["motion"] = custom[i + 1]
                i += 2
            else:
                i += 1
    return args


def pick_motion(motion_arg):
    """自动选择可用的动画文件（跳过损坏文件）"""
    if motion_arg:
        path = MOTIONS_DIR / motion_arg
        if path.is_file():
            return path
        raise FileNotFoundError(f"指定动画不存在: {path}")
    # 自动找第一个能成功导入的
    for fbx in sorted(MOTIONS_DIR.glob("*.fbx")):
        # 跳过已知损坏文件
        if "basic_rock_beat" in fbx.name:
            continue
        # 快速检测：导入测试
        try:
            bpy.ops.wm.read_homefile()
            bpy.ops.import_scene.fbx(filepath=str(fbx))
            # 恢复空场景
            bpy.ops.wm.read_homefile()
            return fbx
        except Exception:
            continue
    raise FileNotFoundError(f"无可用动画文件: {MOTIONS_DIR}")


# ── 场景清理 ────────────────────────────────────────────
def clean_scene():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    for block in bpy.data.meshes:
        if block.users == 0:
            bpy.data.meshes.remove(block)
    for block in bpy.data.armatures:
        if block.users == 0:
            bpy.data.armatures.remove(block)
    for block in bpy.data.actions:
        if block.users == 0:
            bpy.data.actions.remove(block)
    for block in bpy.data.cameras:
        if block.users == 0:
            bpy.data.cameras.remove(block)
    for block in bpy.data.lights:
        if block.users == 0:
            bpy.data.lights.remove(block)
    for block in bpy.data.materials:
        if block.users == 0:
            bpy.data.materials.remove(block)
    for block in bpy.data.worlds:
        if block.users == 0:
            bpy.data.worlds.remove(block)


# ── 步骤 1：导入角色 ────────────────────────────────────
def import_character(char_path):
    print(f"\n[1] 导入角色: {char_path.name}")
    bpy.ops.import_scene.fbx(
        filepath=str(char_path),
        use_anim=True,
        automatic_bone_orientation=True,
        ignore_leaf_bones=True,
    )

    armature = None
    meshes = []
    for obj in bpy.context.selected_objects:
        if obj.type == 'ARMATURE':
            armature = obj
        elif obj.type == 'MESH':
            meshes.append(obj)

    assert armature is not None, "角色 FBX 中未找到 Armature"
    bone_count = len(armature.data.bones)
    vert_count = sum(len(m.data.vertices) for m in meshes)
    print(f"    Armature: {armature.name} ({bone_count} bones)")
    print(f"    Meshes: {len(meshes)}, Vertices: {vert_count}")
    return armature, meshes


# ── 步骤 2：导入动画 + 提取 Action ──────────────────────
def import_motion(motion_path, char_armature):
    print(f"\n[2] 导入动画: {motion_path.name}")
    bpy.ops.import_scene.fbx(
        filepath=str(motion_path),
        use_anim=True,
        automatic_bone_orientation=True,
        ignore_leaf_bones=True,
    )

    motion_armature = None
    motion_action = None
    imported = list(bpy.context.selected_objects)
    for obj in imported:
        if obj.type == 'ARMATURE':
            motion_armature = obj
            if obj.animation_data and obj.animation_data.action:
                motion_action = obj.animation_data.action
            break

    assert motion_action is not None, "动画 FBX 中未找到 Action"

    frame_start = int(motion_action.frame_range[0])
    frame_end = int(motion_action.frame_range[1])
    print(f"    Action: {motion_action.name} ({frame_start}-{frame_end} frames)")

    # 复制 Action 到角色骨骼
    new_action = motion_action.copy()
    new_action.name = f"{char_armature.name}_{motion_path.stem}"
    if not char_armature.animation_data:
        char_armature.animation_data_create()
    char_armature.animation_data.action = new_action

    # 设置帧范围
    scene = bpy.context.scene
    scene.frame_start = frame_start
    scene.frame_end = frame_end

    # 清理导入的临时对象（保留 Action 副本）
    for obj in imported:
        if obj != char_armature:
            bpy.data.objects.remove(obj, do_unlink=True)
    if motion_action.users == 0:
        bpy.data.actions.remove(motion_action)

    print(f"    Action 已应用到角色骨骼: {new_action.name}")
    return new_action, frame_start, frame_end


# ── 步骤 3：场景设置（灯光 + 地面 + 相机）──────────────
def setup_scene(char_armature, meshes):
    print("\n[3] 场景设置")
    scene = bpy.context.scene

    # ── 地面 ──
    bpy.ops.mesh.primitive_plane_add(size=10, location=(0, 0, 0))
    ground = bpy.context.object
    ground.name = "Ground"
    ground_mat = bpy.data.materials.new(name='ShadowCatcher')
    ground_mat.use_nodes = True
    ground_mat.node_tree.nodes['Principled BSDF'].inputs['Alpha'].default_value = 0.0
    try:
        ground.is_shadow_catcher = True
    except (AttributeError, Exception):
        try:
            ground.cycles.is_shadow_catcher = True
        except (AttributeError, Exception):
            pass
    ground.data.materials.append(ground_mat)

    # ── 灯光（studio preset）──
    lights_config = [
        {"type": "AREA", "location": (2, -2, 2.5), "energy": 800,
         "color": (1.0, 0.95, 0.9), "size": 2.0},
        {"type": "AREA", "location": (-1.5, -1.5, 1.8), "energy": 300,
         "color": (0.9, 0.95, 1.0), "size": 1.5},
        {"type": "AREA", "location": (0, 2, 2.5), "energy": 500,
         "color": (1.0, 1.0, 1.0), "size": 1.0},
    ]
    for lc in lights_config:
        bpy.ops.object.light_add(type=lc['type'], location=lc['location'])
        lt = bpy.context.object
        lt.data.energy = lc['energy']
        lt.data.color = lc['color']
        if hasattr(lt.data, 'size'):
            lt.data.size = lc.get('size', 1.0)

    # ── 世界背景 ──
    world = bpy.data.worlds.new(name='TestWorld')
    scene.world = world
    world.use_nodes = True
    bg_node = world.node_tree.nodes['Background']
    bg_node.inputs[0].default_value = (0.15, 0.15, 0.18, 1)
    bg_node.inputs[1].default_value = 1

    # ── 相机：动态取景 ──
    bbox_min = None
    bbox_max = None
    for obj in meshes:
        for corner in obj.bound_box:
            world_pt = obj.matrix_world @ mathutils.Vector(corner)
            if bbox_min is None:
                bbox_min = mathutils.Vector(world_pt)
                bbox_max = mathutils.Vector(world_pt)
            for ax in range(3):
                if world_pt[ax] < bbox_min[ax]:
                    bbox_min[ax] = world_pt[ax]
                if world_pt[ax] > bbox_max[ax]:
                    bbox_max[ax] = world_pt[ax]

    center = (bbox_min + bbox_max) / 2
    size = (bbox_max - bbox_min).length
    dist = size * 1.8
    print(f"    BBox center: ({center.x:.2f}, {center.y:.2f}, {center.z:.2f}), "
          f"size: {size:.2f}, cam_dist: {dist:.2f}")

    cam_data = bpy.data.cameras.new(name="TestCamera")
    camera = bpy.data.objects.new("TestCamera", cam_data)
    scene.collection.objects.link(camera)
    scene.camera = camera

    # 三角位（正面偏 45°）
    dx, dy = 1.4, -1.4
    camera.location = (
        center.x + dx * dist / 1.8,
        center.y + dy * dist / 1.8,
        center.z + 0.6 * dist / 1.8,
    )

    # 使用 look_at 方法（to_track_quat）确保相机正确朝向目标
    cam_to_target = center - mathutils.Vector(camera.location)
    cam_to_target.normalize()
    # Blender 相机默认朝 -Z，up 是 +Y
    rot_quat = cam_to_target.to_track_quat('-Z', 'Y')
    camera.rotation_euler = rot_quat.to_euler()

    print(f"    Camera: loc={tuple(round(v, 2) for v in camera.location)}, "
          f"rot={tuple(round(v, 2) for v in camera.rotation_euler)}")


# ── 步骤 4：GPU 诊断 ────────────────────────────────────
def diagnose_gpu():
    print("\n[4] GPU 诊断")
    gpu_info = {"cycles_devices": [], "gpu_backend": "unknown"}

    try:
        prefs = bpy.context.preferences.addons['cycles'].preferences
        prefs.get_devices()
        for d in prefs.devices:
            gpu_info["cycles_devices"].append({
                "name": d.name,
                "type": d.type,
                "use": d.use,
            })
            print(f"    Device: {d.name} (type={d.type}, use={d.use})")
    except Exception as e:
        print(f"    Cycles preferences 读取失败: {e}")

    try:
        gpu_info["gpu_backend"] = gpu.platform.backend_type_get()
        gpu_info["renderer"] = gpu.platform.renderer_get()
        gpu_info["vendor"] = gpu.platform.vendor_get()
        print(f"    GPU Backend: {gpu_info['gpu_backend']}")
        print(f"    Renderer: {gpu_info['renderer']}")
        print(f"    Vendor: {gpu_info['vendor']}")
    except Exception as e:
        print(f"    GPU info 读取失败: {e}")

    return gpu_info


# ── 步骤 5：渲染 ────────────────────────────────────────
def render_frame(engine, frame, suffix, extra_setup=None):
    """渲染单帧并返回输出路径"""
    scene = bpy.context.scene
    scene.frame_set(frame)
    scene.render.engine = engine
    scene.render.resolution_x = RESOLUTION
    scene.render.resolution_y = RESOLUTION
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGBA'
    scene.render.film_transparent = False

    if extra_setup:
        extra_setup(scene)

    filepath = str(OUTPUT_DIR / f"test_{suffix}.png")
    scene.render.filepath = filepath
    t0 = time.time()
    bpy.ops.render.render(write_still=True)
    elapsed = time.time() - t0
    return filepath, elapsed


def diagnose_before_render(char_armature, camera):
    """渲染前诊断：检查骨骼位置、相机朝向、射线检测"""
    print("\n[DIAG] 渲染前诊断")

    # 1. 关键骨骼世界坐标
    scene = bpy.context.scene
    key_bones = ["mixamorig:Head", "mixamorig:Hips", "mixamorig:LeftFoot",
                 "mixamorig:RightFoot", "mixamorig:Spine"]
    print("    骨骼世界坐标:")
    for bname in key_bones:
        bone = char_armature.pose.bones.get(bname)
        if bone:
            mat = char_armature.matrix_world @ bone.matrix
            loc = mat.to_translation()
            print(f"      {bname}: ({loc.x:.3f}, {loc.y:.3f}, {loc.z:.3f})")
        else:
            print(f"      {bname}: 未找到")

    # 2. 相机矩阵
    cam_world = camera.matrix_world
    cam_loc = cam_world.to_translation()
    cam_forward = -cam_world.to_quaternion() @ mathutils.Vector((0, 0, 1))
    print(f"    相机位置: ({cam_loc.x:.3f}, {cam_loc.y:.3f}, {cam_loc.z:.3f})")
    print(f"    相机朝向 (-Z): ({cam_forward.x:.3f}, {cam_forward.y:.3f}, {cam_forward.z:.3f})")

    # 3. 从相机向场景中心射线检测
    cam_pos = mathutils.Vector(camera.location)
    scene_center = mathutils.Vector((0, 0, 1))  # 角色大概位置
    direction = (scene_center - cam_pos).normalized()
    hit, location, normal, index, obj, matrix = bpy.context.scene.ray_cast(
        bpy.context.evaluated_depsgraph_get(), cam_pos, direction
    )
    if hit:
        print(f"    射线检测: HIT! obj={obj.name}, loc=({location.x:.3f}, {location.y:.3f}, {location.z:.3f})")
    else:
        print(f"    射线检测: MISS (从相机向场景中心方向无碰撞)")

    # 4. 所有 mesh 对象 bounding box
    print("    场景物体:")
    for obj in bpy.context.scene.objects:
        if obj.type == 'MESH':
            bb_min = mathutils.Vector((float('inf'),) * 3)
            bb_max = mathutils.Vector((float('-inf'),) * 3)
            for corner in obj.bound_box:
                world_pt = obj.matrix_world @ mathutils.Vector(corner)
                for ax in range(3):
                    bb_min[ax] = min(bb_min[ax], world_pt[ax])
                    bb_max[ax] = max(bb_max[ax], world_pt[ax])
            print(f"      {obj.name}: ({bb_min.x:.2f},{bb_min.y:.2f},{bb_min.z:.2f}) - "
                  f"({bb_max.x:.2f},{bb_max.y:.2f},{bb_max.z:.2f})")



    scene.eevee.taa_render_samples = 32


def setup_eevee(scene):
    scene.eevee.taa_render_samples = 32


def setup_cycles(scene):
    scene.cycles.samples = CYCLES_SAMPLES
    scene.cycles.device = 'GPU'
    scene.cycles.use_denoising = True
    try:
        scene.cycles.denoiser = 'OPTIX'
    except Exception:
        pass
    scene.cycles.max_bounces = 8
    scene.cycles.diffuse_bounces = 4
    scene.cycles.glossy_bounces = 4
    try:
        scene.view_settings.view_transform = 'AgX'
    except Exception:
        pass
    # 显式启用 GPU
    try:
        prefs = bpy.context.preferences.addons['cycles'].preferences
        prefs.get_devices()
        for d in prefs.devices:
            if 'NVIDIA' in d.name or 'RTX' in d.name or d.type == 'CUDA':
                d.use = True
    except Exception:
        pass


def setup_cycles_cpu(scene):
    """Cycles CPU fallback"""
    scene.cycles.samples = CYCLES_SAMPLES
    scene.cycles.device = 'CPU'
    scene.cycles.use_denoising = True
    scene.cycles.max_bounces = 8


# ── 步骤 6：输出验证 ────────────────────────────────────
def validate_render(filepath):
    """验证渲染结果：存在、非零大小、非纯色"""
    issues = []

    if not os.path.isfile(filepath):
        return {"valid": False, "issues": ["文件不存在"]}

    file_size = os.path.getsize(filepath)
    if file_size < 1000:
        issues.append(f"文件过小 ({file_size} bytes)")

    # 通过 Blender 的图像加载验证像素
    try:
        img = bpy.data.images.load(filepath)
        p = img.pixels[:]
        channels = img.channels
        pixel_count = len(p) // channels
        if pixel_count == 0:
            issues.append("图像无像素数据")
            bpy.data.images.remove(img)
            return {"valid": len(issues) == 0, "issues": issues, "file_size": file_size}

        # 采样 10 个像素点，检查是否全同色
        sample_indices = [int(i * pixel_count / 10) for i in range(10)]
        colors = []
        for idx in sample_indices:
            r = p[idx * channels]
            g = p[idx * channels + 1]
            b = p[idx * channels + 2]
            colors.append((round(r, 3), round(g, 3), round(b, 3)))

        unique_colors = set(colors)
        if len(unique_colors) == 1:
            issues.append(f"纯色图像: {colors[0]}")

        bpy.data.images.remove(img)
    except Exception as e:
        issues.append(f"图像验证失败: {e}")

    return {"valid": len(issues) == 0, "issues": issues, "file_size": file_size}


# ── 主流程 ──────────────────────────────────────────────
def main():
    args = parse_args()
    char_path = CHARACTERS_DIR / args["character"]
    motion_path = pick_motion(args["motion"])

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("Mixamo FBX → Render 端到端测试")
    print("=" * 60)
    print(f"角色: {char_path}")
    print(f"动画: {motion_path}")
    print(f"输出: {OUTPUT_DIR}")

    results = {}

    # 清理
    clean_scene()

    # 1. 导入角色
    try:
        armature, meshes = import_character(char_path)
        results["import_character"] = "PASS"
    except Exception as e:
        results["import_character"] = f"FAIL: {e}"
        print(f"    FAIL: {e}")
        _print_report(results)
        return

    # 2. 导入动画
    try:
        action, frame_start, frame_end = import_motion(motion_path, armature)
        results["import_motion"] = "PASS"
    except Exception as e:
        results["import_motion"] = f"FAIL: {e}"
        print(f"    FAIL: {e}")
        _print_report(results)
        return

    # 3. 场景设置
    try:
        setup_scene(armature, meshes)
        results["scene_setup"] = "PASS"
    except Exception as e:
        results["scene_setup"] = f"FAIL: {e}"
        print(f"    FAIL: {e}")
        _print_report(results)
        return

    # 4. GPU 诊断
    gpu_info = diagnose_gpu()
    results["gpu_info"] = gpu_info

    # 4b. 渲染前诊断
    camera = bpy.data.objects.get("TestCamera")
    if camera:
        diagnose_before_render(armature, camera)

    # 测试帧（取动画中间帧）
    test_frame = (frame_start + frame_end) // 2

    # 5a. EEVEE 渲染
    print(f"\n[5a] EEVEE 渲染 (frame {test_frame})")
    try:
        filepath_eevee, t_eevee = render_frame(
            'BLENDER_EEVEE', test_frame, "eevee", setup_eevee
        )
        v = validate_render(filepath_eevee)
        results["eevee"] = {
            "status": "PASS" if v["valid"] else "FAIL",
            "filepath": filepath_eevee,
            "time": round(t_eevee, 2),
            "validation": v,
        }
        print(f"    {'PASS' if v['valid'] else 'FAIL'}: {filepath_eevee} "
              f"({v.get('file_size', 0)} bytes, {t_eevee:.1f}s)")
        if v["issues"]:
            for issue in v["issues"]:
                print(f"    ISSUE: {issue}")
    except Exception as e:
        results["eevee"] = {"status": f"FAIL: {e}"}
        print(f"    FAIL: {e}")

    # 5b. Cycles GPU 渲染
    print(f"\n[5b] Cycles GPU 渲染 (frame {test_frame})")
    try:
        filepath_cg, t_cg = render_frame(
            'CYCLES', test_frame, "cycles_gpu", setup_cycles
        )
        v = validate_render(filepath_cg)
        results["cycles_gpu"] = {
            "status": "PASS" if v["valid"] else "FAIL",
            "filepath": filepath_cg,
            "time": round(t_cg, 2),
            "validation": v,
        }
        print(f"    {'PASS' if v['valid'] else 'FAIL'}: {filepath_cg} "
              f"({v.get('file_size', 0)} bytes, {t_cg:.1f}s)")
        if v["issues"]:
            for issue in v["issues"]:
                print(f"    ISSUE: {issue}")
    except Exception as e:
        results["cycles_gpu"] = {"status": f"FAIL: {e}"}
        print(f"    FAIL: {e}")

    # 5c. Cycles CPU 渲染（GPU 失败时的 fallback）
    if results.get("cycles_gpu", {}).get("status") != "PASS":
        print(f"\n[5c] Cycles CPU fallback 渲染 (frame {test_frame})")
        try:
            filepath_cc, t_cc = render_frame(
                'CYCLES', test_frame, "cycles_cpu", setup_cycles_cpu
            )
            v = validate_render(filepath_cc)
            results["cycles_cpu"] = {
                "status": "PASS" if v["valid"] else "FAIL",
                "filepath": filepath_cc,
                "time": round(t_cc, 2),
                "validation": v,
            }
            print(f"    {'PASS' if v['valid'] else 'FAIL'}: {filepath_cc} "
                  f"({v.get('file_size', 0)} bytes, {t_cc:.1f}s)")
            if v["issues"]:
                for issue in v["issues"]:
                    print(f"    ISSUE: {issue}")
        except Exception as e:
            results["cycles_cpu"] = {"status": f"FAIL: {e}"}
            print(f"    FAIL: {e}")

    # 6. 保存报告
    _print_report(results)

    report_path = OUTPUT_DIR / "e2e_report.json"
    with open(report_path, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n报告已保存: {report_path}")


def _print_report(results):
    print("\n" + "=" * 60)
    print("测试报告")
    print("=" * 60)
    all_pass = True
    for step, info in results.items():
        if step == "gpu_info":
            continue
        if isinstance(info, str):
            status = info
        elif isinstance(info, dict):
            status = info.get("status", "UNKNOWN")
        else:
            status = str(info)
        marker = "OK" if status == "PASS" else "XX"
        if status != "PASS":
            all_pass = False
        print(f"  [{marker}] {step}: {status}")

    print(f"\n总结果: {'ALL PASS' if all_pass else 'HAS FAILURES'}")
    print("=" * 60)


if __name__ == "__main__":
    main()
