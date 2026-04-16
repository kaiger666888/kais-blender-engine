import subprocess
import time

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse

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
            raise HTTPException(500, f"渲染失败: {result.stderr[-1000:]}")

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


if __name__ == "__main__":
    import uvicorn
    from config import HOST, PORT

    uvicorn.run(app, host=HOST, port=PORT)
