#!/usr/bin/env python3
"""
kais-blender client — 调用 Windows Blender Agent Server 生成角色/场景多角度渲染图。
支持 SMB 挂载直读和 HTTP 下载两种模式。
"""

import argparse
import json
import shutil
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

try:
    import requests
except ImportError:
    print("❌ 缺少 requests 模块，请运行: pip install requests")
    sys.exit(1)

SMB_MOUNT = Path("/mnt/blender_agent")
DEFAULT_TIMEOUT = 300


class BlenderAgentClient:
    def __init__(self, windows_ip: str = "192.168.71.38", port: int = 8080):
        self.base_url = f"http://{windows_ip}:{port}"
        self.smb_mount = SMB_MOUNT

    # ── Health ──────────────────────────────────────────────

    def health_check(self, timeout: int = 5) -> bool:
        try:
            r = requests.get(f"{self.base_url}/health", timeout=timeout)
            if r.status_code == 200:
                data = r.json()
                print(f"✅ Blender Server 在线 — {data.get('blender_path', 'N/A')}")
                return True
        except requests.ConnectionError:
            print("❌ 无法连接到 Blender Server")
        except requests.Timeout:
            print("❌ 连接超时")
        except Exception as e:
            print(f"❌ 健康检查失败: {e}")
        return False

    # ── Character ───────────────────────────────────────────

    def generate_character(
        self,
        name: str,
        gender: str = "male",
        height: float = 1.75,
        mass: float = 0.5,
        age: int = 25,
        style: str = "realistic",
        camera_preset: str = "standard_8",
        resolution: int = 1024,
        output_dir: str = "./outputs",
        timeout: int = DEFAULT_TIMEOUT,
    ) -> Dict:
        payload = {
            "preset_name": name,
            "gender": gender,
            "height": height,
            "mass": mass,
            "age": age,
            "style": style,
            "camera_preset": camera_preset,
            "resolution": resolution,
        }

        print(f"🎨 请求生成角色: {name} ({gender}, {height}m, {style})")
        print(f"   相机预设: {camera_preset}, 分辨率: {resolution}")

        t0 = time.time()
        resp = requests.post(
            f"{self.base_url}/generate/character", json=payload, timeout=timeout
        )
        elapsed = time.time() - t0

        if resp.status_code != 200:
            print(f"❌ 生成失败 [{resp.status_code}]: {resp.text[:500]}")
            return {"error": resp.text, "images": []}

        data = resp.json()
        if data.get("status") != "success":
            print(f"❌ 生成失败: {data}")
            return {"error": str(data), "images": []}

        # 获取本地文件路径
        local_paths = self._resolve_files(
            data.get("outputs", []), output_dir, name
        )

        print(f"✅ 完成！{len(local_paths)} 张图，耗时 {elapsed:.1f}s")
        for p in local_paths:
            print(f"   📷 {p}")

        return {
            "name": name,
            "images": local_paths,
            "blend_file": data.get("blend_file", ""),
            "count": len(local_paths),
            "elapsed": elapsed,
        }

    # ── Scene ───────────────────────────────────────────────

    def generate_scene(
        self,
        name: str,
        scene_type: str = "interior",
        style: str = "modern",
        objects: Optional[List[str]] = None,
        lighting: str = "soft",
        room_size: str = "medium",
        camera_preset: str = "isometric",
        output_dir: str = "./outputs",
        timeout: int = DEFAULT_TIMEOUT,
    ) -> Dict:
        payload = {
            "preset_name": name,
            "scene_type": scene_type,
            "style": style,
            "objects": objects or [],
            "lighting": lighting,
            "room_size": room_size,
            "camera_preset": camera_preset,
        }

        print(f"🎬 请求生成场景: {name} ({scene_type}, {style})")
        if objects:
            print(f"   物体: {', '.join(objects)}")

        t0 = time.time()
        resp = requests.post(
            f"{self.base_url}/generate/scene", json=payload, timeout=timeout
        )
        elapsed = time.time() - t0

        if resp.status_code != 200:
            print(f"❌ 生成失败 [{resp.status_code}]: {resp.text[:500]}")
            return {"error": resp.text, "images": []}

        data = resp.json()
        local_paths = self._resolve_files(
            data.get("outputs", []), output_dir, name
        )

        print(f"✅ 完成！{len(local_paths)} 张图，耗时 {elapsed:.1f}s")
        for p in local_paths:
            print(f"   📷 {p}")

        return {
            "name": name,
            "images": local_paths,
            "blend_file": data.get("blend_file", ""),
            "count": len(local_paths),
            "elapsed": elapsed,
        }

    # ── File resolution ─────────────────────────────────────

    def _resolve_files(
        self, win_paths: List[str], output_dir: str, name: str
    ) -> List[str]:
        """
        优先 SMB 挂载直读，降级为 HTTP 下载。
        """
        local_dir = Path(output_dir) / name
        local_dir.mkdir(parents=True, exist_ok=True)
        local_paths = []

        # 检查 SMB 是否可用
        use_smb = self.smb_mount.exists() and any(self.smb_mount.iterdir())

        for win_path in win_paths:
            filename = Path(win_path).name

            if use_smb:
                # SMB: Windows D:/BlenderAgent/outputs/xxx.png → /mnt/blender_agent/outputs/xxx.png
                try:
                    rel = Path(win_path)
                    # 去掉盘符前缀
                    parts = rel.parts
                    if len(parts) > 1 and ":" in parts[0]:
                        rel = Path(*parts[1:])
                    smb_path = self.smb_mount / rel
                    if smb_path.exists():
                        # 复制到本地输出目录
                        dest = local_dir / filename
                        shutil.copy2(smb_path, dest)
                        local_paths.append(str(dest))
                        continue
                except Exception as e:
                    print(f"⚠️ SMB 读取失败 {filename}: {e}")

            # 降级: HTTP 下载
            try:
                url = f"{self.base_url}/outputs/{filename}"
                dest = local_dir / filename
                r = requests.get(url, timeout=60)
                if r.status_code == 200:
                    with open(dest, "wb") as f:
                        f.write(r.content)
                    local_paths.append(str(dest))
                else:
                    print(f"⚠️ 下载失败 {filename}: HTTP {r.status_code}")
            except Exception as e:
                print(f"⚠️ 下载失败 {filename}: {e}")

        return local_paths


