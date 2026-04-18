#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Mixamo 批量下载工具

基于 Mixamo 内部 API，通过 Playwright 浏览器自动化登录获取 token，
然后直接调用 API 批量下载动画素材。

用法:
  # 首次运行（需手动登录 Adobe 账号）
  python mixamo_downloader.py --login

  # 按配置文件批量下载
  python mixamo_downloader.py --config mixamo_animations.yaml

  # 搜索动画
  python mixamo_downloader.py --search "walking"

  # 下载全部动画
  python mixamo_downloader.py --config mixamo_animations.yaml --all
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import quote

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import yaml

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
MIXAMO_BASE = "https://www.mixamo.com/api/v1"
MIXAMO_SITE = "https://www.mixamo.com"
API_KEY = "mixamo2"

SESSION_FILE = Path(__file__).parent / ".mixamo_session.json"
DEFAULT_CONFIG = Path(__file__).parent / "mixamo_animations.yaml"
DEFAULT_OUTPUT = Path(__file__).parent.parent / "mixamo_library"

HEADERS_TEMPLATE = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "X-Api-Key": API_KEY,
    "X-Requested-With": "XMLHttpRequest",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/135.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.mixamo.com/",
    "Origin": "https://www.mixamo.com",
}

# ---------------------------------------------------------------------------


def sanitize_filename(name: str) -> str:
    """将动画名转为文件名友好格式：空格→下划线，去除特殊字符，全小写。"""
    name = name.strip()
    name = re.sub(r"[^\w\s-]", "", name)
    name = re.sub(r"[\s]+", "_", name)
    return name.lower()


# ===========================================================================
# 认证模块
# ===========================================================================


