# Unreal 静帧渲染管线

基于 **Unreal Engine 5.5.4** 的 Python 静帧渲染管线。读取 JSON 配置，在 UE 场景中通过 **NavMesh 随机采样**目标点，放置角色/物体，用**单个相机沿 11 帧轨迹**遍历 11 个相机位，经 **Movie Render Queue (MRQ)** 批量渲染出 11 张静帧（1 中心 + 10 环绕）。

脚本与渲染工程分离：`ue_pipeline` 只含脚本，渲染工程（如 `我的项目3`）只提供关卡/资产。

---

## 目录结构

```
ue_pipeline/
├── run_pipeline.py          # 唯一入口：Python 直接启动 UnrealEditor（无 bat）
├── render_main.py           # 主流程（引擎 -ExecutePythonScript 加载）
├── src/                     # 核心源码
│   ├── config_parser.py     # JSON 配置解析 + 校验
│   ├── camera_rig.py        # 11 相机位几何计算（1 中心 + 10 环绕）
│   ├── target_sampler.py    # NavMesh 随机采样 + 碰撞检测
│   ├── scene_assembler.py   # 关卡加载 + 三种模式装配 + 动画绑定 + IK 重定向
│   ├── sequence_builder.py  # LevelSequence 构建（单相机 11 帧轨迹）
│   ├── mrq_renderer.py      # MRQ 批量渲染（每 sequence 双 job：PNG + EXR）
│   └── cleanup.py           # 自动清理上次运行残留
├── configs/                 # 示例配置
│   ├── example_config.json          # char_anim_scene 单任务
│   ├── example_config_full.json     # 多任务批量（3 sequence）
│   ├── example_config_pure.json     # pure_scene 纯场景
│   └── example_config_actor.json    # actor_scene 物体放置
└── tests/
    └── test_integration.py  # mock 回归测试
```

---

## 环境要求

| 项 | 要求 |
|----|------|
| Unreal Engine | 5.5.x（本工程验证于 5.5.4） |
| 渲染工程 | 需启用插件：`PythonScriptPlugin`、`MovieRenderPipeline`、`SequencerScripting`、`HDRIBackdrop`、`SunPosition` |
| 关卡资产 | 需有 NavMesh（NavMeshBoundsVolume 或 RecastNavMesh） |

---

## 配置格式

```json
{
    "use_hdr": false,
    "render_type": "char_anim_scene",
    "params": [
        {
            "scene": "/Game/TopDown/Maps/TopDownMap",
            "char": "/Game/Characters/Mannequins/Meshes/SKM_Manny",
            "anim": "/Game/Characters/Mannequin_UE4/Animations/Jog_Fwd",
            "anim_point": 0.23,
            "actor": "/Engine/BasicShapes/Cube",
            "output_dir": "D:/output/circle_test/char_anim_001",
            "distance": 180,
            "rotation_angle": 160,
            "focal_angle": 3
        }
    ]
}
```

### 字段说明

| 字段 | 说明 |
|------|------|
| `use_hdr` | 控制 **HDR 环境光**：`true` 时设置 SkyLight 并从 `Content/HDR` 加载 cubemap 环境贴图（参考脚本 `setup_level_light`）；与输出格式无关 |
| `render_type` | `pure_scene` / `char_anim_scene` / `actor_scene` |
| `params[]` | 任务列表，每个任务渲染 11 张图 |
| `scene` | 关卡包路径（必须） |
| `char` | 骨骼网格体路径（仅 `char_anim_scene`） |
| `anim` | 动画序列路径（仅 `char_anim_scene`） |
| `anim_point` | 动画定格百分位 0~1（仅 `char_anim_scene`） |
| `actor` | 物体资产路径，支持 Blueprint/Class/StaticMesh（仅 `actor_scene`） |
| `output_dir` | 输出目录（必须） |
| `distance` | 中心相机到目标距离（150~250） |
| `rotation_angle` | 水平基准方位角（0~360） |
| `focal_angle` | 环绕半径角（2.5~5），环绕半径 = `distance * tan(focal_angle)` |

---

## 三种渲染模式

| 模式 | 行为 |
|------|------|
| `pure_scene` | 只加载关卡，目标点 = NavMesh 随机点（不做碰撞检测） |
| `char_anim_scene` | 放置骨骼角色（**spawnable**）+ 序列动画轨道定格到 `anim_point` 帧（`play_rate=0` 冻结，不播放）；骨架不同自动 IK 重定向；放置前碰撞检测 |
| `actor_scene` | 放置物体（Blueprint/Class/StaticMesh）；放置前碰撞检测 |

