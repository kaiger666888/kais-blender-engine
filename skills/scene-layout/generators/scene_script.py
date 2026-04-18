"""场景布局生成器 v2 — 生成自包含的 Blender 执行脚本

一个函数生成完整脚本，避免变量作用域问题。
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field


@dataclass
class SceneRequest:
    """场景请求"""
    characters: List[Dict] = field(default_factory=list)
    furniture: List[str] = field(default_factory=list)
    hdri: str = ""
    camera_shots: List[str] = field(default_factory=lambda: ["wide", "medium", "closeup"])
    output_dir: str = r"D:\BlenderAgent\outputs"


def generate_full_scene_script(request: SceneRequest) -> str:
    """
    生成完整的自包含 Blender Python 脚本。
    所有变量在同一个作用域内，无跨段引用问题。
    """
    # 构建 character placements
    char_blocks = []
    for ci, char in enumerate(request.characters):
        anim = char.get("animation", "")
        target = char.get("position", "").replace("on:", "").strip()
        clr = char.get("clearance", 0.05)
        char_blocks.append((anim, target, clr))
    
    # 构建 camera shots
    shots = request.camera_shots or ["wide", "medium", "closeup"]
    shot_params = {
        "extreme_wide": (-4.5, -4.5, 2.8),
        "wide": (-3.5, -3.5, 2.5),
        "medium": (-2.0, -2.5, 1.8),
        "closeup": (-1.2, -1.6, 1.3),
        "extreme_closeup": (-0.8, -1.0, 1.0),
    }
    
    lines = []
    a = lines.append
    
    # ═══ Header ═══
    a("import bpy, sys, mathutils")
    a("sys.stderr.write('[scene-layout] Starting...\\\\n')")
    a("")
    
    # ═══ get_aabb ═══
    a("def get_aabb(obj):")
    a("    corners = [obj.matrix_world @ mathutils.Vector(c) for c in obj.bound_box]")
    a("    xs=[c.x for c in corners]; ys=[c.y for c in corners]; zs=[c.z for c in corners]")
    a("    return mathutils.Vector((min(xs),min(ys),min(zs))), mathutils.Vector((max(xs),max(ys),max(zs)))")
    a("")
    
    # ═══ Open base scene ═══
    a("bpy.ops.wm.open_mainfile(filepath=r'D:\\BlenderAgent\\cache\\full_scene.blend')")
    a("sys.stderr.write('[scene-layout] Base scene loaded\\\\n')")
    a("")
    
    # ═══ Assemble furniture components ═══
    a("# ── Assemble furniture components ──")
    a("for obj in bpy.context.scene.objects:")
    a("    if obj.type != 'MESH': continue")
    a("    # sofa: seat onto base")
    a("    if 'sofa_02_seat' in obj.name.lower():")
    a("        base = next((o for o in bpy.context.scene.objects if 'sofa_02_base' in o.name.lower() and o.type=='MESH'), None)")
    a("        if base:")
    a("            b_mn, b_mx = get_aabb(base)")
    a("            s_mn, s_mx = get_aabb(obj)")
    a("            if s_mn.z < b_mx.z - 0.01:")
    a("                obj.location.z += b_mx.z - s_mn.z")
    a("                bpy.context.view_layer.update()")
    a("                sys.stderr.write(f'  Assembled {obj.name} onto base: z=[{s_mn.z + b_mx.z - s_mn.z:.2f}]\\\\n')")
    a("")
    
    # ═══ Characters ═══
    for ci, (anim, target, clr) in enumerate(char_blocks):
        a(f"# ── Character {ci+1}: {anim} ──")
        a("# Clear old characters")
        a("to_del = [o for o in bpy.context.scene.objects if o.type == 'ARMATURE' or (o.type == 'MESH' and 'Beta' in o.name)]")
        a("for obj in to_del:")
        a("    bpy.data.objects.remove(obj, do_unlink=True)")
        a("")
        a(f"bpy.ops.import_scene.fbx(filepath=r'{anim}', use_anim=True)")
        a("arm = next((o for o in bpy.context.scene.objects if o.type == 'ARMATURE'), None)")
        a("if arm and arm.animation_data:")
        a("    bpy.context.scene.frame_set(1)")
        a("    bpy.context.view_layer.update()")
        a("")
        a("# Collect character AABB")
        a("c_mn, c_mx = get_aabb(arm)")
        a("for m in bpy.context.scene.objects:")
        a("    if m.type == 'MESH' and m.parent and m.parent.type == 'ARMATURE':")
        a("        mn, mx = get_aabb(m)")
        a("        for ax in range(3):")
        a("            if mn[ax] < c_mn[ax]: c_mn[ax] = mn[ax]")
        a("            if mx[ax] > c_mx[ax]: c_mx[ax] = mx[ax]")
        a(f"sys.stderr.write(f'  Char {ci+1}: z=[{{c_mn.z:.2f}},{{c_mx.z:.2f}}] h={{c_mx.z-c_mn.z:.2f}}\\\\n')")
        a("")
        
        if target:
            a(f"# Place on {target}")
            a("furniture = None")
            a(f"for obj in bpy.context.scene.objects:")
            a(f"    if obj.type == 'MESH' and '{target.lower()}' in obj.name.lower():")
            a("        furniture = obj")
            a("        break")
            a("if furniture:")
            a("    f_mn, f_mx = get_aabb(furniture)")
            a("    seat_top = f_mx.z")
            a("    sit_region = c_mn.z + (c_mx.z - c_mn.z) * 0.40")
            a(f"    delta_z = seat_top + {clr} - sit_region")
            a("    seat_cy = (f_mn.y + f_mx.y) / 2")
            a("    char_cy = (c_mn.y + c_mx.y) / 2")
            a("    delta_y = seat_cy - char_cy")
            a(f"    sys.stderr.write(f'  Placing on {{furniture.name}}: dz={{delta_z:.3f}} dy={{delta_y:.3f}}\\\\n')")
            a("    arm.location.z += delta_z")
            a("    arm.location.y += delta_y")
            a("    bpy.context.view_layer.update()")
            a("else:")
            a(f"    sys.stderr.write('  WARNING: {target} not found\\\\n')")
            a("")
    
    # ═══ HDRI ═══
    if request.hdri:
        a("# ── HDRI ──")
        a("world = bpy.context.scene.world or bpy.data.worlds.new('World')")
        a("bpy.context.scene.world = world")
        a("world.use_nodes = True")
        a("bg = world.node_tree.nodes.get('Background')")
        a("if bg:")
        a(f"    env = world.node_tree.nodes.new(type='ShaderNodeTexEnvironment')")
        a(f"    env.image = bpy.data.images.load(r'D:\\BlenderAgent\\assets\\polyhaven\\hdris\\{request.hdri}.hdr')")
        a("    world.node_tree.links.new(env.outputs[0], bg.inputs[0])")
        a("    bg.inputs[1].default_value = 1.0")
        a("")
    
    # ═══ Camera + Render ═══
    a("# ── Camera + Render ──")
    a("cam = next((o for o in bpy.context.scene.objects if o.type == 'CAMERA'), None)")
    a("if not cam:")
    a("    cam = bpy.data.objects.new('Camera', bpy.data.cameras.new('Camera'))")
    a("    bpy.context.scene.collection.objects.link(cam)")
    a("bpy.context.scene.camera = cam")
    a("")
    a("# Scene AABB")
    a("amn = amx = None")
    a("for obj in bpy.context.scene.objects:")
    a("    if obj.type in ('MESH','ARMATURE') and obj.name != 'Floor':")
    a("        mn, mx = get_aabb(obj)")
    a("        if amn is None: amn, amx = mn, mx")
    a("        else:")
    a("            amn = mathutils.Vector((min(amn.x,mn.x),min(amn.y,mn.y),min(amn.z,mn.z)))")
    a("            amx = mathutils.Vector((max(amx.x,mx.x),max(amx.y,mx.y),max(amx.z,mx.z)))")
    a("ctr = (amn + amx) / 2")
    a("def pt(c, t):")
    a("    d = mathutils.Vector(t) - c.location")
    a("    c.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()")
    a("")
    a("scene = bpy.context.scene")
    a("scene.render.engine = 'CYCLES'")
    a("scene.cycles.device = 'GPU'")
    a("scene.render.resolution_x = 1280")
    a("scene.render.resolution_y = 720")
    a("scene.cycles.samples = 128")
    a("")
    
    for shot in shots:
        params = shot_params.get(shot, shot_params["medium"])
        ox, oy, oz = params
        a(f"cam.location = ctr + mathutils.Vector(({ox}, {oy}, {oz}))")
        a("pt(cam, ctr)")
        a(f"scene.render.filepath = r'{request.output_dir}\\\\scene_{shot}.png'")
        a("bpy.ops.render.render(write_still=True)")
        a(f"sys.stderr.write(f'[OK] {shot}\\\\n')")
        a("")
    
    a("bpy.ops.wm.save_as_mainfile(filepath=r'D:\\BlenderAgent\\cache\\scene_layout.blend')")
    a("print('DONE')")
    
    return "\n".join(lines)
