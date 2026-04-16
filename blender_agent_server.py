import shutil
import subprocess
import time
import zipfile
from pathlib import Path
from typing import Optional

import requests as http_requests
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from config import BLENDER_EXE, CACHE_DIR, OUTPUT_DIR, RENDER_TIMEOUT
from generators.character import CharacterParams, generate_character_script
from generators.scene import SceneParams, generate_scene_script

app = FastAPI(title="Blender Agent Server - Programmatic Modeling & Rendering")


@app.post("/generate/character")
async def generate_character(
    params: CharacterParams,
    background_tasks: BackgroundTasks,
):
    """生成程序化角色并返回多角度渲染图"""
    try:
        script = generate_character_script(params)
        script_file = CACHE_DIR / f"gen_{params.preset_name}_{int(time.time())}.py"
        script_file.write_text(script, encoding="utf-8")

        result = subprocess.run(
            [str(BLENDER_EXE), "-b", "--python", str(script_file)],
            capture_output=True,
            text=True,
            timeout=RENDER_TIMEOUT,
        )

        output_files = sorted(
            str(f) for f in OUTPUT_DIR.glob(f"{params.preset_name}_*.png")
        )

        if not output_files:
            stderr_tail = result.stderr[-2000:] if result.stderr else "no stderr"
            stdout_tail = result.stdout[-2000:] if result.stdout else "no stdout"
            raise HTTPException(500, f"渲染失败:\nstdout: {stdout_tail}\nstderr: {stderr_tail}")

        background_tasks.add_task(
            lambda: script_file.unlink() if script_file.exists() else None
        )

        return {
            "status": "success",
            "preset_name": params.preset_name,
            "outputs": output_files,
            "blend_file": str(CACHE_DIR / f"{params.preset_name}.blend"),
            "count": len(output_files),
        }

    except subprocess.TimeoutExpired:
        raise HTTPException(504, "渲染超时（超过5分钟）")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/generate/scene")
async def generate_scene(params: SceneParams):
    """生成程序化场景"""
    try:
        script = generate_scene_script(params)
        script_file = CACHE_DIR / f"scene_{params.preset_name}.py"
        script_file.write_text(script, encoding="utf-8")

        subprocess.run(
            [str(BLENDER_EXE), "-b", "--python", str(script_file)],
            capture_output=True,
            text=True,
            timeout=RENDER_TIMEOUT,
        )

        output_files = sorted(
            str(f) for f in OUTPUT_DIR.glob(f"{params.preset_name}_scene_*.png")
        )

        return {
            "status": "success",
            "outputs": output_files,
            "blend_file": str(CACHE_DIR / f"{params.preset_name}_scene.blend"),
        }

    except subprocess.TimeoutExpired:
        raise HTTPException(504, "渲染超时（超过5分钟）")
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/outputs/{filename}")
def get_output(filename: str):
    """获取渲染结果文件"""
    file_path = OUTPUT_DIR / filename
    if not file_path.exists():
        raise HTTPException(404, "文件不存在")
    return FileResponse(file_path)


@app.get("/health")
def health_check():
    """健康检查"""
    return {
        "status": "ok",
        "blender_path": str(BLENDER_EXE),
        "cache_dir": str(CACHE_DIR),
        "output_dir": str(OUTPUT_DIR),
    }


@app.get("/debug/mpfb")
def debug_mpfb():
    """测试 MPFB2 是否在 headless 模式下可用"""
    test_script = '''
import sys
print("=== MPFB2 Debug ===")
print("Python: " + sys.version)

# 测试 1: 模块导入
try:
    from mpfb.services.HumanService import HumanService
    from mpfb.services.TargetService import TargetService
    print("PASS: MPFB modules imported")
except ImportError as e:
    print("FAIL: Cannot import MPFB - " + str(e))
    sys.exit(1)

# 测试 2: create_human
try:
    basemesh = HumanService.create_human(feet_on_ground=True, scale=0.1)
    print("PASS: HumanService.create_human() returned " + str(type(basemesh)))
    print("PASS: basemesh name = " + basemesh.name)
    print("PASS: vertex count = " + str(len(basemesh.data.vertices)))
except Exception as e:
    import traceback
    print("FAIL: create_human failed")
    print(str(e))
    traceback.print_exc()
'''
    script_file = CACHE_DIR / "debug_mpfb.py"
    script_file.write_text(test_script, encoding="utf-8")
    result = subprocess.run(
        [str(BLENDER_EXE), "-b", "--python", str(script_file)],
        capture_output=True, text=True, timeout=60
    )
    return {
        "stdout": result.stdout,
        "stderr": result.stderr,
        "returncode": result.returncode,
    }


# ── 插件管理 ──────────────────────────────────────────────

def _get_addons_dir() -> Path:
    """获取 Blender 用户 addons 目录"""
    # 优先使用用户配置目录
    version_dir = BLENDER_EXE.parent / str(BLENDER_EXE.parent.parent.name).replace("Blender Foundation", "")
    # 回退到标准用户目录
    user_addons = Path.home() / "AppData" / "Roaming" / "Blender Foundation" / "Blender" / BLENDER_EXE.parent.name.replace("Blender ", "") / "scripts" / "addons"
    if not user_addons.exists():
        # 尝试从 BLENDER_EXE 路径推断版本
        import re
        m = re.search(r"(\d+\.\d+)", str(BLENDER_EXE))
        ver = m.group(1) if m else "4.0"
        user_addons = Path.home() / "AppData" / "Roaming" / "Blender Foundation" / "Blender" / ver / "scripts" / "addons"
    user_addons.mkdir(parents=True, exist_ok=True)
    return user_addons


