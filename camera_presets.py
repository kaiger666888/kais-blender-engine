from enum import Enum
from typing import Dict, List, Optional


class CameraPreset(str, Enum):
    """预定义相机位"""
    FRONT = "front"
    THREE_QUARTER = "three_quarter"
    SIDE = "side"
    BACK = "back"
    TOP = "top"
    ISOMETRIC = "isometric"
    CLOSEUP_FACE = "closeup_face"
    FULL_BODY = "full_body"

    # 组合预设
    STANDARD_8 = "standard_8"
    STANDARD_4 = "standard_4"
    PORTRAIT_3 = "portrait_3"


_PRESETS: Dict[CameraPreset, List[Dict]] = {
    CameraPreset.FRONT: [
        {"location": (0, -3, 1.6), "rotation": (1.4, 0, 0)}
    ],
    CameraPreset.THREE_QUARTER: [
        {"location": (2, -2.5, 1.6), "rotation": (1.4, 0, 0.8)}
    ],
    CameraPreset.SIDE: [
        {"location": (3, 0, 1.6), "rotation": (1.4, 0, 1.57)}
    ],
    CameraPreset.BACK: [
        {"location": (0, 3, 1.6), "rotation": (1.4, 0, 3.14)}
    ],
    CameraPreset.TOP: [
        {"location": (0, 0, 4), "rotation": (0, 0, 0)}
    ],
    CameraPreset.ISOMETRIC: [
        {"location": (3, -3, 3), "rotation": (0.9, 0, 0.78)}
    ],
    CameraPreset.CLOSEUP_FACE: [
        {"location": (0, -0.8, 1.7), "rotation": (1.4, 0, 0)}
    ],
    CameraPreset.FULL_BODY: [
        {"location": (0, -4, 1.2), "rotation": (1.3, 0, 0)}
    ],
    CameraPreset.STANDARD_8: [
        {"location": (0, -3, 1.6), "rotation": (1.4, 0, a), "name": f"angle_{int(a * 57.3)}"}
        for a in [0, 0.78, 1.57, 2.36, 3.14, 3.92, 4.71, 5.5]
    ],
    CameraPreset.STANDARD_4: [
        {"location": (0, -3, 1.6), "rotation": (1.4, 0, a)}
        for a in [0, 1.57, 3.14, 4.71]
    ],
    CameraPreset.PORTRAIT_3: [
        {"location": (0, -3, 1.6), "rotation": (1.4, 0, 0), "name": "front"},
        {"location": (2, -2.5, 1.6), "rotation": (1.4, 0, 0.78), "name": "three_quarter"},
        {"location": (3, 0, 1.6), "rotation": (1.4, 0, 1.57), "name": "side"},
    ],
}


def get_camera_angles(
    preset: CameraPreset,
    custom: Optional[List[float]] = None,
) -> List[Dict]:
    """返回相机位配置（位置 + 旋转）

    如果提供了 custom 角度列表，则覆盖预设。
    """
    if custom:
        return [
            {"angle": a, "location": (0, -3, 1.6), "rotation": (1.1, 0, a)}
            for a in custom
        ]
    return list(_PRESETS.get(preset, _PRESETS[CameraPreset.STANDARD_8]))
