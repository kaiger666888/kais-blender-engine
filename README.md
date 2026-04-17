# kais-blender

Windows 端 Blender 渲染 HTTP API 服务，供 Linux 远程调用。
**Mixamo 为主，MPFB2 精修**——核心能力是接收 Mixamo FBX 动画文件并在 Blender 中渲染。

## 架构概览

```
Linux (Client)                         Windows (Server)
┌──────────────────┐    HTTP/JSON     ┌─────────────────────┐
│ 脚本生成逻辑      │ ──────────────→ │ /run/script         │
│ (character/scene  │                  │   ↓                 │
│  /animation)     │                  │ blender.exe -b      │
│                  │ ←──────────────  │   ↓                 │
│ 下载渲染结果      │    /outputs/     │ 渲染完成            │
└──────────────────┘                  └─────────────────────┘

Mixamo FBX 通过共享目录放入:
  D:\BlenderAgent\animations\characters\  — 角色 FBX
  D:\BlenderAgent\animations\motions\     — 动画 FBX
```

## 快速开始

### 1. 前置条件

- Windows 10/11 + NVIDIA GPU（RTX 系列）
- Blender 5.1+ 已安装
- Python 3.10+

### 2. 配置

编辑 `server/config.py`，确认 Blender 路径：

```python
BLENDER_EXE = Path(r"D:\Program\Blender\blender.exe")
```

### 3. 安装依赖

```bash
cd server
pip install -r requirements.txt
```

### 4. 启动服务

```bash
python blender_agent_server.py
```

访问 http://localhost:8080/health 验证。

---

## API 接口

### `GET /health`

健康检查。

```json
{"status": "ok", "blender": "D:\\Program\\Blender\\blender.exe", "output_dir": "D:\\BlenderAgent\\outputs"}
```

---

### `GET /capabilities`

查询 Blender 版本、GPU、已安装插件。

```json
{
  "blender_version": "5.1.1",
  "gpu": [{"name": "NVIDIA GeForce RTX 3060 Ti", "enabled": true}],
  "addons": ["MB-Lab", "mpfb"],
  "output_dir": "D:\\BlenderAgent\\outputs"
}
```

---

### `POST /run/script`

同步执行 Blender Python 脚本。

**Request:**
```json
{"script": "import bpy\n...", "timeout": 600}
```

**Response:**
```json
{"returncode": 0, "stdout": "...", "stderr": ""}
```

---

### `POST /run/async`

异步执行脚本，立即返回 job_id。

**Response:**
```json
{"job_id": "a1b2c3d4e5f6", "status": "running"}
```

**轮询:** `GET /jobs/{job_id}`

---

### `GET /outputs` / `GET /outputs/{filename}` / `DELETE /outputs/{filename}`

输出文件管理。`?prefix=xxx` 按前缀过滤。

---

### `GET /animations`

列出可用的 Mixamo 角色和动画。

```json
{
  "characters": [
    {"name": "hero", "filename": "hero.fbx", "path": "D:\\BlenderAgent\\animations\\characters\\hero.fbx", "size": 1234567, "modified": 1713326400.0}
  ],
  "motions": [
    {"name": "walk", "filename": "walk.fbx", "path": "D:\\BlenderAgent\\animations\\motions\\walk.fbx", "size": 234567, "modified": 1713326400.0}
  ],
  "stats": {"total_characters": 1, "total_motions": 2}
}
```

---

### `GET /animations/rebuild`

重新扫描动画目录。放入新 FBX 后需调用。

```json
{"status": "rebuilt", "stats": {"total_characters": 1, "total_motions": 2}}
```

---

### `GET /assets` / `GET /assets/stats` / `GET /assets/rebuild`

MPFB2 素材索引查询（可选精修用）。

---

## 动画渲染流程

### 准备 Mixamo 资源