class AddonInstallParams(BaseModel):
    url: str = Field(..., description="插件 zip 下载地址（GitHub release URL 或直链）")
    name: Optional[str] = Field(None, description="插件目录名（不填则自动从 zip 推断）")
    enable: bool = Field(True, description="是否安装后自动启用")


class AddonEnableParams(BaseModel):
    module: str = Field(..., description="插件模块名（即目录名或 .py 文件名，不含扩展名）")
    enable: bool = Field(True, description="True=启用, False=禁用")


@app.post("/install/addon")
async def install_addon(params: AddonInstallParams):
    """
    安装 Blender 插件。
    支持 GitHub release zip 直链，自动下载、解压到 addons 目录。
    """
    try:
        addons_dir = _get_addons_dir()
        download_dir = CACHE_DIR / "addon_downloads"
        download_dir.mkdir(parents=True, exist_ok=True)

        # 下载 zip
        filename = params.url.split("/")[-1].split("?")[0]
        if not filename.endswith(".zip"):
            filename += ".zip"
        zip_path = download_dir / filename

        print(f"下载插件: {params.url}")
        r = http_requests.get(params.url, timeout=120, stream=True)
        r.raise_for_status()
        with open(zip_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)

        # 解压
        extract_dir = CACHE_DIR / "addon_extract"
        if extract_dir.exists():
            shutil.rmtree(extract_dir)
        extract_dir.mkdir(parents=True)

        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(extract_dir)

        # 确定插件目录名
        extracted_items = list(extract_dir.iterdir())
        if params.name:
            addon_name = params.name
        elif len(extracted_items) == 1 and extracted_items[0].is_dir():
            addon_name = extracted_items[0].name
        else:
            addon_name = filename.replace(".zip", "")

        # 找到实际的插件目录（处理 zip 内嵌套一层目录的情况）
        if (extract_dir / addon_name).is_dir():
            source_dir = extract_dir / addon_name
        elif len(extracted_items) == 1 and extracted_items[0].is_dir():
            source_dir = extracted_items[0]
        else:
            source_dir = extract_dir

        # 处理 src/ 子目录布局（如 MPFB2: repo/src/mpfb/）
        src_subdir = source_dir / "src"
        if src_subdir.is_dir():
            # 查找 src/ 下包含 __init__.py 的包目录
            for item in src_subdir.iterdir():
                if item.is_dir() and (item / "__init__.py").exists():
                    addon_name = item.name
                    source_dir = item
                    break

        # 检查 __init__.py 存在
        if not (source_dir / "__init__.py").exists():
            # 可能是单文件插件
            py_files = list(source_dir.glob("*.py"))
            if not py_files:
                raise HTTPException(400, f"未找到 __init__.py，不是有效的 Blender 插件")
            source_dir = source_dir  # 单文件直接复制目录

        # 复制到 addons 目录
        dest = addons_dir / addon_name
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(source_dir, dest)

        # 清理
        shutil.rmtree(extract_dir, ignore_errors=True)

        # 自动启用
        module_name = addon_name
        if params.enable:
            enable_script = f'''
import bpy
try:
    bpy.ops.preferences.addon_enable(module="{module_name}")
    bpy.ops.wm.save_userpref()
    print("插件已启用: {module_name}")
except Exception as e:
    print("启用失败（可能在背景模式下不可用）: " + str(e))
    print("请手动在 Blender 编辑器中启用: Edit > Preferences > Add-ons > {module_name}")
'''
            script_file = CACHE_DIR / f"enable_{addon_name}.py"
            script_file.write_text(enable_script, encoding="utf-8")
            subprocess.run(
                [str(BLENDER_EXE), "-b", "--python", str(script_file)],
                capture_output=True, text=True, timeout=30
            )

        return {
            "status": "success",
            "addon_name": addon_name,
            "module": module_name,
            "installed_to": str(dest),
            "enabled": params.enable,
        }

    except http_requests.RequestException as e:
        raise HTTPException(502, f"下载失败: {e}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/addon/enable")
async def enable_addon(params: AddonEnableParams):
    """启用或禁用已安装的插件"""
enable_flag = "True" if params.enable else "False"
    script = f'''
import bpy
try:
    if {enable_flag}:
        bpy.ops.preferences.addon_enable(module="{params.module}")
    else:
        bpy.ops.preferences.addon_disable(module="{params.module}")
    bpy.ops.wm.save_userpref()
    print("OK")
except Exception as e:
    print("ERROR: " + str(e))
'''
    script_file = CACHE_DIR / f"toggle_{params.module}.py"
    script_file.write_text(script, encoding="utf-8")
    result = subprocess.run(
        [str(BLENDER_EXE), "-b", "--python", str(script_file)],
        capture_output=True, text=True, timeout=30
    )
    if "OK" in result.stdout:
        return {"status": "success", "module": params.module, "enabled": params.enable}
    else:
        raise HTTPException(500, f"操作失败: {result.stdout[-500:]}")


@app.get("/addons/list")
def list_addons():
    """列出已安装的插件"""
    addons_dir = _get_addons_dir()
    addons = []
    if addons_dir.exists():
        for item in addons_dir.iterdir():
            if item.is_dir() and (item / "__init__.py").exists():
                addons.append({"name": item.name, "type": "module", "path": str(item)})
            elif item.is_file() and item.suffix == ".py":
                addons.append({"name": item.stem, "type": "file", "path": str(item)})
    return {"status": "ok", "addons_dir": str(addons_dir), "addons": addons}


if __name__ == "__main__":
    import uvicorn
    from config import HOST, PORT

    uvicorn.run(app, host=HOST, port=PORT)
