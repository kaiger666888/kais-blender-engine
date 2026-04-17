from pathlib import Path


# Blender 可执行文件路径（按实际安装位置修改）
BLENDER_EXE = Path(r"D:\Program\Blender\blender.exe")

# 工作目录
WORK_DIR = Path("D:/BlenderAgent")
CACHE_DIR = WORK_DIR / "cache"
OUTPUT_DIR = WORK_DIR / "outputs"
TEMPLATE_DIR = WORK_DIR / "templates"

# 服务配置
HOST = "0.0.0.0"
PORT = 8080

# 渲染默认超时（秒）
RENDER_TIMEOUT = 600

# 确保目录存在
for d in [WORK_DIR, CACHE_DIR, OUTPUT_DIR, TEMPLATE_DIR]:
    d.mkdir(parents=True, exist_ok=True)
