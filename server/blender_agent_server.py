import re
import shutil
import subprocess
import threading
import time
import uuid
import zipfile
from pathlib import Path
from typing import Dict, Optional

import requests as http_requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from config import BLENDER_EXE, CACHE_DIR, OUTPUT_DIR, RENDER_TIMEOUT

app = FastAPI(title="Blender Execution Engine")


# ── 异步任务存储 ──────────────────────────────────────────

_jobs: Dict[str, dict] = {}
_jobs_lock = threading.Lock()


def _run_job(job_id: str, script: str, timeout: int):
    """后台线程执行 Blender 脚本"""
    script_file = CACHE_DIR / f"job_{job_id}.py"
    script_file.write_text(script, encoding="utf-8")
    try:
        result = subprocess.run(
            [str(BLENDER_EXE), "-b", "--python", str(script_file)],
            capture_output=True, text=True, timeout=timeout,
        )
        with _jobs_lock:
            _jobs[job_id]["status"] = "completed"
            _jobs[job_id]["returncode"] = result.returncode
            _jobs[job_id]["stdout"] = result.stdout
            _jobs[job_id]["stderr"] = result.stderr
    except subprocess.TimeoutExpired:
        with _jobs_lock:
            _jobs[job_id]["status"] = "timeout"
    except Exception as e:
        with _jobs_lock:
            _jobs[job_id]["status"] = "error"
            _jobs[job_id]["error"] = str(e)
    finally:
        if script_file.exists():
            script_file.unlink()


# ── 健康检查 ──────────────────────────────────────────────

@app.get("/health")
def health_check():
    """健康检查"""
    return {"status": "ok", "blender": str(BLENDER_EXE), "output_dir": str(OUTPUT_DIR)}


# ── 环境查询 ──────────────────────────────────────────────

@app.get("/capabilities")
def capabilities():
    """查询 Blender 版本、GPU、已安装插件"""
    blender_version = ""
    try:
        r = subprocess.run(
            [str(BLENDER_EXE), "--version"],
            capture_output=True, text=True, timeout=10,
        )
        m = re.search(r"Blender (\S+)", r.stdout)
        if m:
            blender_version = m.group(1)
    except Exception:
        pass

    gpu_info = []
    gpu_script = (
        "import bpy\n"
        "try:\n"
        "    prefs = bpy.context.preferences.addons['cycles'].preferences\n"
        "    prefs.get_devices()\n"
        "    for d in prefs.devices:\n"
        '        print("GPU:" + d.name + ":" + str(d.use))\n'
        "except Exception:\n"
        "    pass\n"
    )
    script_file = CACHE_DIR / "gpu_detect.py"
    script_file.write_text(gpu_script, encoding="utf-8")
    try:
        r = subprocess.run(
            [str(BLENDER_EXE), "-b", "--python", str(script_file)],
            capture_output=True, text=True, timeout=30,
        )
        for line in r.stdout.splitlines():
            if line.startswith("GPU:"):
                parts = line.split(":", 2)
                gpu_info.append({"name": parts[1] if len(parts) > 1 else "", "enabled": parts[2] == "True" if len(parts) > 2 else False})
    except Exception:
        pass
    finally:
        if script_file.exists():
            script_file.unlink()

    addons = []
    addons_dir = _get_addons_dir()
    if addons_dir.exists():
        for item in addons_dir.iterdir():
            if item.is_dir() and (item / "__init__.py").exists():
                addons.append(item.name)

    return {
        "blender_version": blender_version,
        "gpu": gpu_info,
        "addons": sorted(addons),
        "output_dir": str(OUTPUT_DIR),
    }


# ── 脚本执行（同步） ────────────────────────────────────

class RunScriptParams(BaseModel):
    script: str = Field(..., description="要执行的 Blender Python 脚本")
    timeout: int = Field(RENDER_TIMEOUT, description="超时秒数")