三种模式**共用同一相机轨迹函数** `compute_placements()`，区别仅在于目标点如何获得。

---

## 相机系统（11 张）

每个任务渲染 **11 张**，单相机沿 11 帧轨迹：

```
目标位置 Target = NavMesh 随机点

① 中心相机：Target 前方 distance，绕 Target 绕 Z 轴旋转 rotation_angle 度
② 环绕 10 个：圆心 = 中心相机位置（非目标）
   圆面垂直于 中心相机→目标 连线，半径 = distance * tan(focal_angle)
   圆上均布 10 个方位（每 36°）
③ 全部 11 相机 look-at 目标位置

输出：帧 0 = 中心，帧 1~10 = 环绕
```

---

## 目标点采样与碰撞检测

- **NavMesh 全图随机**：`get_random_location_in_navigable_radius` 大半径采样
- **碰撞检测**：spawn 圆柱体检测体，抬高到角色中心高度（`component_overlap_actors`），只检测真实障碍物（场景装饰物等）；失败则重新随机

---

## 渲染输出（MRQ 双 job）

每个 sequence 提交 **2 个 MRQ job**（与参考脚本一致）：

| Job | 输出 | 抗锯齿 | 深度 pass |
|-----|------|--------|-----------|
| RGB | PNG（`write_alpha=False`） | TSR spatial=16 | 无 |
| Depth | EXR（`multilayer=False`） | 关闭（AAM_NONE） | WorldDepth 材质 |

共享配置：2048×2048、`{frame_number}` 命名、`render_all_cameras`、20 条控制台变量（关运动模糊/HZB、质量拉满）。

---

## 运行

### 前置：修改路径常量

`run_pipeline.py` 顶部有 3 个硬编码路径，按你的环境修改：

```python
ENGINE   = r"D:\pc_program\UE\UE_5.5\Engine\Binaries\Win64\UnrealEditor-Cmd.exe"
PROJECT  = r"D:\ue_dir\demo1\我的项目3\我的项目3.uproject"
SCRIPT   = r"D:\ue_dir\ue_pipeline\render_main.py"
```

### 单任务
```bash
python D:\ue_dir\ue_pipeline\run_pipeline.py
```
（默认使用 `configs/example_config.json`，超时 1200s）

### 指定配置 / 批量
```bash
python D:\ue_dir\ue_pipeline\run_pipeline.py D:\ue_dir\ue_pipeline\configs\example_config_full.json
```

### 指定配置 + 超时
```bash
python D:\ue_dir\ue_pipeline\run_pipeline.py D:\ue_dir\ue_pipeline\configs\example_config.json 1800
```

### 运行机制
1. `run_pipeline.py` 用 `subprocess` 直接启动 `UnrealEditor-Cmd.exe`
2. 命令行 `-ExecutePythonScript=render_main.py`，config 通过环境变量 `RENDER_CONFIG` 传入
3. 引擎加载关卡 → 装配场景 → 构建序列 → MRQ 渲染
4. `run_pipeline.py` 轮询引擎进程，渲染完成后引擎退出、启动器正常结束

---

## 输出

每个任务的 `output_dir` 下生成：
```
output_dir/
├── 000.png ~ 010.png      # RGB（11 张：中心 1 + 环绕 10）
└── FinalImage.000.exr ~   # Depth（WorldDepth pass，EXR 序列）
```

---

## 常见问题

**引擎启动卡在 D3D12 RHI**
命令行模式在部分核显/驱动上可能初始化慢。更新显卡驱动，或确认引擎能正常初始化 RHI。

**脚本找不到兄弟模块**
`render_main.py` 已处理 `sys.path`（`src/` 目录）和模块强制重载，无需手动配置。

**NavMesh 采样失败**
确保关卡有 NavMeshBoundsVolume 或 RecastNavMesh。`ensure_navmesh` 会在无 NavMesh 时自动生成并重建。

**碰撞检测全失败**
检查场景装饰物分布。碰撞检测会正确避开真实障碍，通过率约 1/3，重试 1000 次足够。

---

## 开发

```bash
# 运行 mock 回归测试（不依赖引擎）
python D:\ue_dir\ue_pipeline\tests\test_integration.py
```
