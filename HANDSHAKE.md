# Blender Agent — 握手文档（API Contract）

> 本文档定义 Windows 执行引擎与 Linux 客户端之间的通信契约。
> 双方按此文档开发，无需关心对方内部实现。

## 架构总览

```
Linux (Client)                         Windows (Server)
┌──────────────────┐    HTTP/JSON     ┌─────────────────────┐
│ 脚本生成逻辑      │ ──────────────→ │ /run/script         │
│ (character/scene  │                  │   ↓                 │
│  /animation)     │                  │ blender.exe -b      │
│                  │ ←──────────────  │   ↓                 │
│ 下载渲染结果      │    /outputs/     │ 渲染完成            │
└──────────────────┘                  └─────────────────────┘

Mixamo FBX 文件通过共享目录放入:
  D:\BlenderAgent\animations\characters\  — 角色 FBX
  D:\BlenderAgent\animations\motions\     — 动画 FBX
```

## 服务端信息

| 项目 | 值 |
|------|---|
| 地址 | `http://<WINDOWS_IP>:8080` |
| 引擎 | Blender 5.1.1 Cycles (GPU: RTX 3060 Ti) |
| 已装插件 | mpfb (MPFB2 人体建模), MB-Lab |
| 输出目录 | `D:\BlenderAgent\outputs` |
| 动画目录 | `D:\BlenderAgent\animations\characters` + `motions` |
| 超时 | 默认 600s，可自定义 |

---

## API 端点

### 1. `GET /health`

健康检查。

**Response:**
```json
{
  "status": "ok",
  "blender": "D:\\Program\\Blender\\blender.exe",
  "output_dir": "D:\\BlenderAgent\\outputs"
}
```

---

### 2. `GET /capabilities`

查询 Windows 端环境信息。Linux 端应在启动时调用一次，缓存结果用于生成兼容脚本。

**Response:**
```json
{
  "blender_version": "5.1.1",
  "gpu": [
    {"name": "NVIDIA GeForce RTX 3060 Ti", "enabled": true}
  ],
  "addons": ["MB-Lab", "mpfb"],
  "output_dir": "D:\\BlenderAgent\\outputs"
}
```

**使用场景：**
- 检查 `mpfb` 是否在 addons 中，决定是否使用 MPFB2 人体建模
- 根据 `blender_version` 生成兼容的 Blender Python API 调用
- 脚本中的输出路径使用 `output_dir` 值

---

### 3. `POST /run/script`

同步执行 Blender Python 脚本。适用于短任务（< 60s）。

**Request:**
```json
{
  "script": "import bpy\nbpy.ops.mesh.primitive_cube_add()",
  "timeout": 600
}
```

**Response:**
```json
{
  "returncode": 0,
  "stdout": "Blender 5.1.1\n...",
  "stderr": ""
}
```

**错误：**
- `504` 超时
- `500` 内部错误

---

### 4. `POST /run/async`

异步执行脚本，立即返回 job_id。适用于长任务（多角度渲染）。

**Request:** 同 `/run/script`

**Response:**
```json
{
  "job_id": "a1b2c3d4e5f6",
  "status": "running"
}
```

**轮询:** `GET /jobs/{job_id}`

```json
{
  "status": "completed",    // running | completed | timeout | error
  "returncode": 0,
  "stdout": "...",
  "stderr": "..."
}
```

**清理:** `DELETE /jobs/{job_id}`

---

### 5. `GET /outputs`

列出输出文件。

**Query:** `?prefix=hero_` 按前缀过滤

**Response:**
```json
{
  "count": 8,
  "files": [
    {"name": "hero_front.png", "size": 976820, "modified": 1713326400.0},
    {"name": "hero_side.png", "size": 970879, "modified": 1713326414.0}
  ]
}
```

---

### 6. `GET /outputs/{filename}`

下载单个渲染结果文件。返回二进制文件流。

---

### 7. `DELETE /outputs/{filename}`

删除输出文件。

---

### 8. `POST /install/addon`

安装 Blender 插件（zip URL）。

**Request:**
```json
{
  "url": "https://github.com/makehumancommunity/mpfb2/releases/download/v2.0.15/mpfb2.zip",
  "name": "mpfb",
  "enable": true
}
```

**Response:**
```json
{
  "status": "success",
  "addon_name": "mpfb",
  "installed_to": "C:\\Users\\...\\addons\\mpfb"
}
```

---

### 9. `POST /addon/enable`

启用/禁用已安装的插件。

**Request:**
```json
{
  "module": "mpfb",
  "enable": true
}
```

**Response:**
```json
{
  "status": "success",
  "module": "mpfb",
  "enabled": true
}
```

---

### 10. `GET /animations`

列出可用的 Mixamo 角色和动画文件。

**Response:**
```json
{
  "characters": [
    {"name": "hero", "filename": "hero.fbx", "path": "D:\\BlenderAgent\\animations\\characters\\hero.fbx", "size": 1234567, "modified": 1713326400.0}
  ],
  "motions": [
    {"name": "walk", "filename": "walk.fbx", "path": "D:\\BlenderAgent\\animations\\motions\\walk.fbx", "size": 234567, "modified": 1713326400.0},
    {"name": "run", "filename": "run.fbx", "path": "D:\\BlenderAgent\\animations\\motions\\run.fbx", "size": 345678, "modified": 1713326400.0}
  ],
  "stats": {
    "total_characters": 1,
    "total_motions": 2
  }
}
```

