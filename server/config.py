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

# MPFB2 素材索引
MPFB_DATA_DIR = Path(
    r"C:\Users\Kai\AppData\Roaming\Blender Foundation\Blender"
    r"\5.1\scripts\addons\mpfb\data"
)
ASSET_INDEX_PATH = Path(__file__).parent / "asset_index.json"

# Mixamo 动画资源目录
ANIMATIONS_DIR = WORK_DIR / "animations"
CHARACTERS_DIR = ANIMATIONS_DIR / "characters"
MOTIONS_DIR = ANIMATIONS_DIR / "motions"

ANIMATION_INDEX_PATH = Path(__file__).parent / "animation_index.json"

# 确保目录存在
for d in [WORK_DIR, CACHE_DIR, OUTPUT_DIR, TEMPLATE_DIR, ANIMATIONS_DIR, CHARACTERS_DIR, MOTIONS_DIR]:
    d.mkdir(parents=True, exist_ok=True)
