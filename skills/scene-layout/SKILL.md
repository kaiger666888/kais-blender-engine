# scene-layout — 片场级场景布局引擎

> 基于 INFERACT/SceneCraft/AnimateScene 学术研究，实现 Blender 内角色与场景物体的智能布局。
> 核心能力：动作感知放置、碰撞避免、电影级相机、家具自动组装。

## 触发词
`scene-layout`, `场景布局`, `布景`, `scene composition`, `layout`, `布景设计`

## 核心模块

| 模块 | 职责 |
|------|------|
| `layout_engine.py` | 主编排器：场景描述 → Blender 脚本 |
| `contact_analyzer.py` | 从动画 FBX 提取接触点（sit/stand/grasp） |
| `spatial_solver.py` | AABB 碰撞检测 + 物理约束放置 |
| `camera_director.py` | 电影级相机（三分法/180度轴线/视轴引导） |
| `furniture_db.py` | 家具交互区域数据库 |
| `generators/scene_script.py` | 生成 Blender 可执行 Python 脚本 |

## 使用方式

```python
from scene_layout.layout_engine import SceneComposer

composer = SceneComposer()
blender_script = composer.compose(
    characters=[
        {"animation": "sitting_while_laughing", "position": "on:sofa"},
    ],
    furniture=["sofa_02", "Television_01", "potted_plant_04"],
    hdri="studio_small_03",
    camera_shots=["wide", "medium", "closeup"],
)
# blender_script → POST /run/script → Blender 执行
```

## 设计原理

### 第一层：动作感知布局
1. 分析动画 FBX 骨骼 transform → 提取接触点（臀部=支撑面，脚=地面）
2. 根据接触类型匹配家具（sit→sofa, stand→floor, grasp→table）
3. 用 clearance 机制放置角色（接触骨骼 z = 表面 z + clearance）

### 第二层：构图逻辑
- 三分法自动相机：GRID（九宫格交点）
- 180° 对话轴线：双人对话时相机在轴线一侧
- 视线引导：确保角色 A 看向 B 时无遮挡

### 第三层：管线集成
- 输出完整 Blender Python 脚本 → POST /run/script
- 与 kais-movie-agent Phase 5 场景生成集成
