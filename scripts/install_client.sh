#!/bin/bash
# Linux 客户端部署脚本

# 安装依赖
pip install requests

# 创建 SMB 挂载（开机自动）
sudo mkdir -p /mnt/blender_agent
sudo apt-get install -y cifs-utils

# 添加到 fstab（替换为你的 Windows IP）
echo "//192.168.1.100/BlenderAgent /mnt/blender_agent cifs guest,uid=$(id -u),gid=$(id -g),file_mode=0777,dir_mode=0777,_netdev,x-systemd.automount 0 0" | sudo tee -a /etc/fstab

sudo mount -a
echo "客户端配置完成"
