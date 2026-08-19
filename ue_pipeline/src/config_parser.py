# -*- coding: utf-8 -*-
"""
JSON 配置解析层。

将用户提供的渲染配置 JSON 解析为结构化的 RenderJobConfig 对象，
校验必填字段与取值合法性，并按 render_type 分发。

配置格式（用户提供）:
{
    "use_hdr": true,
    "render_type": "pure_scene",          # pure_scene / char_anim_scene / actor_scene
    "params": [
        {
            "scene": "/Game/TopDown/Maps/TopDownMap",
            "char": "/Game/Characters/Mannequins/Meshes/SKM_Manny",
            "anim": "/Game/Characters/Mannequin_UE4/Animations/Jog_Fwd",
            "anim_point": 0.23,
            "actor": "/Game/xxxx/xxx",
            "output_dir": "D:/output/circle_test/xxx1",
            "distance": 180,
            "rotation_angle": 160,
            "focal_angle": 3
        }
    ]
}
"""

import os

# 支持的渲染模式
RENDER_TYPES = ("pure_scene", "char_anim_scene", "actor_scene")

# 相机参数合理区间（用户约定）
DISTANCE_RANGE = (150.0, 250.0)
FOCAL_ANGLE_RANGE = (2.5, 5.0)
ROTATION_ANGLE_RANGE = (0.0, 360.0)

# 默认渲染分辨率
DEFAULT_WIDTH = 2048
DEFAULT_HEIGHT = 2048


class RenderJobConfig(object):
    """单个 job 的配置。render_type 从管线级传入（用户格式中它是顶层字段）。"""

    def __init__(self, raw, index, render_type):
        self.raw = raw
        self.index = index
        self.render_type = render_type
        self.scene = None          # 关卡包路径
        self.char = None           # 骨骼网格体路径（char_anim_scene）
        self.anim = None           # 动画序列路径（char_anim_scene）
        self.anim_point = 0.0      # 动画定格百分位 0~1
        self.actor = None          # 物体资产路径（actor_scene）
        self.output_dir = None     # 输出目录
        self.distance = 180.0      # 中心相机到目标距离
        self.rotation_angle = 0.0  # 水平基准方位角
        self.focal_angle = 3.0     # 环绕半径角度
        self._parse()

    def _parse(self):
        self.scene = self.raw.get("scene")
        self.char = self.raw.get("char")
        self.anim = self.raw.get("anim")
        self.anim_point = float(self.raw.get("anim_point", 0.0))
        self.actor = self.raw.get("actor")
        self.output_dir = self.raw.get("output_dir")
        self.distance = float(self.raw.get("distance", 180.0))
        self.rotation_angle = float(self.raw.get("rotation_angle", 0.0))
        self.focal_angle = float(self.raw.get("focal_angle", 3.0))

        self._validate()

    def _validate(self):
        if not self.scene:
            raise ValueError(f"job[{self.index}]: 'scene' 关卡路径不能为空")
        if not self.output_dir:
            raise ValueError(f"job[{self.index}]: 'output_dir' 输出目录不能为空")
        if not self._range_check(self.distance, DISTANCE_RANGE):
            raise ValueError(
                f"job[{self.index}]: 'distance'={self.distance} 超出范围 {DISTANCE_RANGE}")
        if not self._range_check(self.focal_angle, FOCAL_ANGLE_RANGE):
            raise ValueError(
                f"job[{self.index}]: 'focal_angle'={self.focal_angle} 超出范围 {FOCAL_ANGLE_RANGE}")
        if not self._range_check(self.rotation_angle, ROTATION_ANGLE_RANGE):
            raise ValueError(
                f"job[{self.index}]: 'rotation_angle'={self.rotation_angle} 超出范围 {ROTATION_ANGLE_RANGE}")
        if not 0.0 <= self.anim_point <= 1.0:
            raise ValueError(
                f"job[{self.index}]: 'anim_point'={self.anim_point} 需在 [0,1]")
        self._check_per_render_type()

    def _check_per_render_type(self):
        """按 render_type 校验对应字段。"""
        # char_anim_scene 需要 char + anim
        if self.render_type == "char_anim_scene":
            if not self.char:
                raise ValueError(f"job[{self.index}]: char_anim_scene 需要 'char' 字段")
            if not self.anim:
                raise ValueError(f"job[{self.index}]: char_anim_scene 需要 'anim' 字段")
        # actor_scene 需要 actor
        if self.render_type == "actor_scene":
            if not self.actor:
                raise ValueError(f"job[{self.index}]: actor_scene 需要 'actor' 字段")

    @staticmethod
    def _range_check(value, rng):
        lo, hi = rng
        return lo <= value <= hi

    def __repr__(self):
        return (f"<RenderJobConfig[{self.index}] {self.render_type} "
                f"scene={self.scene} out={self.output_dir}>")


class RenderPipelineConfig(object):
    """整个渲染任务配置。"""

    def __init__(self, raw):
        self.raw = raw
        self.use_hdr = bool(raw.get("use_hdr", False))
        self.render_type = raw.get("render_type", "pure_scene")
        if self.render_type not in RENDER_TYPES:
            raise ValueError(
                f"不支持的 render_type: {self.render_type}，可选 {RENDER_TYPES}")
        params_raw = raw.get("params", [])
        if not isinstance(params_raw, list) or not params_raw:
            raise ValueError("'params' 必须是非空数组")
        self.jobs = [RenderJobConfig(p, i, self.render_type)
                     for i, p in enumerate(params_raw)]


def load_config(json_path):
    """从 JSON 文件加载配置。"""
    import json

    if not os.path.exists(json_path):
        raise FileNotFoundError(f"配置文件不存在: {json_path}")
    with open(json_path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return RenderPipelineConfig(raw)
