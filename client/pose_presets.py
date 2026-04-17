"""MPFB2 骨骼姿态预设 — 常用动作的骨骼旋转数据（弧度）

骨骼命名参考 MPFB2 标准骨骼系统（rig.default.json, 163 bones）。
旋转顺序为 (X, Y, Z)，符合 Blender 默认 XYZ Euler。

主要骨骼名:
  root, spine01-05, head, jaw
  clavicle.L/R, shoulder01.L/R, upperarm01-02.L/R, lowerarm01-02.L/R, wrist.L/R
  finger1-5 (1-3).L/R, metacarpal1-4.L/R
  upperleg01-02.L/R, lowerleg01-02.L/R, foot.L/R, toe1-5.L/R
  neck01-03, eye.L/R, tongue00-07.L/R
"""

POSE_PRESETS = {
    "t-pose": {},
    "standing": {
        "upperarm01.L": (0, 0, 0.3),
        "upperarm01.R": (0, 0, -0.3),
        "lowerarm01.L": (0, 0, -0.1),
        "lowerarm01.R": (0, 0, 0.1),
    },
    "arms_up": {
        "upperarm01.L": (1.5, 0, 0),
        "upperarm01.R": (1.5, 0, 0),
        "lowerarm01.L": (0, 0, 0),
        "lowerarm01.R": (0, 0, 0),
    },
    "walk_left": {
        "upperleg01.L": (0.5, 0, 0),
        "lowerleg01.L": (-0.8, 0, 0),
        "upperarm01.L": (-0.3, 0, 0),
        "lowerarm01.L": (-0.4, 0, 0),
    },
    "walk_right": {
        "upperleg01.R": (-0.5, 0, 0),
        "lowerleg01.R": (0.8, 0, 0),
        "upperarm01.R": (0.3, 0, 0),
        "lowerarm01.R": (0.4, 0, 0),
    },
    "wave": {
        "upperarm01.L": (1.5, 0, 0.2),
        "lowerarm01.L": (2.0, 0, 0),
        "lowerarm02.L": (0, 0, -0.3),
    },
    "sit": {
        "upperleg01.L": (1.5, 0, 0),
        "upperleg01.R": (1.5, 0, 0),
        "lowerleg01.L": (-1.5, 0, 0),
        "lowerleg01.R": (-1.5, 0, 0),
    },
    "run": {
        "upperleg01.L": (0.9, 0, 0),
        "lowerleg01.L": (-1.2, 0, 0),
        "upperleg01.R": (-0.6, 0, 0),
        "lowerleg01.R": (0.3, 0, 0),
        "upperarm01.L": (-0.5, 0, 0),
        "lowerarm01.L": (-0.6, 0, 0),
        "upperarm01.R": (0.5, 0, 0),
        "lowerarm01.R": (0.6, 0, 0),
        "spine01": (-0.1, 0, 0),
        "spine02": (-0.1, 0, 0),
    },
    "fighting_stance": {
        "upperleg01.L": (0.3, 0.1, 0),
        "lowerleg01.L": (-0.6, 0, 0),
        "upperleg01.R": (-0.2, -0.1, 0),
        "lowerleg01.R": (-0.3, 0, 0),
        "upperarm01.L": (0.8, 0.5, 0.3),
        "lowerarm01.L": (-1.5, 0, 0),
        "upperarm01.R": (0.6, -0.3, -0.2),
        "lowerarm01.R": (-1.2, 0, 0),
        "spine02": (0, 0, 0.1),
    },
    "hands_on_hips": {
        "upperarm01.L": (0, 0, 0.8),
        "lowerarm01.L": (1.5, 0, 0),
        "upperarm01.R": (0, 0, -0.8),
        "lowerarm01.R": (1.5, 0, 0),
    },
    "crossed_arms": {
        "upperarm01.L": (0, 0, 0.8),
        "lowerarm01.L": (1.8, 0, 0),
        "upperarm01.R": (0, 0, -0.8),
        "lowerarm01.R": (1.8, 0, 0),
    },
    "sitting_relaxed": {
        "upperleg01.L": (1.5, 0, 0),
        "upperleg01.R": (1.5, 0, 0),
        "lowerleg01.L": (-1.5, 0, 0),
        "lowerleg01.R": (-1.5, 0, 0),
        "upperarm01.L": (0, 0, 0.5),
        "lowerarm01.L": (1.2, 0, 0),
        "upperarm01.R": (0, 0, -0.5),
        "lowerarm01.R": (1.2, 0, 0),
        "spine02": (-0.1, 0, 0),
    },
}