# ── CLI ──────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="kais-blender: 远程 Blender 渲染客户端"
    )
    parser.add_argument("--server-ip", default="192.168.71.38", help="Windows Blender Server IP")
    parser.add_argument("--port", type=int, default=8080, help="Server 端口")
    parser.add_argument("--output-dir", default="./outputs", help="输出目录")
    parser.add_argument("--timeout", type=int, default=300, help="渲染超时(秒)")

    sub = parser.add_subparsers(dest="command", required=True)

    # health
    sub.add_parser("health", help="健康检查")

    # character
    cp = sub.add_parser("character", help="生成角色多角度图")
    cp.add_argument("--name", required=True, help="角色名称/文件名")
    cp.add_argument("--gender", choices=["male", "female"], default="male")
    cp.add_argument("--height", type=float, default=1.75)
    cp.add_argument("--mass", type=float, default=0.5)
    cp.add_argument("--age", type=int, default=25)
    cp.add_argument("--style", choices=["realistic", "anime", "lowpoly"], default="realistic")
    cp.add_argument("--camera-preset", default="standard_8")
    cp.add_argument("--resolution", type=int, default=1024)

    # scene
    sp = sub.add_parser("scene", help="生成场景渲染图")
    sp.add_argument("--name", required=True, help="场景名称/文件名")
    sp.add_argument("--scene-type", choices=["interior", "exterior", "studio", "abstract"], default="interior")
    sp.add_argument("--style", choices=["modern", "cyberpunk", "minimal", "natural"], default="modern")
    sp.add_argument("--objects", nargs="*", default=[])
    sp.add_argument("--lighting", choices=["soft", "dramatic", "neon", "daylight"], default="soft")
    sp.add_argument("--room-size", choices=["small", "medium", "large"], default="medium")
    sp.add_argument("--camera-preset", default="isometric")

    args = parser.parse_args()
    client = BlenderAgentClient(windows_ip=args.server_ip, port=args.port)

    if args.command == "health":
        ok = client.health_check()
        sys.exit(0 if ok else 1)

    elif args.command == "character":
        result = client.generate_character(
            name=args.name,
            gender=args.gender,
            height=args.height,
            mass=args.mass,
            age=args.age,
            style=args.style,
            camera_preset=args.camera_preset,
            resolution=args.resolution,
            output_dir=args.output_dir,
            timeout=args.timeout,
        )
        # 输出 JSON 到 stdout 供下游使用
        print(f"\n📊 JSON 输出:")
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.command == "scene":
        result = client.generate_scene(
            name=args.name,
            scene_type=args.scene_type,
            style=args.style,
            objects=args.objects,
            lighting=args.lighting,
            room_size=args.room_size,
            camera_preset=args.camera_preset,
            output_dir=args.output_dir,
            timeout=args.timeout,
        )
        print(f"\n📊 JSON 输出:")
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
