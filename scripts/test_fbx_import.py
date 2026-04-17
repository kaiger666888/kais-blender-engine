"""Headless 测试：验证 Mixamo FBX 能否在 Blender 中正常导入。"""
import bpy
import sys
import json
from pathlib import Path

LIBRARY = Path(r"E:\KaisProject\kais-blender\mixamo_library")

results = []

fbx_files = sorted(LIBRARY.rglob("*.fbx"))
print(f"找到 {len(fbx_files)} 个 FBX 文件\n")

for fbx in fbx_files:
    rel = fbx.relative_to(LIBRARY)
    # 清空场景
    bpy.ops.wm.read_homefile()

    try:
        bpy.ops.import_scene.fbx(filepath=str(fbx))
        objs = bpy.context.selected_objects
        armatures = [o for o in objs if o.type == 'ARMATURE']
        meshes = [o for o in objs if o.type == 'MESH']
        actions = list(bpy.data.actions)

        # 检查骨骼层级
        bone_count = 0
        if armatures:
            bone_count = len(armatures[0].data.bones)

        # 检查动画帧范围
        frame_range = (0, 0)
        if actions:
            frame_range = (int(actions[0].frame_range[0]), int(actions[0].frame_range[1]))

        info = {
            "file": str(rel),
            "status": "OK",
            "armatures": len(armatures),
            "meshes": len(meshes),
            "bones": bone_count,
            "actions": len(actions),
            "frames": f"{frame_range[0]}-{frame_range[1]}",
            "vertices": sum(len(m.data.vertices) for m in meshes) if meshes else 0,
        }
        print(f"  OK  {rel}")
        print(f"      armatures={len(armatures)} meshes={len(meshes)} bones={bone_count} "
              f"actions={len(actions)} frames={frame_range[0]}-{frame_range[1]} "
              f"verts={info['vertices']}")

    except Exception as e:
        info = {"file": str(rel), "status": f"FAIL: {e}"}
        print(f"  FAIL  {rel}: {e}")

    results.append(info)

# 汇总
ok = [r for r in results if r["status"] == "OK"]
fail = [r for r in results if r["status"] != "OK"]
print(f"\n{'='*60}")
print(f"结果: {len(ok)}/{len(results)} 成功, {len(fail)} 失败")
if fail:
    for f in fail:
        print(f"  FAIL: {f['file']} — {f['status']}")
