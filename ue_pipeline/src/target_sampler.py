# -*- coding: utf-8 -*-
"""
目标位置采样：NavMesh 全图随机 + 碰撞检测。

- 目标位置通过 NavMesh 随机采样得到（参考脚本 sample_test_location("navmesh") 模式：
  在 NavMeshBoundsVolume 内用大半径 get_random_location_in_navigable_radius = 全图随机）。
- 若需要在目标位置放置角色/物体（char_anim_scene / actor_scene），先做碰撞检测，
  不通过则重新 NavMesh 随机，直到找到可放置点（参考脚本 place_charactor_randomly 模式）。
"""

import random

import unreal


def get_editor_world():
    return unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()


def sample_navmesh_target(world=None, navmesh_actors=None):
    """
    在 NavMesh 全图范围内随机采样一个目标位置。

    返回:
        unreal.Vector | None: 采样到的位置；无 NavMesh 或采样失败返回 None
    """
    world = world or get_editor_world()
    if navmesh_actors is None:
        navmesh_actors = _find_navmesh_actors(world)
    if not navmesh_actors:
        raise RuntimeError("场景中未找到 NavMeshBoundsVolume，无法进行 NavMesh 随机采样")

    nav_mesh = random.choice(navmesh_actors)
    # 大半径（10000）相对 NavMeshBoundsVolume 位置 → 覆盖整个 NavMesh 区域，即全图随机
    point = unreal.NavigationSystemV1.get_random_location_in_navigable_radius(
        world, nav_mesh.get_actor_location(), radius=10000)
    if point is None:
        return None
    return unreal.Vector(point.x, point.y, point.z)


def _find_navmesh_actors(world=None):
    """
    从当前关卡中找出导航相关 Actor，兼容两种形态：
    - NavMeshBoundsVolume（体积型）
    - RecastNavMesh（导航数据，TopDown 模板常用）
    """
    actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    actors = actor_subsystem.get_all_level_actors()
    return [a for a in actors
            if isinstance(a, (unreal.NavMeshBoundsVolume, unreal.RecastNavMesh))]


def _is_foliage(actor):
    return isinstance(actor, (unreal.ProceduralFoliageVolume,
                              unreal.ProceduralFoliageBlockingVolume))


def place_check(world, location, radius, height=100.0, ignore_list=None,
                verbose=False):
    """
    在 location 处检测能否放置角色/物体（半径 radius 内无障碍）。

    实现：spawn 一个圆柱体检测体，抬高到角色站立高度（避免嵌入地面），
    用 component_overlap_actors 检测其碰撞形状与场景物体的重叠。
    过滤植被体积等非阻挡物。

    verbose=True 时打印每次采样的位置、重叠物体明细，便于分析。

    返回:
        bool: True 表示可放置（无碰撞）
    """
    ignore_list = ignore_list or []

    # 生成检测圆柱体（默认 /Engine/BasicShapes/Cylinder 半径 50 高 100，缩放达到目标尺寸）
    mesh_asset = unreal.load_asset("/Engine/BasicShapes/Cylinder")
    probe = unreal.EditorLevelLibrary.spawn_actor_from_class(
        unreal.StaticMeshActor, unreal.Vector(0, 0, 0))
    try:
        probe.static_mesh_component.set_static_mesh(mesh_asset)
        probe.set_actor_scale3d(
            unreal.Vector(radius / 50.0, radius / 50.0, height / 100.0))
        # 抬高到角色中心高度：底部贴地，中心在地面以上 height/2
        probe.set_actor_location(
            unreal.Vector(location.x, location.y, location.z + height / 2.0),
            sweep=False, teleport=True)

        transform = unreal.Transform(
            probe.get_actor_location(), unreal.Rotator(0, 0, 0),
            unreal.Vector(1, 1, 1))
        overlapping = unreal.SystemLibrary.component_overlap_actors(
            component=probe.static_mesh_component,
            component_transform=transform,
            object_types=[unreal.ObjectTypeQuery.OBJECT_TYPE_QUERY1],
            actor_class_filter=None,
            actors_to_ignore=ignore_list)
        if overlapping is None:
            overlapping = []
        real_overlaps = [a for a in overlapping if not _is_foliage(a)]

        if verbose:
            unreal.log(
                f"[place_check] loc=({location.x:.1f},{location.y:.1f},"
                f"{location.z:.1f}) radius={radius} "
                f"重叠={len(overlapping)} 过滤后={len(real_overlaps)}")
            for a in overlapping:
                label = ""
                try:
                    label = a.get_actor_label()
                except Exception:
                    label = type(a).__name__
                unreal.log(
                    f"[place_check]   重叠: {label} "
                    f"[{type(a).__name__}] foliage={_is_foliage(a)}")
        return not real_overlaps
    finally:
        unreal.EditorLevelLibrary.destroy_actor(probe)


def acquire_target(need_place, radius=100.0, max_tries=1000, height=100.0):
    """
    获取目标位置。需要放置时反复 NavMesh 随机 + 碰撞检测，直到成功。

    参数:
        need_place (bool): 是否需要做碰撞检测（pure_scene=False，其余 True）
        radius (float): 碰撞检测球半径
        max_tries (int): 最大尝试次数
        height (float): 保留参数（角色高度约束，当前仅作占位）

    返回:
        unreal.Vector: 目标位置

    异常:
        RuntimeError: 无 NavMesh 或超过最大尝试次数
    """
    world = get_editor_world()
    navmesh_actors = _find_navmesh_actors(world)
    if not navmesh_actors:
        raise RuntimeError("场景中未找到 NavMeshBoundsVolume，无法进行 NavMesh 随机采样")

    sample_fail = 0
    place_fail = 0
    for i in range(max_tries):
        try:
            point = sample_navmesh_target(world, navmesh_actors)
        except RuntimeError:
            raise
        if point is None:
            sample_fail += 1
            continue
        if not need_place or place_check(world, point, radius, height=height):
            unreal.log(f"acquire_target: 成功第 {i + 1} 次尝试, pos=({point.x:.2f}, "
                       f"{point.y:.2f}, {point.z:.2f}) need_place={need_place}")
            return point
        place_fail += 1

    unreal.log_error(
        f"acquire_target: 失败。采样返回 None {sample_fail} 次，"
        f"碰撞检测未通过 {place_fail} 次")
    raise RuntimeError(f"Failed to acquire target after {max_tries} tries")
