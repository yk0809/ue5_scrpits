# -*- coding: utf-8 -*-
"""
相机组计算：每个 job 渲染 11 张（1 中心 + 10 环绕），全部 look-at 目标。

几何定义（与用户确认）:
- 中心相机 Center = 目标前方 distance，绕目标绕 Z 轴旋转 rotation_angle 度
- 环绕相机（10 个）圆心 = 中心相机位置 Center（不是目标）
  圆面垂直于 "Center->Target" 连线，半径 R = distance * tan(focal_angle)
  在圆上均布 10 个方位（每 36 度）
- 所有相机 rotation = look-at 目标位置

返回: list[(unreal.Vector 位置, unreal.Rotator 朝向)]，索引 0 为中心，1~10 为环绕。
"""

import math

import unreal

# 每 job 张数
CENTER_INDEX = 0
ORBIT_COUNT = 10
TOTAL_SHOTS = CENTER_INDEX + 1 + ORBIT_COUNT


def _deg2rad(d):
    return math.radians(d)


def _look_at_rotation(cam_pos, target):
    """计算 cam_pos 朝向 target 的旋转。"""
    return unreal.MathLibrary.find_look_at_rotation(cam_pos, target)


def compute_placements(target, distance, rotation_angle, focal_angle):
    """
    计算 11 个相机位（位置, 朝向）。

    参数:
        target (unreal.Vector): 目标位置
        distance (float): 中心相机到目标的距离
        rotation_angle (float): 水平基准方位角（度，0~360）
        focal_angle (float): 环绕半径角（度）

    返回:
        list[(unreal.Vector, unreal.Rotator)]: 11 个相机位
    """
    # ---------- ① 中心相机 ----------
    # 世界前向为 +X。先把前向向量绕 Z 轴旋转 rotation_angle 度
    rad = _deg2rad(rotation_angle)
    forward = unreal.Vector(math.cos(rad), math.sin(rad), 0.0)
    center_pos = target + forward * distance

    # ---------- ② 环绕 10 个 ----------
    # 圆心 = 中心相机位置；圆面垂直于 Center->Target 连线
    initial_cam_forward = center_pos - target
    up_world = unreal.Vector(0, 0, 1)

    right = _normalize(_cross(initial_cam_forward, up_world))
    up = _normalize(_cross(initial_cam_forward, right))

    radius = distance * math.tan(_deg2rad(focal_angle))

    placements = [(center_pos, _look_at_rotation(center_pos, target))]

    for k in range(ORBIT_COUNT):
        angle = rad + k * (2 * math.pi / ORBIT_COUNT)
        right_offset = math.cos(angle) * radius
        up_offset = math.sin(angle) * radius
        cam_pos = center_pos + right * right_offset + up * up_offset
        placements.append((cam_pos, _look_at_rotation(cam_pos, target)))

    return placements


def _cross(a, b):
    return unreal.Vector(a.y * b.z - a.z * b.y,
                         a.z * b.x - a.x * b.z,
                         a.x * b.y - a.y * b.x)


def _normalize(vec):
    length = math.sqrt(vec.x ** 2 + vec.y ** 2 + vec.z ** 2)
    if length == 0.0:
        return unreal.Vector(0, 0, 1)
    return unreal.Vector(vec.x / length, vec.y / length, vec.z / length)
