# Blender Agent Server

Windows 端 Blender 程序化建模 + 渲染 HTTP API 服务，供 Linux OpenClaw 等远程调用。

## 架构概览

```
┌─────────────────────┐         HTTP/SMB          ┌──────────────────────┐
│   Linux (OpenClaw)  │ ◄──────────────────────► │  Windows (Blender)   │
│                     │                            │                      │
│  openclaw_blender_  │   POST /generate/...      │  blender_agent_      │
│  client.py          │ ──────────────────────►   │  server.py           │
│                     │                            │    ├─ FastAPI 8080   │
│  /mnt/blender_agent │ ◄── SMB 文件共享 ───────  │    ├─ Blender CLI    │
│                     │   或 HTTP /outputs/xxx     │    └─ GPU 渲染       │
└─────────────────────┘                            └──────────────────────┘
```

## 快速开始

### 1. 前置条件

- Windows 10/11 + NVIDIA GPU（建议 RTX 系列）
- [Blender 4.x](https://www.blender.org/download/) 已安装
- Python 3.10+

### 2. 配置

编辑 `config.py`，确认 Blender 路径正确：

```python
BLENDER_EXE = Path(r"C:\Program Files\Blender Foundation\Blender 4.0\blender.exe")
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

### 4. 一键部署（可选）

以管理员身份运行 PowerShell：

```powershell
.\scripts\install.ps1
```

这会自动完成：
- 安装 Python 依赖
- 创建 `D:\BlenderAgent\` 目录结构
- 开启 SMB 共享（供 Linux 局域网读取文件）
- 防火墙放行 8080 端口

### 5. 启动服务

```bash
python blender_agent_server.py
```

服务默认监听 `0.0.0.0:8080`，启动后访问 http://localhost:8080/health 验证。

---

## API 接口

### 健康检查

```
GET /health
```

**响应示例：**

```json
{
  "status": "ok",
  "blender_path": "C:\\Program Files\\Blender Foundation\\Blender 4.0\\blender.exe",
  "cache_dir": "D:\\BlenderAgent\\cache",
  "output_dir": "D:\\BlenderAgent\\outputs"
}
```

---

### 生成角色

```
POST /generate/character
Content-Type: application/json
```

**请求参数：**

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `preset_name` | string | 是 | - | 输出文件名，如 `hero_001` |
| `gender` | string | 否 | `"male"` | `"male"` 或 `"female"` |
| `height` | float | 否 | `1.75` | 身高 1.4 ~ 2.0 米 |
| `mass` | float | 否 | `0.5` | 肌肉量/体重 0.0 ~ 1.0 |
| `age` | int | 否 | `25` | 年龄 18 ~ 80 |
| `style` | string | 否 | `"realistic"` | `"realistic"` / `"anime"` / `"lowpoly"` |
| `camera_preset` | string | 否 | `"standard_8"` | 相机位预设（见下表） |
| `custom_angles` | float[] | 否 | `null` | 自定义角度（弧度），覆盖预设 |
| `resolution` | int | 否 | `1024` | 渲染分辨率（正方形） |

**相机位预设：**

| 预设值 | 说明 | 输出数量 |
|--------|------|----------|
| `standard_8` | 8角度环拍（默认） | 8 张 |
| `standard_4` | 前/右/后/左 4角度 | 4 张 |
| `portrait_3` | 正脸/3⁄4侧/侧脸（证件照） | 3 张 |
| `front` | 正脸 | 1 张 |
| `three_quarter` | 3⁄4 侧脸 | 1 张 |
| `side` | 正侧脸 | 1 张 |
| `back` | 背面 | 1 张 |
| `top` | 俯视 | 1 张 |
| `isometric` | 等角视图 | 1 张 |
| `closeup_face` | 面部特写 | 1 张 |
| `full_body` | 全身 | 1 张 |

**请求示例 — curl：**

```bash
# 默认 8 角度环拍
curl -X POST http://localhost:8080/generate/character \
  -H "Content-Type: application/json" \
  -d '{"preset_name": "hero_001"}'

# 自定义参数
curl -X POST http://localhost:8080/generate/character \
  -H "Content-Type: application/json" \
  -d '{
    "preset_name": "female_warrior",
    "gender": "female",
    "height": 1.7,
    "mass": 0.6,
    "style": "realistic",
    "camera_preset": "portrait_3",
    "resolution": 2048
  }'

# 自定义角度（弧度）
curl -X POST http://localhost:8080/generate/character \
  -H "Content-Type: application/json" \
  -d '{
    "preset_name": "custom_angle",
    "custom_angles": [0, 1.57, 3.14]
  }'
```

**请求示例 — Python：**

```python
import requests

resp = requests.post("http://localhost:8080/generate/character", json={
    "preset_name": "hero_001",
    "gender": "male",
    "height": 1.8,
    "camera_preset": "standard_8",
})
print(resp.json())
```

**请求示例 — OpenClaw Skill：**

```python
from openclaw_blender_client import skill_generate_character