@app.post("/run/script")
async def run_script(params: RunScriptParams):
    """同步执行 Blender Python 脚本"""
    script_file = CACHE_DIR / f"job_{int(time.time())}.py"
    script_file.write_text(params.script, encoding="utf-8")
    try:
        result = subprocess.run(
            [str(BLENDER_EXE), "-b", "--python", str(script_file)],
            capture_output=True, text=True, timeout=params.timeout,
        )
        return {
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    except subprocess.TimeoutExpired:
        raise HTTPException(504, f"脚本执行超时（{params.timeout}s）")
    finally:
        if script_file.exists():
            script_file.unlink()


# ── 脚本执行（异步） ────────────────────────────────────

class AsyncScriptParams(BaseModel):
    script: str = Field(..., description="要执行的 Blender Python 脚本")
    timeout: int = Field(RENDER_TIMEOUT, description="超时秒数")


@app.post("/run/async")
async def run_async(params: AsyncScriptParams):
    """异步执行脚本，立即返回 job_id，通过 /jobs/{job_id} 轮询结果"""
    job_id = uuid.uuid4().hex[:12]
    with _jobs_lock:
        _jobs[job_id] = {"status": "running", "created_at": time.time()}
    t = threading.Thread(target=_run_job, args=(job_id, params.script, params.timeout), daemon=True)
    t.start()
    return {"job_id": job_id, "status": "running"}


@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    """查询异步任务状态"""
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, "任务不存在")
    return dict(job)


@app.delete("/jobs/{job_id}")
def delete_job(job_id: str):
    """删除已完成任务记录"""
    with _jobs_lock:
        if job_id not in _jobs:
            raise HTTPException(404, "任务不存在")
        if _jobs[job_id]["status"] == "running":
            raise HTTPException(409, "任务正在运行，无法删除")
        del _jobs[job_id]
    return {"status": "deleted"}


# ── 文件管理 ──────────────────────────────────────────────

@app.get("/outputs")
def list_outputs(prefix: str = ""):
    """列出输出目录中的文件"""
    pattern = f"{prefix}*" if prefix else "*"
    files = []
    for f in sorted(OUTPUT_DIR.glob(pattern)):
        if f.is_file():
            files.append({
                "name": f.name,
                "size": f.stat().st_size,
                "modified": f.stat().st_mtime,
            })
    return {"count": len(files), "files": files}


@app.get("/outputs/{filename}")
def get_output(filename: str):
    """下载渲染结果文件"""
    file_path = OUTPUT_DIR / filename
    if not file_path.exists():
        raise HTTPException(404, "文件不存在")
    return FileResponse(file_path)


@app.delete("/outputs/{filename}")
def delete_output(filename: str):
    """删除输出文件"""
    file_path = OUTPUT_DIR / filename
    if not file_path.exists():
        raise HTTPException(404, "文件不存在")
    file_path.unlink()
    return {"status": "deleted"}


# ── 插件管理 ──────────────────────────────────────────────

def _get_addons_dir() -> Path:
    """获取 Blender 用户 addons 目录，自动检测版本"""
    version = None
    try:
        result = subprocess.run(
            [str(BLENDER_EXE), "--version"],
            capture_output=True, text=True, timeout=10,
        )
        m = re.search(r"Blender (\d+\.\d+)", result.stdout)
        if m:
            version = m.group(1)
    except Exception:
        pass

    if not version:
        m = re.search(r"(\d+\.\d+)", str(BLENDER_EXE))
        version = m.group(1) if m else "4.0"

    bf_dir = Path.home() / "AppData" / "Roaming" / "Blender Foundation" / "Blender"
    if bf_dir.exists():
        for d in sorted(bf_dir.iterdir(), reverse=True):
            if d.is_dir() and re.match(r"\d+\.\d+", d.name):
                addons = d / "scripts" / "addons"
                if addons.exists():
                    return addons

    user_dir = bf_dir / version / "scripts" / "addons"
    user_dir.mkdir(parents=True, exist_ok=True)
    return user_dir


