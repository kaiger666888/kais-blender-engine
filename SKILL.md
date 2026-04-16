---
name: kais-blender
version: 1.0.0
description: "通过HTTP API调用Windows高配机上的Blender，生成多机位角度的角色模型图和场景图。支持程序化角色生成（MB-Lab/几何降级）、程序化场景生成、8角度环拍、自定义相机位。Linux客户端，SMB挂载或HTTP下载获取渲染结果。触发词：生成角色图、blender角色、角色多角度、场景渲染、blender场景、角色模型图、场景模型图、blender渲染、character render、scene render"
---

<!-- FREEDOM:low -->
# kais-blender

Blender 远程渲染客户端。通过 HTTP API 调用 Windows 高配机上的 Blender，返回多机位角度的角色/场景渲染图。

## 架构

```
OpenClaw (Linux)  ──HTTP──▶  Windows Blender Server (FastAPI :8080)
       │                              │
       ├── SMB挂载 ◀──SMB─────────── D:/BlenderAgent/outputs/
       └── HTTP下载 ◀──GET────────── /outputs/{filename}
```

## 前置条件

- Windows 端已部署 Blender Agent Server（FastAPI :8080）
- Linux 端已安装 `cifs-utils`、`python3 requests`
- 网络互通（局域网或 VPN）

### Linux 端安装（首次）

```bash
# 1. 安装依赖
sudo apt-get install -y cifs-utils
pip install requests

# 2. 创建挂载点
sudo mkdir -p /mnt/blender_agent

# 3. 配置 SMB 挂载（替换 IP 为实际 Windows IP）
# 手动挂载测试：
sudo mount -t cifs //192.168.71.38/BlenderAgent /mnt/blender_agent \
  -o guest,uid=$(id -u),gid=$(id -g),file_mode=0777,dir_mode=0777

# 永久挂载（写入 fstab）：
echo "//192.168.71.38/BlenderAgent /mnt/blender_agent cifs guest,uid=$(id -u),gid=$(id -g),file_mode=0777,dir_mode=0777,_netdev,x-systemd.automount 0 0" | sudo tee -a /etc/fstab
sudo mount -a
```

### 验证连通性

```bash
python3 ~/.openclaw/workspace/skills/kais-blender/scripts/blender_client.py health \
  --server-ip 192.168.71.38 --port 8080
```

## 使用方法

### 生成角色多角度图

```bash
python3 ~/.openclaw/workspace/skills/kais-blender/scripts/blender_client.py character \
  --server-ip 192.168.71.38 \
  --name hero_001 \
  --gender male \
  --height 1.75 \
  --style realistic \
  --camera-preset standard_8 \
  --resolution 1024 \
  --output-dir ./outputs
```

### 生成场景渲染图

```bash
python3 ~/.openclaw/workspace/skills/kais-blender/scripts/blender_client.py scene \
  --server-ip 192.168.71.38 \
  --name cyberpunk_room \
  --scene-type interior \
  --style cyberpunk \
  --objects desk chair window \
  --lighting neon \
  --camera-preset isometric \
  --output-dir ./outputs
```

### 直接在 OpenClaw 中调用

Agent 可直接用 `exec` 执行上述命令，或通过 Python API：

```python
import sys
sys.path.insert(0, '/home/kai/.openclaw/workspace/skills/kais-blender/scripts')
from blender_client import BlenderAgentClient

client = BlenderAgentClient(windows_ip="192.168.71.38")
result = client.generate_character(name="hero_001", camera_preset="standard_8")
# result["images"] -> 本地文件路径列表
```

## 相机预设

| 预设 | 说明 | 角度数 |
|------|------|--------|
| `standard_8` | 8角度环拍（每45°） | 8 |
| `standard_4` | 4角度（前后左右） | 4 |
| `portrait_3` | 前/45°/侧脸（证件照） | 3 |
| `front` | 正脸 | 1 |
| `three_quarter` | 3/4侧脸 | 1 |
| `side` | 正侧脸 | 1 |
| `back` | 背面 | 1 |
| `closeup_face` | 面部特写 | 1 |
| `full_body` | 全身 | 1 |
| `isometric` | 等角视图（技术图） | 1 |

## 参数说明

### 角色生成

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `--name` | str | 必填 | 输出文件名 |
| `--gender` | male/female | male | 性别 |
| `--height` | float | 1.75 | 身高 (1.4-2.0m) |
| `--mass` | float | 0.5 | 肌肉量 (0-1) |
| `--age` | int | 25 | 年龄 (18-80) |
| `--style` | realistic/anime/lowpoly | realistic | 风格 |
| `--camera-preset` | 见上表 | standard_8 | 相机预设 |
| `--resolution` | int | 1024 | 分辨率 |

### 场景生成

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `--name` | str | 必填 | 输出文件名 |
| `--scene-type` | interior/exterior/studio/abstract | interior | 场景类型 |
| `--style` | modern/cyberpunk/minimal/natural | modern | 风格 |
| `--objects` | str[] | [] | 物体列表（desk/chair/window等） |
| `--lighting` | soft/dramatic/neon/daylight | soft | 灯光 |
| `--camera-preset` | 见上表 | isometric | 相机预设 |

## 输出

- 渲染图片：PNG 格式，存入 `--output-dir`
- 通过 SMB 挂载直接访问（推荐）或 HTTP 下载
- 返回 JSON 包含本地路径列表

## 错误处理

- 连接失败：检查 Windows 服务是否运行、防火墙是否放行 8080 端口
- SMB 挂载失败：降级为 HTTP 下载
- 渲染超时：默认 300 秒，可通过 `--timeout` 调整
