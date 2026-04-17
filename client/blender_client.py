"""Blender Agent HTTP 客户端 — 封装与 Server 的完整交互流程"""

import time
from typing import Optional

import requests

from generators.animation import AnimationParams, generate_animation_script
from generators.character import CharacterParams, generate_character_script


class BlenderAgentClient:
    """Blender Agent Server 的 HTTP 客户端

    封装：查询环境 → 生成脚本 → 提交执行 → 轮询结果 → 返回输出
    """

    def __init__(self, server_url: str = "http://localhost:8080"):
        self.server_url = server_url.rstrip("/")
        self._caps: Optional[dict] = None

    # ── 基础请求 ──────────────────────────────────────────

    def _get(self, path: str, **kwargs) -> dict:
        r = requests.get(f"{self.server_url}{path}", timeout=30, **kwargs)
        r.raise_for_status()
        return r.json()

    def _post(self, path: str, data: dict) -> dict:
        r = requests.post(f"{self.server_url}{path}", json=data, timeout=30)
        r.raise_for_status()
        return r.json()

    # ── 环境查询 ──────────────────────────────────────────

    def health(self) -> dict:
        return self._get("/health")

    def capabilities(self) -> dict:
        """查询并缓存 Server 环境信息"""
        self._caps = self._get("/capabilities")
        return self._caps

    def _ensure_caps(self) -> dict:
        if self._caps is None:
            self.capabilities()
        return self._caps

    # ── 动画资源 ──────────────────────────────────────────

    def list_animations(self) -> dict:
        """列出可用的 Mixamo 角色和动画"""
        return self._get("/animations")

    def rebuild_animation_index(self) -> dict:
        """重新扫描动画目录索引"""
        return self._get("/animations/rebuild")

    # ── 任务执行 ──────────────────────────────────────────

    def run_sync(self, script: str, timeout: int = 600) -> dict:
        """同步执行 Blender 脚本"""
        return self._post("/run/script", {"script": script, "timeout": timeout})

    def run_async(self, script: str, timeout: int = 600) -> str:
        """异步执行，返回 job_id"""
        result = self._post("/run/async", {"script": script, "timeout": timeout})
        return result["job_id"]

    def poll_job(self, job_id: str, interval: float = 5.0, max_wait: float = 3600.0) -> dict:
        """轮询任务直到完成，返回最终状态"""
        start = time.time()
        while True:
            status = self._get(f"/jobs/{job_id}")
            if status["status"] in ("completed", "timeout", "error"):
                return status
            if time.time() - start > max_wait:
                return {"status": "timeout", "error": f"轮询超时 ({max_wait}s)"}
            time.sleep(interval)

    def wait_and_get_outputs(self, job_id: str, interval: float = 5.0, max_wait: float = 3600.0) -> dict:
        """等待任务完成并返回输出文件列表"""
        status = self.poll_job(job_id, interval, max_wait)
        if status["status"] != "completed":
            return {"status": status["status"], "error": status.get("error", ""), "outputs": []}
        outputs = self._get("/outputs")
        return {"status": "completed", "outputs": outputs["files"]}

    # ── 输出文件 ──────────────────────────────────────────

    def list_outputs(self, prefix: str = "") -> list[dict]:
        params = {"prefix": prefix} if prefix else {}
        return self._get("/outputs", params=params).get("files", [])

    def download_output(self, filename: str, save_to: Optional[str] = None) -> bytes:
        """下载输出文件，可选保存到本地"""
        r = requests.get(f"{self.server_url}/outputs/{filename}", timeout=120)
        r.raise_for_status()
        if save_to:
            with open(save_to, "wb") as f:
                f.write(r.content)
        return r.content

    def delete_output(self, filename: str) -> dict:
        r = requests.delete(f"{self.server_url}/outputs/{filename}", timeout=30)
        r.raise_for_status()
        return r.json()

    # ── 高级接口：动画渲染 ────────────────────────────────

    def render_animation(
        self,
        params: AnimationParams,
        timeout: int = 1800,
        poll_interval: float = 10.0,
    ) -> dict:
        """一键动画渲染：生成脚本 → 异步提交 → 轮询 → 返回输出

        Args:
            params: 动画渲染参数
            timeout: Blender 执行超时（秒），动画较长建议 1800+
            poll_interval: 轮询间隔

        Returns:
            {"status": "completed", "job_id": "...", "outputs": [...]}
        """
        caps = self._ensure_caps()
        output_dir = caps["output_dir"]

        # 从 output_dir 推导 animations 目录（同级的 animations/）
        from pathlib import PureWindowsPath
        work_dir = str(PureWindowsPath(output_dir).parent)
        chars_dir = f"{work_dir}/animations/characters"
        motions_dir = f"{work_dir}/animations/motions"

        script = generate_animation_script(
            params,
            output_dir=output_dir,
            characters_dir=chars_dir,
            motions_dir=motions_dir,
        )

        job_id = self.run_async(script, timeout=timeout)
        result = self.wait_and_get_outputs(job_id, interval=poll_interval, max_wait=timeout)
        result["job_id"] = job_id
        return result

    # ── 高级接口：角色渲染（MPFB2 精修） ──────────────────

    def render_character(
        self,
        params: CharacterParams,
        timeout: int = 600,
    ) -> dict:
        """一键角色渲染：生成脚本 → 异步提交 → 轮询 → 返回输出"""
        caps = self._ensure_caps()
        output_dir = caps["output_dir"]
        cache_dir = output_dir.replace("/outputs", "/cache")

        script = generate_character_script(
            params,
            output_dir=output_dir,
            cache_dir=cache_dir,
        )

        job_id = self.run_async(script, timeout=timeout)
        result = self.wait_and_get_outputs(job_id, interval=5.0, max_wait=timeout)
        result["job_id"] = job_id
        return result