---

### 11. `GET /animations/rebuild`

重新扫描 `animations/` 目录并生成索引。新放入 FBX 文件后需调用此端点。

**Response:**
```json
{
  "status": "rebuilt",
  "stats": {
    "total_characters": 1,
    "total_motions": 2
  }
}
```

---

## 典型调用流程

### Mixamo 动画渲染（角色 × 多动画）

```python
import requests

SERVER = "http://192.168.1.100:8080"

# 1. 查询可用动画资源
anims = requests.get(f"{SERVER}/animations").json()
print(f"角色: {anims['stats']['total_characters']} 个")
print(f"动画: {anims['stats']['total_motions']} 个")

# 2. 生成动画渲染脚本
from generators.animation import generate_animation_script, AnimationParams

script = generate_animation_script(
    AnimationParams(
        preset_name="hero_showreel",
        character="hero.fbx",
        motions=["walk.fbx", "run.fbx", "idle.fbx"],
        output_format="both",          # PNG 帧序列 + MP4 视频
        resolution=1024,
        samples=256,
        fps=24,
        lighting_preset="studio",
        camera_preset="three_quarter",
    ),
    output_dir="D:/BlenderAgent/outputs",
    characters_dir="D:/BlenderAgent/animations/characters",
    motions_dir="D:/BlenderAgent/animations/motions",
)

# 3. 异步提交（动画渲染可能较长）
job = requests.post(f"{SERVER}/run/async", json={"script": script, "timeout": 1800}).json()
job_id = job["job_id"]

# 4. 轮询结果
import time
while True:
    status = requests.get(f"{SERVER}/jobs/{job_id}").json()
    if status["status"] in ("completed", "timeout", "error"):
        break
    time.sleep(10)

# 5. 获取输出
files = requests.get(f"{SERVER}/outputs?prefix=hero_showreel_").json()
```

### 角色生成（MPFB2 静态参考图）

```python
import requests

SERVER = "http://192.168.1.100:8080"

# 1. 查询环境
caps = requests.get(f"{SERVER}/capabilities").json()
output_dir = caps["output_dir"]

# 2. 生成脚本（由 client/generators/ 完成）
from generators.character import generate_character_script, CharacterParams

script = generate_character_script(
    CharacterParams(
        preset_name="hero_001",
        gender="male",
        body_type="athletic",
        race="asian",
        lighting_preset="studio",
        camera_preset="STANDARD_8",
        samples=256,
    ),
    output_dir=output_dir,
    cache_dir="D:/BlenderAgent/cache",
)

# 3. 异步提交
job = requests.post(f"{SERVER}/run/async", json={"script": script, "timeout": 600}).json()
job_id = job["job_id"]

# 4. 轮询结果
import time
while True:
    status = requests.get(f"{SERVER}/jobs/{job_id}").json()
    if status["status"] in ("completed", "timeout", "error"):
        break
    time.sleep(5)

# 5. 获取输出文件列表
files = requests.get(f"{SERVER}/outputs?prefix=hero_001_").json()
for f in files["files"]:
    # 下载文件
    content = requests.get(f"{SERVER}/outputs/{f['name']}")
    with open(f["name"], "wb") as fh:
        fh.write(content.content)
```

---

## 脚本注意事项

Linux 端生成的 Blender Python 脚本需注意：

1. **输出路径**: 使用 `/capabilities` 返回的 `output_dir`，Windows 路径用 `r"D:\..."` 原始字符串
2. **MPFB2 初始化**: 脚本中需包含 monkey-patch（见 `client/generators/character.py` 参考）
3. **渲染结果**: 脚本中用 `print(json.dumps(output_paths))` 输出文件路径列表
4. **GPU**: 脚本中设置 `scene.cycles.device = 'GPU'`，Windows 端会自动使用 RTX 3060 Ti
5. **Blender 5.x API 变化**: `use_nodes` 属性将在 6.0 移除，`extension_path_user` 对非 extension 抛异常

---

## 状态跟踪

### Windows 端当前状态
- [x] Blender 5.1.1 + Cycles GPU 渲染正常
- [x] MPFB2 人体建模 headless 可用（需 monkey-patch）
- [x] 11 种相机预设 + 4 种灯光预设
- [x] 同步 + 异步任务执行
- [x] 文件管理（列表/下载/删除）
- [x] Mixamo FBX 动画渲染（帧序列 + 视频）
- [x] 动画资源索引管理

### Linux 端待开发
- [ ] 集成 OpenClaw 调用
- [ ] 角色生成脚本库（基于 client/generators/）
- [ ] 场景生成脚本库
- [ ] 自动下载并转发渲染结果

### 已知问题
| 问题 | 状态 | 说明 |
|------|------|------|
| MPFB2 Blender 5.x 兼容 | 已修复 | monkey-patch + addon_utils.enable |
| Shadow catcher API 变化 | 已处理 | try/except 多种 API 尝试 |
| HIPEW/HIP 动态库警告 | 可忽略 | AMD GPU 未安装，不影响 NVIDIA 渲染 |

---

## 变更日志

| 日期 | 变更 |
|------|------|
| 2026-04-17 | 初始版本：精简为执行引擎，新增 capabilities/async/jobs/outputs 端点 |
| 2026-04-17 | 新增 Mixamo 动画渲染：/animations 端点、animation.py 生成器、帧序列+视频输出 |
