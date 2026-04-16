from pathlib import Path
from typing import Dict, List

import requests


class BlenderAgentClient:
    """Linux 端客户端，调用 Windows Blender Agent Server"""

    def __init__(self, windows_ip: str = "192.168.1.100", port: int = 8080):
        self.base_url = f"http://{windows_ip}:{port}"
        self.smb_mount = Path("/mnt/blender_agent")

    def health_check(self) -> bool:
        try:
            r = requests.get(f"{self.base_url}/health", timeout=5)
            return r.status_code == 200
        except Exception:
            return False

    def generate_character(
        self,
        name: str,
        gender: str = "male",
        height: float = 1.75,
        style: str = "realistic",
        camera_preset: str = "standard_8",
    ) -> Dict:
        payload = {
            "preset_name": name,
            "gender": gender,
            "height": height,
            "style": style,
            "camera_preset": camera_preset,
            "resolution": 1024,
        }

        resp = requests.post(
            f"{self.base_url}/generate/character", json=payload, timeout=300
        )
        data = resp.json()

        if data.get("status") != "success":
            raise Exception(f"生成失败: {data}")

        # 转换为 Linux 可访问路径
        linux_paths = []
        if self.smb_mount.exists():
            for win_path in data["outputs"]:
                rel_path = Path(win_path).relative_to("D:/BlenderAgent")
                linux_paths.append(self.smb_mount / rel_path)
        else:
            linux_paths = self._download_files(data["outputs"], f"./outputs/{name}")

        return {
            "name": name,
            "images": linux_paths,
            "blend_file": data["blend_file"],
            "count": data["count"],
        }

    def generate_scene(
        self,
        name: str,
        scene_type: str = "interior",
        style: str = "cyberpunk",
        objects: List[str] = None,
    ) -> Dict:
        payload = {
            "preset_name": name,
            "scene_type": scene_type,
            "style": style,
            "objects": objects or [],
            "camera_preset": "isometric",
        }
        resp = requests.post(
            f"{self.base_url}/generate/scene", json=payload, timeout=300
        )
        return resp.json()

    def _download_files(self, remote_paths: List[str], local_dir: str) -> List[Path]:
        local_dir = Path(local_dir)
        local_dir.mkdir(parents=True, exist_ok=True)
        local_paths = []

        for remote_path in remote_paths:
            filename = Path(remote_path).name
            url = f"{self.base_url}/outputs/{filename}"
            local_path = local_dir / filename

            r = requests.get(url)
            with open(local_path, "wb") as f:
                f.write(r.content)
            local_paths.append(local_path)

        return local_paths


def skill_generate_character(params: dict) -> dict:
    """OpenClaw Skill 集成函数"""
    client = BlenderAgentClient(
        windows_ip=params.get("windows_ip", "192.168.1.100")
    )

    if not client.health_check():
        return {"error": "Windows Blender 服务不可用"}

    result = client.generate_character(
        name=params["name"],
        gender=params.get("gender", "male"),
        height=params.get("height", 1.75),
        style=params.get("style", "realistic"),
        camera_preset=params.get("camera_preset", "standard_8"),
    )

    return {
        "character_name": result["name"],
        "reference_images": [str(p) for p in result["images"]],
        "image_count": len(result["images"]),
    }
