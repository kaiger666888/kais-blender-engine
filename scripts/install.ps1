# install.ps1
# Windows 服务端部署脚本，以管理员运行

# 1. 安装 Python 依赖
pip install fastapi uvicorn python-multipart pydantic

# 2. 创建目录结构
$dirs = @(
    "D:\BlenderAgent",
    "D:\BlenderAgent\cache",
    "D:\BlenderAgent\outputs",
    "D:\BlenderAgent\templates"
)
foreach ($dir in $dirs) {
    New-Item -ItemType Directory -Path $dir -Force | Out-Null
}

# 3. 开启 SMB 共享（局域网访问）
# 先移除已有的同名共享，再重新创建
Remove-SmbShare -Name "BlenderAgent" -Force -ErrorAction SilentlyContinue
New-SmbShare -Name "BlenderAgent" -Path "D:\BlenderAgent" -FullAccess "Everyone"

# 4. 防火墙放行（先移除再添加，避免重复报错）
Remove-NetFirewallRule -DisplayName "BlenderAgent-API" -ErrorAction SilentlyContinue
Remove-NetFirewallRule -DisplayName "BlenderAgent-SMB" -ErrorAction SilentlyContinue
New-NetFirewallRule -DisplayName "BlenderAgent-API" -Direction Inbound -LocalPort 8080 -Protocol TCP -Action Allow
New-NetFirewallRule -DisplayName "BlenderAgent-SMB" -Direction Inbound -LocalPort 445 -Protocol TCP -Action Allow

# 5. 启动服务（建议用 nssm 做成 Windows 服务）
Write-Host "安装完成，运行: python blender_agent_server.py"