def login_and_save_token(proxy: str | None = None) -> str:
    """
    启动 Playwright 浏览器让用户手动登录 Mixamo，
    登录成功后从 localStorage 提取 access_token 并保存。
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("错误: 需要安装 playwright。运行: pip install playwright && playwright install chromium")
        sys.exit(1)

    print("=" * 60)
    print("Mixamo 登录")
    print("=" * 60)
    print("即将打开浏览器，请手动登录你的 Adobe 账号。")
    print("登录成功后页面会跳转到 Mixamo 主页，脚本会自动提取 token。")
    print("=" * 60)

    with sync_playwright() as p:
        launch_opts = {
            "headless": False,
            "args": ["--disable-blink-features=AutomationControlled"],
        }
        if proxy:
            launch_opts["proxy"] = {"server": proxy}

        browser = p.chromium.launch(**launch_opts)
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/135.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()

        page.goto(f"{MIXAMO_SITE}/#", wait_until="commit", timeout=60000)
        print("\n等待登录... 请在浏览器中完成 Adobe 登录。")

        # 轮询等待 token 出现
        token = None
        for _ in range(300):  # 最多等 5 分钟
            time.sleep(1)
            try:
                token = page.evaluate("localStorage.getItem('access_token')")
            except Exception:
                pass
            if token:
                break

        if not token:
            print("超时：5 分钟内未检测到登录。请重试。")
            browser.close()
            sys.exit(1)

        # 获取 character_id：先尝试浏览器内 JS，失败则用 requests API 回退
        character_id = None
        character_name = None

        # 方式 1: 浏览器内 JS 调用
        try:
            page.wait_for_load_state("domcontentloaded", timeout=10000)
            resp = page.evaluate(
                """async () => {
                    const r = await fetch('/api/v1/characters/primary', {
                        headers: {
                            'Authorization': 'Bearer ' + localStorage.getItem('access_token'),
                            'X-Api-Key': 'mixamo2',
                            'Accept': 'application/json'
                        }
                    });
                    return await r.json();
                }"""
            )
            if resp:
                character_id = resp.get("primary_character_id")
                character_name = resp.get("primary_character_name")
        except Exception:
            pass

        # 方式 2: requests API 回退
        if not character_id:
            try:
                import requests as _req
                _headers = dict(HEADERS_TEMPLATE)
                _headers["Authorization"] = f"Bearer {token}"
                _proxies = {"http": proxy, "https": proxy} if proxy else None
                _resp = _req.get(
                    "https://www.mixamo.com/api/v1/characters/primary",
                    headers=_headers,
                    proxies=_proxies,
                    timeout=15,
                )
                _data = _resp.json()
                character_id = _data.get("primary_character_id")
                character_name = _data.get("primary_character_name")
            except Exception as e:
                print(f"警告: 无法获取 character_id: {e}")

        browser.close()

    # 保存 session
    session_data = {
        "access_token": token,
        "character_id": character_id,
        "character_name": character_name,
        "saved_at": time.time(),
    }
    SESSION_FILE.write_text(json.dumps(session_data, indent=2), encoding="utf-8")
    print(f"\n登录成功！角色: {character_name} ({character_id})")
    print(f"Token 已保存到: {SESSION_FILE}")

    return token


def load_session() -> dict | None:
    """从文件加载已保存的 session。"""
    if not SESSION_FILE.exists():
        return None
    try:
        data = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
        # token 有效期约 24 小时
        if time.time() - data.get("saved_at", 0) > 86400:
            print("警告: Token 可能已过期（超过 24 小时），建议重新登录。")
        return data
    except Exception:
        return None


def get_authenticated_session(session_data: dict, proxy: str | None = None) -> requests.Session:
    """创建带认证、自动重试和连接池的 requests.Session。

    优化点:
    - HTTPAdapter 自动重试: 连接错误 / 429 / 502/503/504 指数退避
    - 连接池: pool_connections=10, pool_maxsize=10，复用 TCP 连接
    - 浏览器头: UA/Referer/Origin，模拟真实浏览器流量
    """
    sess = requests.Session()
    sess.headers.update(HEADERS_TEMPLATE)
    sess.headers["Authorization"] = f"Bearer {session_data['access_token']}"
    if proxy:
        sess.proxies = {"http": proxy, "https": proxy}

    # 自动重试策略
    retry = Retry(
        total=5,
        backoff_factor=1.0,       # 1s, 2s, 4s, 8s, 16s
        status_forcelist=[429, 502, 503, 504],
        allowed_methods=["GET", "POST"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(
        max_retries=retry,
        pool_connections=10,
        pool_maxsize=10,
    )
    sess.mount("https://", adapter)
    sess.mount("http://", adapter)

    return sess


# ===========================================================================
# API 调用
# ===========================================================================


def search_animations(
    sess: requests.Session,
    query: str = "",
    page: int = 1,
    limit: int = 96,
) -> dict:
    """搜索 Mixamo 动画。"""
    url = f"{MIXAMO_BASE}/products"
    params = {
        "page": page,
        "limit": limit,
        "type": "Motion",
        "query": query,
    }
    resp = sess.get(url, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_all_animations(sess: requests.Session, query: str = "") -> list[dict]:
    """获取搜索结果的所有页。"""
    all_results = []
    page = 1
    while True:
        data = search_animations(sess, query=query, page=page)
        results = data.get("results", [])
        all_results.extend(results)
        pagination = data.get("pagination", {})
        num_pages = pagination.get("num_pages", 1)
        print(f"  页 {page}/{num_pages} — 累计 {len(all_results)} 条")
        if page >= num_pages:
            break
        page += 1
        time.sleep(0.3)  # 避免触发限速
    return all_results


def get_animation_detail(
    sess: requests.Session,
    anim_id: str,
    character_id: str,
) -> dict | None:
    """获取动画详情（含 gms_hash）。"""
    url = f"{MIXAMO_BASE}/products/{anim_id}"
    params = {"similar": 0, "character_id": character_id}
    try:
        resp = sess.get(url, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except requests.HTTPError as e:
        print(f"  获取动画详情失败 [{anim_id}]: {e}")
        return None


def export_animation(
    sess: requests.Session,
    character_id: str,
    character_name: str,
    anim_detail: dict,
    fmt: str = "fbx7_2019",
    skin: bool = False,
    fps: str = "30",
    in_place: bool = True,
) -> dict | None:
    """提交动画导出请求。"""
    anim_id = anim_detail["id"]
    product_name = anim_detail.get("description", f"anim_{anim_id}")
    anim_type = anim_detail.get("type", "Motion")

    # 构建 gms_hash
    details = anim_detail.get("details", {})
    gms_raw = details.get("gms_hash", {})
    if gms_raw:
        # 转换 params 格式: [["Speed", -1.0], ["Overdrive", 0.0]] → "-1.0,0.0"
        raw_params = gms_raw.get("params", [])
        if isinstance(raw_params, list) and raw_params and isinstance(raw_params[0], list):
            params_str = ",".join(str(p[1]) for p in raw_params)
        else:
            params_str = str(raw_params) if raw_params else "0"

        # trim 必须是整数，float 会导致导出帧数异常
        raw_trim = gms_raw.get("trim", [0, 100])
        trim = [int(raw_trim[0]), int(raw_trim[1])]

        gms_hash = [{
            "model-id": gms_raw.get("model-id", 0),
            "mirror": gms_raw.get("mirror", False),
            "trim": trim,
            "overdrive": gms_raw.get("overdrive", 0),
            "params": params_str,
            "arm-space": gms_raw.get("arm-space", 0),
            "inplace": in_place,
        }]
    else:
        gms_hash = None

    payload = {
        "character_id": character_id,
        "product_name": product_name,
        "type": anim_type,
        "preferences": {
            "format": fmt,
            "skin": str(skin).lower(),
            "fps": fps,
            "reducekf": "0",
        },
        "gms_hash": gms_hash,
    }

    url = f"{MIXAMO_BASE}/animations/export"
    try:
        resp = sess.post(url, json=payload, timeout=30)
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", "30"))
            print(f"  429 限速，等待 {retry_after} 秒后重试...")
            time.sleep(retry_after)
            resp = sess.post(url, json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except requests.ConnectionError:
        print(f"  导出连接中断，2 秒后重试...")
        time.sleep(2)
        try:
            resp = sess.post(url, json=payload, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except Exception:
            return None
    except requests.HTTPError as e:
        print(f"  导出失败 [{product_name}]: {e}")
        return None


def wait_for_export(
    sess: requests.Session,
    character_id: str,
    timeout: int = 300,
    poll_interval: int = 3,
) -> str | None:
    """轮询 monitor 端点等待导出完成，返回下载 URL。"""
    url = f"{MIXAMO_BASE}/characters/{character_id}/monitor"
    start = time.time()
    while time.time() - start < timeout:
        try:
            resp = sess.get(url, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                status = data.get("status", "")
                if status == "completed":
                    return data.get("job_result")
                elif status == "failed":
                    print(f"  导出失败: {data.get('message', '未知错误')}")
                    return None
            # 202 = still processing
        except requests.RequestException as e:
            print(f"  轮询出错: {e}")
        time.sleep(poll_interval)
    print("  导出超时")
    return None


def download_file(url: str, dest: Path, proxy: str | None = None) -> bool:
    """下载文件到指定路径，带自动重试。"""
    retry_adapter = HTTPAdapter(
        max_retries=Retry(total=3, backoff_factor=1.0, status_forcelist=[429, 502, 503, 504]),
        pool_connections=2,
        pool_maxsize=2,
    )
    dl_sess = requests.Session()
    dl_sess.mount("https://", retry_adapter)
    dl_sess.mount("http://", retry_adapter)
    if proxy:
        dl_sess.proxies = {"http": proxy, "https": proxy}

    for attempt in range(3):
        try:
            resp = dl_sess.get(url, timeout=120, stream=True)
            resp.raise_for_status()
            dest.parent.mkdir(parents=True, exist_ok=True)
            with open(dest, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            return True
        except requests.ConnectionError:
            if attempt < 2:
                wait = 2 ** attempt
                print(f"  下载连接中断，{wait} 秒后重试 ({attempt+1}/3)...")
                time.sleep(wait)
            else:
                print(f"  下载失败（连接重试耗尽）")
                return False
        except Exception as e:
            print(f"  下载失败: {e}")
            return False
    return False


# ===========================================================================
# 配置加载
# ===========================================================================


def load_config(config_path: Path) -> dict:
    """加载 YAML 配置文件。"""
    if not config_path.exists():
        print(f"配置文件不存在: {config_path}")
        print("请创建配置文件或使用 --search 查找动画。")
        sys.exit(1)

    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ===========================================================================
# 进度追踪
# ===========================================================================


class ProgressTracker:
    """跟踪下载进度，支持断点续传。"""

    def __init__(self, output_dir: Path):
        self.file = output_dir / ".download_progress.json"
        self.data = self._load()

    def _load(self) -> dict:
        if self.file.exists():
            try:
                return json.loads(self.file.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"completed": [], "failed": []}

    def save(self):
        self.file.parent.mkdir(parents=True, exist_ok=True)
        self.file.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")

    def is_completed(self, anim_id: str) -> bool:
        return anim_id in self.data["completed"]

    def mark_completed(self, anim_id: str):
        self.data["completed"].append(anim_id)
        self.save()

    def mark_failed(self, anim_id: str):
        self.data["failed"].append(anim_id)
        self.save()

    @property
    def completed_count(self) -> int:
        return len(self.data["completed"])

    @property
    def failed_count(self) -> int:
        return len(self.data["failed"])


# ===========================================================================
# 核心下载逻辑
# ===========================================================================


def download_animation(
    sess: requests.Session,
    character_id: str,
    character_name: str,
    anim_id: str,
    anim_name: str,
    output_dir: Path,
    category: str,
    progress: ProgressTracker,
    proxy: str | None = None,
    fmt: str = "fbx7_2019",
    skin: bool = False,
    fps: str = "30",
    in_place: bool = True,
    with_suffix: str = "",
) -> bool:
    """下载单个动画的完整流程。"""
    # 检查是否已完成
    if progress.is_completed(anim_id):
        print(f"  [跳过] {anim_name} (已完成)")
        return True

    print(f"  下载: {anim_name} [{anim_id}] → {category}/")

    # 1. 获取动画详情
    detail = get_animation_detail(sess, anim_id, character_id)
    if not detail:
        progress.mark_failed(anim_id)
        return False

    # 2. 提交导出
    export_result = export_animation(
        sess, character_id, character_name, detail,
        fmt=fmt, skin=skin, fps=fps, in_place=in_place,
    )
    if not export_result:
        progress.mark_failed(anim_id)
        return False

    # 3. 等待处理完成
    download_url = wait_for_export(sess, character_id)
    if not download_url:
        progress.mark_failed(anim_id)
        return False

    # 4. 构建文件名和路径
    safe_name = sanitize_filename(anim_name)
    suffix = with_suffix
    if in_place and "_inplace" not in suffix:
        suffix += "_inplace"
    if skin:
        suffix += "_withskin"
    filename = f"{safe_name}{suffix}.fbx"
    dest = output_dir / category / filename

    # 5. 下载文件
    if download_file(download_url, dest, proxy):
        print(f"  完成: {dest}")
        progress.mark_completed(anim_id)
        return True
    else:
        progress.mark_failed(anim_id)
        return False


def download_tpose(
    sess: requests.Session,
    character_id: str,
    character_name: str,
    output_dir: Path,
    proxy: str | None = None,
    fmt: str = "fbx7_2019",
) -> bool:
    """下载角色的 T-Pose。"""
    print(f"下载 T-Pose: {character_name}")

    payload = {
        "character_id": character_id,
        "product_name": character_name,
        "type": "Character",
        "preferences": {
            "format": fmt,
            "mesh": "t-pose",
        },
        "gms_hash": None,
    }

    url = f"{MIXAMO_BASE}/animations/export"
    try:
        resp = sess.post(url, json=payload, timeout=30)
        resp.raise_for_status()
    except requests.HTTPError as e:
        print(f"  T-Pose 导出失败: {e}")
        return False

    download_url = wait_for_export(sess, character_id)
    if not download_url:
        return False

    dest = output_dir / "tposes" / f"{sanitize_filename(character_name)}_tpose.fbx"
    return download_file(download_url, dest, proxy)


# ===========================================================================
# 批量下载入口
# ===========================================================================


def batch_download(
    sess: requests.Session,
    config: dict,
    session_data: dict,
    proxy: str | None = None,
):
    """按配置文件批量下载动画。"""
    character_id = session_data["character_id"]
    character_name = session_data.get("character_name", "Unknown")

    output_dir = Path(config.get("output_dir", str(DEFAULT_OUTPUT)))
    output_dir.mkdir(parents=True, exist_ok=True)

    fmt = config.get("format", "fbx7_2019")
    default_in_place = config.get("default_in_place", True)
    default_with_skin = config.get("default_with_skin", False)
    fps = str(config.get("fps", 30))
    delay = config.get("delay_between_downloads", 2)

    progress = ProgressTracker(output_dir)

    # 是否下载 T-Pose
    if config.get("download_tpose", False):
        download_tpose(sess, character_id, character_name, output_dir, proxy, fmt)

    animations = config.get("animations", {})
    total = sum(len(anims) for anims in animations.values())
    current = 0

    print(f"\n开始批量下载: {total} 个动画")
    print(f"角色: {character_name} | 格式: {fmt} | In-Place: {default_in_place}")
    print(f"输出目录: {output_dir}")
    print("=" * 60)

    # 构建搜索索引：一次性全量加载所有动画，建立 name → id 映射
    name_to_id = {}

    # 收集配置中已指定 ID 的动画（跳过搜索）
    needs_search = set()
    for category, anims in animations.items():
        for anim in anims:
            if isinstance(anim, dict) and anim.get("id"):
                name_to_id[anim.get("name", "").strip()] = str(anim["id"])
            elif isinstance(anim, dict):
                needs_search.add(anim.get("name", ""))
            elif isinstance(anim, str):
                needs_search.add(anim)

    if needs_search:
        print("\n构建动画索引...")
        # 对每个需要的动画名，用关键词搜索并精确匹配
        for query in sorted(needs_search):
            data = search_animations(sess, query=query, limit=96)
            results = data.get("results", [])
            matched_id = None

            # 优先精确匹配（不区分大小写）
            for r in results:
                desc = r.get("description", "").strip()
                if desc.lower() == query.lower():
                    matched_id = str(r.get("id", ""))
                    break

            # 精确匹配失败，取第一个搜索结果
            if not matched_id and results:
                matched_id = str(results[0].get("id", ""))

            if matched_id:
                name_to_id[query] = matched_id
                print(f"  \"{query}\" → {matched_id}")
            else:
                print(f"  \"{query}\" → 未找到")

        print(f"  索引构建完成: {len(name_to_id)} 条记录")

    # 开始逐个下载
    for category, anims in animations.items():
        print(f"\n--- 分类: {category} ---")
        for anim in anims:
            current += 1

            # 解析动画配置
            if isinstance(anim, str):
                anim_name = anim
                anim_id = None
                anim_in_place = default_in_place
                anim_skin = default_with_skin
                anim_suffix = ""
            elif isinstance(anim, dict):
                anim_name = anim.get("name", "")
                anim_id = anim.get("id")
                anim_in_place = anim.get("in_place", default_in_place)
                anim_skin = anim.get("with_skin", default_with_skin)
                anim_suffix = anim.get("suffix", "")
            else:
                continue

            # 查找动画 ID（索引中已精确匹配，直接取）
            if not anim_id:
                anim_id = name_to_id.get(anim_name)

            if not anim_id:
                print(f"  [未找到] {anim_name} — 请检查动画名或提供 ID")
                progress.mark_failed(f"unknown_{anim_name}")
                continue

            print(f"\n[{current}/{total}] ", end="")

            success = download_animation(
                sess=sess,
                character_id=character_id,
                character_name=character_name,
                anim_id=anim_id,
                anim_name=anim_name,
                output_dir=output_dir,
                category=category,
                progress=progress,
                proxy=proxy,
                fmt=fmt,
                skin=anim_skin,
                fps=fps,
                in_place=anim_in_place,
                with_suffix=anim_suffix,
            )

            if not success:
                print(f"  失败: {anim_name}")

            time.sleep(delay)

    # 打印报告
    print("\n" + "=" * 60)
    print("下载报告")
    print("=" * 60)
    print(f"完成: {progress.completed_count}")
    print(f"失败: {progress.failed_count}")
    if progress.data["failed"]:
        print("失败列表:")
        for fid in progress.data["failed"]:
            print(f"  - {fid}")


def download_all_animations(
    sess: requests.Session,
    session_data: dict,
    output_dir: Path,
    proxy: str | None = None,
    fmt: str = "fbx7_2019",
    in_place: bool = True,
    skin: bool = False,
    delay: float = 2.0,
):
    """下载 Mixamo 上的所有动画。"""
    character_id = session_data["character_id"]
    character_name = session_data.get("character_name", "Unknown")
    output_dir.mkdir(parents=True, exist_ok=True)
    progress = ProgressTracker(output_dir)

    print(f"开始下载全部动画 | 角色: {character_name}")
    print(f"格式: {fmt} | In-Place: {in_place} | Skin: {skin}")
    print("=" * 60)

    # 获取总页数
    first_page = search_animations(sess, query="", page=1, limit=96)
    pagination = first_page.get("pagination", {})
    total = pagination.get("num_results", 0)
    num_pages = pagination.get("num_pages", 1)
    print(f"共 {total} 个动画，{num_pages} 页")

    page = 1
    current = 0
    while page <= num_pages:
        if page == 1:
            data = first_page
        else:
            data = search_animations(sess, query="", page=page, limit=96)
            time.sleep(0.5)

        results = data.get("results", [])
        for anim in results:
            current += 1
            anim_id = str(anim.get("id", ""))
            anim_name = anim.get("description", f"anim_{anim_id}")

            print(f"\n[{current}/{total}] ", end="")
            download_animation(
                sess=sess,
                character_id=character_id,
                character_name=character_name,
                anim_id=anim_id,
                anim_name=anim_name,
                output_dir=output_dir,
                category="all",
                progress=progress,
                proxy=proxy,
                fmt=fmt,
                skin=skin,
                in_place=in_place,
            )
            time.sleep(delay)  # 避免限速

        page += 1

    print(f"\n完成: {progress.completed_count} | 失败: {progress.failed_count}")


# ===========================================================================
# CLI
# ===========================================================================


def main():
    parser = argparse.ArgumentParser(
        description="Mixamo 批量下载工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 登录获取 token
  python mixamo_downloader.py --login

  # 搜索动画
  python mixamo_downloader.py --search "walking"

  # 按配置下载
  python mixamo_downloader.py --config mixamo_animations.yaml

  # 下载所有动画
  python mixamo_downloader.py --all --output ./my_library
        """,
    )

    parser.add_argument("--login", action="store_true", help="登录 Mixamo 并保存 token")
    parser.add_argument("--search", type=str, help="搜索动画（显示结果列表）")
    parser.add_argument("--config", type=str, default=str(DEFAULT_CONFIG), help="配置文件路径")
    parser.add_argument("--all", action="store_true", help="下载全部动画（忽略配置文件）")
    parser.add_argument("--output", type=str, help="输出目录")
    parser.add_argument("--proxy", type=str, default="http://127.0.0.1:7891", help="HTTP 代理地址")
    parser.add_argument("--no-proxy", action="store_true", help="不使用代理")
    parser.add_argument("--format", type=str, default="fbx7_2019", help="下载格式 (fbx7_2019/fbx7/dae_mixamo)")
    parser.add_argument("--in-place", type=bool, default=True, help="优先下载 In-Place 版本")
    parser.add_argument("--skin", action="store_true", help="包含皮肤网格")
    parser.add_argument("--delay", type=float, default=2.0, help="每次下载间隔（秒）")

    args = parser.parse_args()

    proxy = None if args.no_proxy else args.proxy

    # 登录
    if args.login:
        login_and_save_token(proxy)
        return

    # 搜索
    if args.search:
        session_data = load_session()
        if not session_data:
            print("请先运行 --login 登录。")
            sys.exit(1)

        sess = get_authenticated_session(session_data, proxy)
        print(f"搜索: {args.search}")
        results = search_animations(sess, query=args.search)

        pagination = results.get("pagination", {})
        print(f"找到 {pagination.get('num_results', 0)} 个结果 ({pagination.get('num_pages', 1)} 页)")
        print("-" * 60)

        for r in results.get("results", []):
            anim_id = r.get("id", "?")
            name = r.get("description", "未知")
            print(f"  [{anim_id}] {name}")
        return

    # 批量下载
    session_data = load_session()
    if not session_data:
        print("请先运行 --login 登录。")
        sys.exit(1)

    sess = get_authenticated_session(session_data, proxy)

    if args.all:
        output = Path(args.output) if args.output else DEFAULT_OUTPUT
        download_all_animations(
            sess, session_data, output, proxy,
            fmt=args.format, in_place=args.in_place, skin=args.skin,
            delay=args.delay,
        )
    else:
        config = load_config(Path(args.config))
        if args.output:
            config["output_dir"] = args.output
        if args.delay:
            config["delay_between_downloads"] = args.delay
        batch_download(sess, config, session_data, proxy)


if __name__ == "__main__":
    main()