class AddonInstallParams(BaseModel):
    url: str = Field(..., description="插件 zip 下载地址")
    name: Optional[str] = Field(None, description="插件目录名（不填则自动推断）")
    enable: bool = Field(True, description="是否安装后自动启用")


@app.post("/install/addon")
async def install_addon(params: AddonInstallParams):
    """安装 Blender 插件（zip 直链）"""
    try:
        addons_dir = _get_addons_dir()
        download_dir = CACHE_DIR / "addon_downloads"
        download_dir.mkdir(parents=True, exist_ok=True)

        filename = params.url.split("/")[-1].split("?")[0]
        if not filename.endswith(".zip"):
            filename += ".zip"
        zip_path = download_dir / filename

        r = http_requests.get(params.url, timeout=120, stream=True)
        r.raise_for_status()
        with open(zip_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)

        extract_dir = CACHE_DIR / "addon_extract"
        if extract_dir.exists():
            shutil.rmtree(extract_dir)
        extract_dir.mkdir(parents=True)

        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(extract_dir)

        extracted_items = list(extract_dir.iterdir())
        if params.name:
            addon_name = params.name
        elif len(extracted_items) == 1 and extracted_items[0].is_dir():
            addon_name = extracted_items[0].name
        else:
            addon_name = filename.replace(".zip", "")

        if (extract_dir / addon_name).is_dir():
            source_dir = extract_dir / addon_name
        elif len(extracted_items) == 1 and extracted_items[0].is_dir():
            source_dir = extracted_items[0]
        else:
            source_dir = extract_dir

        src_subdir = source_dir / "src"
        if src_subdir.is_dir():
            for item in src_subdir.iterdir():
                if item.is_dir() and (item / "__init__.py").exists():
                    addon_name = item.name
                    source_dir = item
                    break

        dest = addons_dir / addon_name
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(source_dir, dest)
        shutil.rmtree(extract_dir, ignore_errors=True)

        if params.enable:
            enable_script = (
                "import bpy\n"
                "try:\n"
                f'    bpy.ops.preferences.addon_enable(module="{addon_name}")\n'
                "    bpy.ops.wm.save_userpref()\n"
                f'    print("OK: {addon_name} enabled")\n'
                "except Exception as e:\n"
                f'    print("WARN: {addon_name} " + str(e))\n'
            )
            script_file = CACHE_DIR / f"enable_{addon_name}.py"
            script_file.write_text(enable_script, encoding="utf-8")
            subprocess.run(
                [str(BLENDER_EXE), "-b", "--python", str(script_file)],
                capture_output=True, text=True, timeout=30,
            )

        return {
            "status": "success",
            "addon_name": addon_name,
            "installed_to": str(dest),
        }

    except http_requests.RequestException as e:
        raise HTTPException(502, f"下载失败: {e}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


class AddonEnableParams(BaseModel):
    module: str = Field(..., description="插件模块名")
    enable: bool = Field(True, description="True=启用, False=禁用")


@app.post("/addon/enable")
async def enable_addon(params: AddonEnableParams):
    """启用或禁用已安装的插件"""
    action = "addon_enable" if params.enable else "addon_disable"
    script = (
        "import bpy\n"
        "try:\n"
        f'    bpy.ops.preferences.{action}(module="{params.module}")\n'
        "    bpy.ops.wm.save_userpref()\n"
        '    print("OK")\n'
        "except Exception as e:\n"
        '    print("ERROR: " + str(e))\n'
    )
    script_file = CACHE_DIR / f"toggle_{params.module}.py"
    script_file.write_text(script, encoding="utf-8")
    try:
        result = subprocess.run(
            [str(BLENDER_EXE), "-b", "--python", str(script_file)],
            capture_output=True, text=True, timeout=30,
        )
        if "OK" in result.stdout:
            return {"status": "success", "module": params.module, "enabled": params.enable}
        raise HTTPException(500, result.stdout[-500:])
    finally:
        if script_file.exists():
            script_file.unlink()


if __name__ == "__main__":
    import uvicorn
    from config import HOST, PORT

    uvicorn.run(app, host=HOST, port=PORT)