1. 在 [Mixamo](https://www.mixamo.com/) 上传角色 → Auto-Rig → 下载带骨骼角色 FBX → 放入 `D:\BlenderAgent\animations\characters\`
2. 选择动画 → 下载 FBX (Without Skin, fbx for Blender) → 放入 `D:\BlenderAgent\animations\motions\`
3. 调用 `GET /animations/rebuild` 刷新索引

### 客户端调用

```python
import requests
from generators.animation import generate_animation_script, AnimationParams

SERVER = "http://192.168.1.100:8080"

# 1. 生成动画渲染脚本
script = generate_animation_script(
    AnimationParams(
        preset_name="hero_showreel",
        character="hero.fbx",
        motions=["walk.fbx", "run.fbx", "idle.fbx"],
        output_format="both",        # PNG 帧序列 + MP4 视频
        resolution=1024,
        samples=256,
        fps=24,
        lighting_preset="studio",    # studio / dramatic / soft / neon
        camera_preset="three_quarter",  # front / side / three_quarter / follow / orbit
    ),
    output_dir="D:/BlenderAgent/outputs",
    characters_dir="D:/BlenderAgent/animations/characters",
    motions_dir="D:/BlenderAgent/animations/motions",
)

# 2. 异步提交
job = requests.post(f"{SERVER}/run/async", json={"script": script, "timeout": 1800}).json()
job_id = job["job_id"]

# 3. 轮询结果
import time
while True:
    status = requests.get(f"{SERVER}/jobs/{job_id}").json()
    if status["status"] in ("completed", "timeout", "error"):
        break
    time.sleep(10)

# 4. 获取输出文件
files = requests.get(f"{SERVER}/outputs?prefix=hero_showreel_").json()
```

### AnimationParams 参数

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `preset_name` | string | 是 | - | 输出文件名前缀 |
| `character` | string | 是 | - | 角色 FBX 文件名 |
| `motions` | string[] | 是 | - | 动画 FBX 文件名列表 |
| `output_format` | string | 否 | `"frames"` | `"frames"` / `"video"` / `"both"` |
| `resolution` | int | 否 | `1024` | 渲染分辨率 |
| `samples` | int | 否 | `256` | Cycles 采样数 |
| `fps` | int | 否 | `24` | 帧率 |
| `lighting_preset` | string | 否 | `"studio"` | 灯光预设 |
| `camera_preset` | string | 否 | `"three_quarter"` | 相机模式 |
| `transparent_bg` | bool | 否 | `false` | 透明背景 |
| `character_scale` | float | 否 | `1.0` | 角色缩放 |

### 动画相机模式

| 模式 | 说明 |
|------|------|
| `front` | 正面固定机位 |
| `side` | 侧面固定机位 |
| `three_quarter` | 3/4 角度固定机位（默认） |
| `follow` | 相机跟随角色根骨骼移动 |
| `orbit` | 相机环绕角色旋转 |

### 输出结构

```
outputs/
├── hero_showreel_walk/          # PNG 帧序列（output_format=frames 或 both）
│   ├── 0001.png
│   ├── 0002.png
│   └── ...
├── hero_showreel_walk.mp4       # MP4 视频（output_format=video 或 both）
├── hero_showreel_run/
│   └── ...
└── hero_showreel_run.mp4
```

---

## 架构策略

| 场景 | 方案 |
|------|------|
| **默认（95%）** | Mixamo FBX → Blender 渲染 |
| **绑定失败（复杂服装穿模）** | MPFB2 手动权重修正 |
| **面部特写（微表情）** | MPFB2 骨骼兜底 |
| **角色一致性（recurring 主角）** | MPFB2 参数化体型保存 |

MPFB2 代码保留在 `client/generators/character.py`，按需使用。

---

## 项目结构

```
server/
├── blender_agent_server.py      # FastAPI 主服务
├── config.py                    # 路径/端口配置
├── build_asset_index.py         # MPFB2 素材索引
├── build_animation_index.py     # Mixamo 动画索引
└── scripts/install.ps1          # Windows 部署

client/
├── generators/
│   ├── animation.py             # Mixamo 动画脚本生成器
│   ├── character.py             # MPFB2 角色脚本生成器（可选精修）
│   └── scene.py                 # 场景脚本生成器
├── camera_presets.py            # 静态相机预设
└── scripts/install_client.sh    # Linux 客户端
```

---

## 骨骼绑定与姿态系统

### 工作流

```
1. generate_rigged_character_script()  →  生成带骨骼的角色包 .blend
2. generate_pose_script()              →  加载角色包 + 设置姿态 + 渲染输出
```

### 骨骼绑定 — 生成角色包

调用 `generate_rigged_character_script()` 生成 Blender 脚本，通过 `/run/script` 发送到 Windows 执行：

```python
from client.generators.pose import generate_rigged_character_script
from client.generators.character import _build_macro_details, CharacterParams

params = CharacterParams(preset_name="hero_001", gender="male", height=1.8)
script = generate_rigged_character_script(
    preset_name="hero_001",
    macro_details=_build_macro_details(params),
    rig_file="rig.default.json",      # 或 rig.mixamo.json
    weights_file="weights.default.json",
)
# POST script 到 192.168.71.38:8080/run/script
# 输出: D:/BlenderAgent/cache/hero_001.blend
```

### 姿态渲染

```python
from client.generators.pose import generate_pose_script
from client.pose_presets import POSE_PRESETS

# 使用预设姿态
script = generate_pose_script(
    preset_name="hero_001",
    bone_rotations=POSE_PRESETS["wave"],
    camera_preset="front",
    resolution=1024,
)
# POST 到 Windows → D:/BlenderAgent/outputs/hero_001_front.png

# 自定义骨骼旋转
script = generate_pose_script(
    preset_name="hero_001",
    bone_rotations={
        "upperarm01.L": (1.5, 0, 0),
        "lowerarm01.L": (2.0, 0, 0),
    },
)
```

### 姿态预设（POSE_PRESETS）

| 预设名 | 说明 |
|--------|------|
| `t-pose` | T 姿势（默认骨骼姿势） |
| `standing` | 自然站立 |
| `arms_up` | 双手举过头顶 |
| `wave` | 挥手 |
| `walk_left` | 左腿迈步 |
| `walk_right` | 右腿迈步 |
| `sit` | 坐姿 |
| `run` | 跑步 |
| `fighting_stance` | 格斗站姿 |
| `hands_on_hips` | 双手叉腰 |
| `crossed_arms` | 抱臂 |
| `sitting_relaxed` | 放松坐姿 |

### MPFB2 主要骨骼名（163 bones）

```
root
spine01, spine02, spine03, spine04, spine05
neck01, neck02, neck03
head, jaw, eye.L, eye.R

clavicle.L, shoulder01.L, upperarm01.L, upperarm02.L,
lowerarm01.L, lowerarm02.L, wrist.L
finger1-1.L ~ finger5-3.L, metacarpal1-4.L

clavicle.R, shoulder01.R, upperarm01.R, upperarm02.R,
lowerarm01.R, lowerarm02.R, wrist.R
finger1-1.R ~ finger5-3.R, metacarpal1-4.R

upperleg01.L, upperleg02.L, lowerleg01.L, lowerleg02.L,
foot.L, toe1-5.L
upperleg01.R, upperleg02.R, lowerleg01.R, lowerleg02.R,
foot.R, toe1-5.R

tongue00.L ~ tongue07.L
```

旋转格式: `(rx, ry, rz)` 弧度，Blender 默认 XYZ Euler 顺序。

---

## 常见问题

**Q: Blender 路径在哪改？**
A: `server/config.py` 中的 `BLENDER_EXE`。

**Q: Mixamo FBX 放哪？**
A: 角色 → `D:\BlenderAgent\animations\characters\`，动画 → `D:\BlenderAgent\animations\motions\`，然后调 `/animations/rebuild`。

**Q: 渲染超时？**
A: `server/config.py` 的 `RENDER_TIMEOUT`，或在请求中传 `timeout` 参数。动画渲染建议设 1800s+。

**Q: Mixamo 下载什么格式？**
A: FBX for Blender，In-Place 模式，Without Skin（纯动画复用），FBX 2019。
