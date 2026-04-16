# Windows Blender Agent Server

部署在 Windows 高配机上，提供 HTTP API 供 Linux OpenClaw 调用。

## 安装

```powershell
# 以管理员运行
pip install fastapi uvicorn python-multipart pydantic

# 创建目录
New-Item -ItemType Directory -Path "D:\BlenderAgent\cache","D:\BlenderAgent\outputs","D:\BlenderAgent\templates" -Force

# 开启 SMB 共享
New-SmbShare -Name "BlenderAgent" -Path "D:\BlenderAgent" -FullAccess "Everyone" -Force

# 防火墙放行
New-NetFirewallRule -DisplayName "BlenderAgent-API" -Direction Inbound -LocalPort 8080 -Protocol TCP -Action Allow -Force
New-NetFirewallRule -DisplayName "BlenderAgent-SMB" -Direction Inbound -LocalPort 445 -Protocol TCP -Action Allow -Force
```

## 启动

```powershell
python blender_agent_server.py
```

推荐用 nssm 注册为 Windows 服务实现开机自启。

## API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/health` | GET | 健康检查 |
| `/generate/character` | POST | 生成角色多角度图 |
| `/generate/scene` | POST | 生成场景渲染图 |
| `/outputs/{filename}` | GET | 下载渲染结果 |

## 前置要求

- Blender 4.0+（修改 `BLENDER_EXE` 路径）
- 可选：MB-Lab 插件（角色生成降级为基础几何体）
- NVIDIA GPU（CUDA/OptiX 加速渲染）