result = skill_generate_character({
    "name": "hero_001",
    "gender": "male",
    "height": 1.8,
    "windows_ip": "192.168.1.100",  # Windows 机 IP
    "camera_preset": "standard_8",
})
# result = {
#     "character_name": "hero_001",
#     "reference_images": ["/mnt/blender_agent/outputs/hero_001_angle_0.png", ...],
#     "image_count": 8
# }
```

**响应示例：**

```json
{
  "status": "success",
  "preset_name": "hero_001",
  "outputs": [
    "D:\\BlenderAgent\\outputs\\hero_001_angle_0.png",
    "D:\\BlenderAgent\\outputs\\hero_001_angle_45.png",
    "D:\\BlenderAgent\\outputs\\hero_001_angle_90.png",
    "D:\\BlenderAgent\\outputs\\hero_001_angle_135.png",
    "D:\\BlenderAgent\\outputs\\hero_001_angle_180.png",
    "D:\\BlenderAgent\\outputs\\hero_001_angle_225.png",
    "D:\\BlenderAgent\\outputs\\hero_001_angle_270.png",
    "D:\\BlenderAgent\\outputs\\hero_001_angle_315.png"
  ],
  "blend_file": "D:\\BlenderAgent\\cache\\hero_001.blend",
  "count": 8
}
```

---

### 生成场景

```
POST /generate/scene
Content-Type: application/json
```

**请求参数：**

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `preset_name` | string | 是 | - | 输出文件名 |
| `scene_type` | string | 是 | - | `"interior"` / `"exterior"` / `"studio"` / `"abstract"` |
| `room_size` | string | 否 | `"medium"` | `"small"` / `"medium"` / `"large"` |
| `style` | string | 否 | `"modern"` | `"modern"` / `"cyberpunk"` / `"minimal"` / `"natural"` |
| `objects` | string[] | 否 | `[]` | 场景物体，如 `["desk", "chair", "window"]` |
| `lighting` | string | 否 | `"soft"` | `"soft"` / `"dramatic"` / `"neon"` / `"daylight"` |
| `camera_preset` | string | 否 | `"isometric"` | 相机位预设（同角色接口） |

**请求示例 — curl：**

```bash
curl -X POST http://localhost:8080/generate/scene \
  -H "Content-Type: application/json" \
  -d '{
    "preset_name": "cyberpunk_room",
    "scene_type": "interior",
    "style": "cyberpunk",
    "room_size": "medium",
    "objects": ["desk", "chair", "window"],
    "lighting": "neon"
  }'
```

**请求示例 — Python：**

```python
from openclaw_blender_client import BlenderAgentClient

client = BlenderAgentClient("192.168.1.100")
result = client.generate_scene(
    name="cyberpunk_room",
    scene_type="interior",
    style="cyberpunk",
    objects=["desk", "chair", "window"],
)
```

**响应示例：**

```json
{
  "status": "success",
  "outputs": [
    "D:\\BlenderAgent\\outputs\\cyberpunk_room_scene_0.png"
  ],
  "blend_file": "D:\\BlenderAgent\\cache\\cyberpunk_room_scene.blend"
}
```

---

### 下载渲染结果

```
GET /outputs/{filename}
```

Linux 未挂载 SMB 时，可通过 HTTP 直接下载：

```bash
curl -O http://192.168.1.100:8080/outputs/hero_001_angle_0.png
```

---

## Linux 客户端部署

```bash
# 运行安装脚本
bash scripts/install_client.sh

# 然后在 Python 中使用
from openclaw_blender_client import BlenderAgentClient

client = BlenderAgentClient("192.168.1.100")
print(client.health_check())  # True
```

## 文件传输方式

| 方式 | 适用场景 | 配置 |
|------|----------|------|
| **SMB 挂载** | 局域网内，速度最快 | `install.ps1` 自动开启共享，Linux 端 `install_client.sh` 自动挂载到 `/mnt/blender_agent` |
| **HTTP 下载** | SMB 不可用或跨网段 | 客户端自动 fallback 到 HTTP 下载 |

## 典型工作流

```
OpenClaw 收到指令: "生成赛博朋克角色，身高1.8米，8角度"
  │
  ▼
skill_generate_character({...})
  │
  ▼ HTTP POST → Windows:8080/generate/character
  │
  ├─ Windows 端:
  │   1. 生成 Blender Python 脚本
  │   2. Blender CLI 后台执行
  │   3. MB-Lab 程序化建模（失败则降级为基础几何体）
  │   4. 按预设放置相机 → GPU 渲染多角度
  │   5. 保存 PNG 到 outputs/，.blend 到 cache/
  │
  ▼ 返回文件路径列表
  │
  ├─ Linux 端:
  │   1. 通过 SMB 挂载直接读取 PNG
  │   2. 或通过 HTTP /outputs/ 下载
  │
  ▼
传给下游（Seedance 等）
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

**Q: Blender 路径在哪修改？**
A: 编辑 `config.py` 中的 `BLENDER_EXE`。

**Q: 渲染超时怎么办？**
A: 修改 `config.py` 中的 `RENDER_TIMEOUT`（默认 300 秒）。

**Q: MB-Lab 没安装会怎样？**
A: 自动降级为基础几何体（胶囊体+球体），不会报错。

**Q: 如何注册为 Windows 服务（开机自启）？**
A: 使用 [nssm](https://nssm.cc/)：
```powershell
nssm install BlenderAgent "C:\Python310\python.exe" "D:\path\to\blender_agent_server.py"
nssm start BlenderAgent
```
