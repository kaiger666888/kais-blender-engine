---
name: kais-blender-engine
version: 0.1.0
description: "Blender 渲染引擎客户端。通过 HTTP API 远程调用 Windows 端 Blender 执行动画渲染、姿态渲染、场景渲染、资产管理。触发词：blender engine, 渲染引擎, blender客户端, 动画渲染, 姿态渲染, 角色渲染, render animation, pose render, blender api, blenderrun, 跑blender, 提交渲染"
---

# kais-blender-engine — Blender 渲染引擎客户端

> Linux 端通过 HTTP 远程调用 Windows Blender 执行渲染任务。
> 本 skill 封装 client 部分，server 部分同仓库维护（`server/` 目录）。

## 前置依赖

- Windows 端已启动 Blender Agent Server（默认 `http://<IP>:8080`）
- `pip install requests pydantic`

## 快速使用

```python
import sys
sys.path.insert(0, "/home/kai/.openclaw/workspace/skills/kais-blender-engine/client")

from blender_client import BlenderAgentClient

cli = BlenderAgentClient("http://192.168.1.100:8080")

# 健康检查
print(cli.health())

# 查询环境（Blender版本、GPU、插件）
print(cli.capabilities())
```

## 核心能力

### 1. 动画渲染（Animation Rendering）

导入 Mixamo 角色+动画 FBX，渲染为视频/帧序列。

```python
import sys
sys.path.insert(0, "/home/kai/.openclaw/workspace/skills/kais-blender-engine/client")

from blender_client import BlenderAgentClient
from generators.animation import AnimationParams

cli = BlenderAgentClient("http://192.168.1.100:8080")

# 列出可用资源
assets = cli.list_animations()
print("角色:", [c["name"] for c in assets["characters"]])
print("动画:", [m["name"] for m in assets["motions"]])

# 提交动画渲染
result = cli.render_animation(
    AnimationParams(
        preset_name="hero_walk",
        character="hero.fbx",
        motions=["walk.fbx", "run.fbx"],
        output_format="both",        # frames / video / both
        resolution=1024,
        samples=256,
        fps=24,
        lighting_preset="studio",    # studio / dramatic / soft / neon
        camera_preset="three_quarter",  # front / side / three_quarter / follow / orbit
    ),
    timeout=1800,
)
print("状态:", result["status"])
print("输出:", result["outputs"])
```

**AnimationParams 字段：**

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `preset_name` | str | 必填 | 输出文件名前缀 |
| `character` | str | 必填 | 角色 FBX 文件名 |
| `motions` | str[] | 必填 | 动画 FBX 文件名列表 |
| `output_format` | str | `"frames"` | `frames` / `video` / `both` |
| `resolution` | int | `1024` | 渲染分辨率 |
| `samples` | int | `256` | Cycles 采样数 (32-2048) |
| `fps` | int | `24` | 帧率 |
| `lighting_preset` | str | `"studio"` | `studio` / `dramatic` / `soft` / `neon` |
| `camera_preset` | str | `"three_quarter"` | `front` / `side` / `three_quarter` / `follow` / `orbit` |
| `transparent_bg` | bool | `false` | 透明背景 |
| `character_scale` | float | `1.0` | 角色缩放 |

**灯光预设：**
- `studio` — 三点布光，均匀柔和
- `dramatic` — 高对比主光+补光，戏剧性
- `soft` — 单一大面积柔光
- `neon` — 双色霓虹灯效果

**相机模式：**
- `front` / `side` / `three_quarter` — 固定机位
- `follow` — 跟随角色根骨骼
- `orbit` — 环绕旋转

### 2. 姿态渲染（Pose Rendering）

设置角色骨骼姿态，渲染静态图。

```python
import sys
sys.path.insert(0, "/home/kai/.openclaw/workspace/skills/kais-blender-engine/client")

from blender_client import BlenderAgentClient
from generators.pose import generate_pose_script
from pose_presets import get_pose_preset

cli = BlenderAgentClient("http://192.168.1.100:8080")

script = generate_pose_script(
    preset_name="hero_001",
    bone_rotations=get_pose_preset("wave"),  # 或自定义骨骼旋转
    camera_preset="front",                   # 见 camera_presets.py
    resolution=1024,
)

result = cli.run_sync(script, timeout=300)
print("渲染完成:", result["returncode"] == 0)
```

**内置姿态预设：**

| 预设名 | 说明 |
|--------|------|
| `t-pose` | T 姿势（默认） |
| `standing` | 自然站立 |
| `arms_up` | 双手举过头顶 |
| `wave` | 挥手 |
| `walk_left` / `walk_right` | 迈步 |
| `sit` | 坐姿 |
| `run` | 跑步 |
| `fighting_stance` | 格斗站姿 |
| `hands_on_hips` | 双手叉腰 |
| `crossed_arms` | 抱臂 |
| `sitting_relaxed` | 放松坐姿 |

### 3. 场景渲染（Scene Rendering）

程序化场景建模+渲染。

```python
import sys
sys.path.insert(0, "/home/kai/.openclaw/workspace/skills/kais-blender-engine/client")

from blender_client import BlenderAgentClient
from generators.scene import SceneParams, generate_scene_script

cli = BlenderAgentClient("http://192.168.1.100:8080")

script = generate_scene_script(
    SceneParams(
        preset_name="lab_001",
        scene_type="interior",       # interior / exterior / studio / abstract
        room_size="medium",          # small / medium / large
        style="modern",              # modern / cyberpunk / minimal / natural
        objects=["desk", "chair", "screen"],
        lighting="soft",             # soft / dramatic / neon / daylight
        camera_preset="isometric",
    ),
)
result = cli.run_sync(script, timeout=600)
```

### 4. 资产管理

```python
# 查看可用角色和动画
assets = cli.list_animations()

# 放入新 FBX 后刷新索引
cli.rebuild_animation_index()

# 查看场景素材（Poly Haven + ambientCG）
cli._get("/assets/stats")
cli._get("/assets/rebuild")

# 管理输出文件
files = cli.list_outputs(prefix="hero_")
data = cli.download_output("hero_walk.mp4", save_to="/tmp/hero.mp4")
cli.delete_output("hero_walk.mp4")
```

### 5. 底层任务控制

```python
# 同步执行任意 Blender Python 脚本
result = cli.run_sync("import bpy\nprint(bpy.data.objects.keys())", timeout=120)

# 异步执行（长任务）
job_id = cli.run_async(script, timeout=1800)

# 轮询任务状态
status = cli.poll_job(job_id, interval=10, max_wait=3600)

# 等待完成并获取输出
result = cli.wait_and_get_outputs(job_id)
```

## 与其他 Skill 的协作

```
kais-blender-scenecraft (场景蓝图)
       ↓ JSON
kais-blender-engine (本skill) → 动画渲染 / 姿态渲染 / 场景渲染
       ↓
kais-blender-layout (场景布局，更高级的场景组合渲染)
       ↓
kais-camera (视频生成)
```

**分工说明：**
- **engine（本skill）**：底层 API 客户端，单角色动画/姿态/简单场景
- **layout**：高层场景组合，多角色+家具+HDRI+多机位，内部调用 engine server
- **scenecraft**：纯规划，不接触 Blender

## 注意事项

- 所有路径为 Windows 端路径（`D:\BlenderAgent\...`），由 server 本地执行
- Mixamo FBX 放入后需调用 `rebuild_animation_index()` 刷新
- 动画渲染建议 timeout ≥ 1800s
- 本 skill 是 client 部分，server 部分见同仓库 `server/` 目录
