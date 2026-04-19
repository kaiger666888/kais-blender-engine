"""Blender Agent HTTP 客户端 — 封装与 Server 的完整交互流程"""

import time
from typing import Dict, List, Optional, Tuple

import requests

from camera_presets import CameraPreset
from generators.animation import AnimationParams, generate_animation_script
from generators.pose import generate_pose_script
from generators.scene import SceneParams, generate_scene_script


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

    def wait_and_get_outputs(self, job_id: str, interval: float = 5.0, max_wait: float = 3600.0, prefix: str = "") -> dict:
        """等待任务完成并返回输出文件列表"""
        status = self.poll_job(job_id, interval, max_wait)
        if status["status"] != "completed":
            return {"status": status["status"], "error": status.get("error", ""), "outputs": []}
        params = {"prefix": prefix} if prefix else {}
        outputs = self._get("/outputs", params=params)
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
        chars_dir = caps["characters_dir"]
        motions_dir = caps["motions_dir"]

        script = generate_animation_script(
            params,
            output_dir=output_dir,
            characters_dir=chars_dir,
            motions_dir=motions_dir,
        )

        job_id = self.run_async(script, timeout=timeout)
        result = self.wait_and_get_outputs(job_id, interval=poll_interval, max_wait=timeout, prefix=params.preset_name)
        result["job_id"] = job_id
        return result

    # ── 高级接口：姿态渲染 ────────────────────────────────

    def render_pose(
        self,
        preset_name: str,
        bone_rotations: Optional[Dict[str, Tuple[float, float, float]]] = None,
        ik_targets: Optional[Dict[str, Tuple[float, float, float]]] = None,
        ik_chain_counts: Optional[Dict[str, int]] = None,
        action_name: Optional[str] = None,
        camera_preset: CameraPreset = CameraPreset.FRONT,
        custom_angles: Optional[list] = None,
        resolution: int = 1024,
        samples: int = 256,
        timeout: int = 600,
        poll_interval: float = 5.0,
    ) -> dict:
        """一键姿态渲染：生成脚本 → 异步提交 → 轮询 → 返回输出

        Args:
            preset_name: 角色名（对应 cache/{preset_name}.blend）
            bone_rotations: FK 骨骼旋转 {bone_name: (rx, ry, rz)}
            ik_targets: IK 目标位置 {末端骨骼: (x, y, z)}
            ik_chain_counts: IK 链长度覆盖 {末端骨骼: chain_count}
            action_name: 切换到指定 NLA action
            camera_preset: 相机预设
            custom_angles: 自定义相机角度
            resolution: 渲染分辨率
            samples: Cycles 采样数
            timeout: Blender 执行超时（秒）
            poll_interval: 轮询间隔

        Returns:
            {"status": "completed", "job_id": "...", "outputs": [...]}
        """
        caps = self._ensure_caps()
        output_dir = caps["output_dir"]
        cache_dir = caps["cache_dir"]

        script = generate_pose_script(
            preset_name=preset_name,
            bone_rotations=bone_rotations,
            ik_targets=ik_targets,
            ik_chain_counts=ik_chain_counts,
            action_name=action_name,
            camera_preset=camera_preset,
            custom_angles=custom_angles,
            resolution=resolution,
            samples=samples,
            output_dir=output_dir,
            cache_dir=cache_dir,
        )

        job_id = self.run_async(script, timeout=timeout)
        result = self.wait_and_get_outputs(job_id, interval=poll_interval, max_wait=timeout, prefix=preset_name)
        result["job_id"] = job_id
        return result

    # ── 高级接口：场景渲染 ────────────────────────────────

    def list_scene_assets(self, source: str = "", category: str = "", q: str = "") -> dict:
        """查询场景素材（HDRI / 3D模型 / PBR纹理）"""
        params = {}
        if source:
            params["source"] = source
        if category:
            params["category"] = category
        if q:
            params["q"] = q
        return self._get("/scene-assets", params=params)

    def render_scene(
        self,
        params: SceneParams,
        timeout: int = 1800,
        poll_interval: float = 10.0,
    ) -> dict:
        """一键场景渲染：生成脚本 → 异步提交 → 轮询 → 返回输出

        Args:
            params: 场景渲染参数（HDRI + 模型 + 可选角色动画）
            timeout: Blender 执行超时（秒）
            poll_interval: 轮询间隔

        Returns:
            {"status": "completed", "job_id": "...", "outputs": [...]}
        """
        caps = self._ensure_caps()
        output_dir = caps["output_dir"]
        assets_dir = caps.get("assets_dir", "")

        script = generate_scene_script(
            params,
            output_dir=output_dir,
            assets_dir=assets_dir,
            characters_dir=caps.get("characters_dir", ""),
            motions_dir=caps.get("motions_dir", ""),
        )

        job_id = self.run_async(script, timeout=timeout)
        result = self.wait_and_get_outputs(job_id, interval=poll_interval, max_wait=timeout, prefix=params.scene_name)
        result["job_id"] = job_id
        return result

