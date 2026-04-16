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

# 3. 修复 SMB guest 访问被 Windows 拒绝的问题
# Windows 10/11 默认禁止不安全的 Guest 登录，需要通过注册表开启
Write-Host "配置 SMB 允许 Guest 访问..."

# 允许本地账户的空密码登录（Guest 模式需要）
$lanmanPath = "HKLM:\SYSTEM\CurrentControlSet\Services\LanmanServer\Parameters"
$lrestrictNullSessAccess = Get-ItemProperty -Path $lanmanPath -Name "RestrictNullSessAccess" -ErrorAction SilentlyContinue
if ($null -eq $lrestrictNullSessAccess) {
    New-ItemProperty -Path $lanmanPath -Name "RestrictNullSessAccess" -Value 0 -PropertyType DWord -Force | Out-Null
} else {
    Set-ItemProperty -Path $lanmanPath -Name "RestrictNullSessAccess" -Value 0 -Force
}

# 禁用"启用不安全的 Guest 登录"策略（AllowInsecureGuestAuth = 1）
$lanmanWksta = "HKLM:\SOFTWARE\Policies\Microsoft\Windows\LanmanWorkstation"
if (-not (Test-Path $lanmanWksta)) {
    New-Item -Path $lanmanWksta -Force | Out-Null
}
$allowGuest = Get-ItemProperty -Path $lanmanWksta -Name "AllowInsecureGuestAuth" -ErrorAction SilentlyContinue
if ($null -eq $allowGuest) {
    New-ItemProperty -Path $lanmanWksta -Name "AllowInsecureGuestAuth" -Value 1 -PropertyType DWord -Force | Out-Null
} else {
    Set-ItemProperty -Path $lanmanWksta -Name "AllowInsecureGuestAuth" -Value 1 -Force
}

# 4. 开启 SMB 共享（局域网访问）
Remove-SmbShare -Name "BlenderAgent" -Force -ErrorAction SilentlyContinue
New-SmbShare -Name "BlenderAgent" -Path "D:\BlenderAgent" -FullAccess "Everyone"

# 5. 防火墙放行
Remove-NetFirewallRule -DisplayName "BlenderAgent-API" -ErrorAction SilentlyContinue
Remove-NetFirewallRule -DisplayName "BlenderAgent-SMB" -ErrorAction SilentlyContinue
New-NetFirewallRule -DisplayName "BlenderAgent-API" -Direction Inbound -LocalPort 8080 -Protocol TCP -Action Allow
New-NetFirewallRule -DisplayName "BlenderAgent-SMB" -Direction Inbound -LocalPort 445 -Protocol TCP -Action Allow

# 6. 重启 SMB 服务使注册表生效
Restart-Service lanmanworkstation -Force -ErrorAction SilentlyContinue
Restart-Service lanmanserver -Force -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "安装完成！"
Write-Host ""
Write-Host "如果 Linux 端仍然无法 Guest 挂载，请在 Linux 端改用用户名密码认证："
Write-Host "  mount -t cifs //WINDOWS_IP/BlenderAgent /mnt/blender_agent -o username=你的Windows用户名,password=你的Windows密码,uid=`$(id -u),gid=`$(id -g)"
Write-Host ""
Write-Host "启动服务: python blender_agent_server.py"
