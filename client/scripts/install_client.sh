#!/bin/bash
# install_client.sh
# Linux 客户端部署脚本

# 安装依赖
pip install requests
sudo apt-get install -y cifs-utils

# 创建挂载点
sudo mkdir -p /mnt/blender_agent

echo ""
echo "请选择 SMB 挂载方式："
echo ""
echo "方式1: Guest 匿名挂载（Windows 需已运行 install.ps1 开启 Guest 访问）"
echo "  sudo mount -t cifs //192.168.1.100/BlenderAgent /mnt/blender_agent \\"
echo "    -o guest,uid=$(id -u),gid=$(id -g),file_mode=0777,dir_mode=0777"
echo ""
echo "方式2: 用户名密码认证（推荐，更稳定）"
echo "  sudo mount -t cifs //192.168.1.100/BlenderAgent /mnt/blender_agent \\"
echo "    -o username=你的Windows用户名,password=你的Windows密码,uid=$(id -u),gid=$(id -g),file_mode=0777,dir_mode=0777"
echo ""
echo "永久挂载（写入 fstab，替换 IP/用户名/密码）："
echo "  //192.168.1.100/BlenderAgent /mnt/blender_agent cifs username=USER,password=PASS,uid=$(id -u),gid=$(id -g),file_mode=0777,dir_mode=0777,_netdev,x-systemd.automount 0 0"
echo ""
echo "客户端配置完成"
