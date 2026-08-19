# -*- coding: utf-8 -*-
"""
场景装配：加载关卡、按 render_type 装配场景内容、绑定动画（必要时重定向）。

三种模式：
- pure_scene      ：只加载关卡，目标点 = NavMesh 随机点
- char_anim_scene ：加载关卡 + 放置骨骼角色 + 绑定动画定格，目标点 = NavMesh 随机点（碰撞检测）
- actor_scene     ：加载关卡 + 放置物体，目标点 = NavMesh 随机点（碰撞检测）

动画绑定策略：
- 骨架相同：直接绑定动画序列
- 骨架不同：自动 IK 重定向到角色骨架（IKRetargetBatchOperation），再绑定

定格方式：SkeletalMeshComponent 单节点动画模式 + set_position(anim_point*时长) + set_play_rate(0)。
"""

import unreal

from camera_rig import compute_placements
from target_sampler import acquire_target

# 重定向动画输出目录
RETARGET_DIR = "/Game/retarget"


def _load_asset(path):
    """加载资产，失败时抛出明确异常。"""
    asset = unreal.load_asset(path)
    if asset is None:
        raise RuntimeError(f"无法加载资产: {path}")
    return asset


def _spawn_actor(actor_class, location, rotation=None):
    rotation = rotation or unreal.Rotator(0.0, 0.0, 0.0)
    return unreal.EditorLevelLibrary.spawn_actor_from_class(
        actor_class, location, rotation)


def _editor_world():
    return unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()


def _all_level_actors():
    return unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()


# ---------------------------------------------------------------------------
# 关卡与全局状态
# ---------------------------------------------------------------------------
def load_scene(scene_path):
    """加载关卡，冻结全局时间，并确保 NavMesh 可用。"""
    unreal.EditorLevelLibrary.load_level(scene_path)
    world = _editor_world()
    # 场景全局静止，避免环境动画/时间流逝影响静帧
    unreal.GameplayStatics.set_global_time_dilation(world, 0.0)
    ensure_navmesh(world)
    return world


def ensure_navmesh(world):
    """
    确保关卡有可用的 NavMesh。

    诊断结论（2026-08-09）：
    - get_random_location_in_navigable_radius 在已构建 NavMesh 上能正常采样
    - 但 RebuildNavigation 会销毁已保存的 NavMesh 数据（rebuild 后采样全 None）
    - 因此：仅当关卡没有任何 NavMeshBoundsVolume 时才 spawn + rebuild；
      已有 NavMeshBoundsVolume 时直接跳过，保留已构建的数据。
    """
    actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    has_bounds_volume = any(
        isinstance(a, unreal.NavMeshBoundsVolume)
        for a in actor_subsystem.get_all_level_actors())
    if not has_bounds_volume:
        unreal.log("ensure_navmesh: 无 NavMeshBoundsVolume，生成一个并触发 RebuildNavigation")
        _spawn_scene_covering_navmesh_volume()
        unreal.SystemLibrary.execute_console_command(world, "RebuildNavigation")
        unreal.log("ensure_navmesh: 已触发 RebuildNavigation")
    else:
        unreal.log("ensure_navmesh: 已有 NavMeshBoundsVolume，跳过 rebuild（保留已构建数据）")


def _spawn_scene_covering_navmesh_volume():
    """
    生成一个覆盖当前场景范围的 NavMeshBoundsVolume。

    默认圆柱 brush 半径 200 / 高 160（cm），放大到 100x 覆盖约 20000cm 范围，
    足以覆盖绝大多数关卡的可走区域。
    """
    vol = unreal.EditorLevelLibrary.spawn_actor_from_class(
        unreal.NavMeshBoundsVolume,
        unreal.Vector(0, 0, 0),
        unreal.Rotator(0, 0, 0))
    vol.set_actor_scale3d(unreal.Vector(100, 100, 40))
    unreal.log(f"ensure_navmesh: 已生成 NavMeshBoundsVolume "
               f"scale={vol.get_actor_scale3d()}")


def setup_hdr_environment(world):
    """
    配置 HDR 环境光（use_hdr=True 时调用）。
    使用关卡中已有的 SkyLight 并从 Content/HDR 加载 cubemap。
    """
    cubemaps = unreal.EditorAssetLibrary.list_assets(
        "/Game/HDR", recursive=False, include_folder=False)
    sky_lights = [a for a in _all_level_actors()
                  if isinstance(a, unreal.SkyLight)]
    if not sky_lights:
        unreal.log_warning("setup_hdr_environment: 场景中没有 SkyLight，跳过")
        return
    sky_light = sky_lights[0]
    light_comp = sky_light.light_component
    light_comp.set_editor_property("real_time_capture", False)
    light_comp.set_editor_property(
        "source_type", unreal.SkyLightSourceType.SLS_SPECIFIED_CUBEMAP)
    if cubemaps:
        cubemap = unreal.load_asset(cubemaps[0])
        light_comp.set_editor_property("cubemap", cubemap)


# ---------------------------------------------------------------------------
# 三种模式的场景装配
# ---------------------------------------------------------------------------
def assemble_pure_scene(job_config, world):
    """纯场景：目标点 = NavMesh 随机点，不做碰撞检测。"""
    return acquire_target(need_place=False)


def assemble_char_anim_scene(job_config, world):
    """
    角色 + 动画场景：放置骨骼角色（spawnable），动画定格交给序列动画轨道。

    返回:
        (unreal.Vector, unreal.Actor, AnimSequenceBase):
        目标位置, 角色 actor（待加入序列作 spawnable）, 动画资产
    """
    target = acquire_target(need_place=True, radius=_char_spawn_radius(job_config))
    char_actor = _spawn_skeletal_actor(job_config.char, target)
    anim_asset = _resolve_animation(job_config)
    return target, char_actor, anim_asset


def assemble_actor_scene(job_config, world):
    """物体放置场景：在目标点放置 actor 资产。"""
    target = acquire_target(need_place=True, radius=50.0)
    _spawn_actor_asset(job_config.actor, target)
    return target


def _char_spawn_radius(job_config):
    """角色放置碰撞检测半径：基于 distance 估算，避免相机穿模角色。"""
    return max(50.0, job_config.distance * 0.15)


def _spawn_skeletal_actor(char_path, location):
    """生成骨骼网格角色 Actor（spawnable 用），返回 actor。"""
    skel_mesh = _load_asset(char_path)
    actor = _spawn_actor(unreal.SkeletalMeshActor, location)
    component = actor.get_component_by_class(unreal.SkeletalMeshComponent)
    if component is None:
        raise RuntimeError(f"角色 Actor 没有 SkeletalMeshComponent: {char_path}")
    component.set_skeletal_mesh_asset(skel_mesh)
    return actor


def _spawn_actor_asset(actor_path, location):
    """
    加载并放置物体资产到指定位置。

    支持的类型：
    - Blueprint 资产：取其 generated_class 生成 actor
    - Class：直接生成
    - StaticMesh：放入 StaticMeshActor
    - 其他：生成空 actor 并告警
    """
    actor_asset = _load_asset(actor_path)

    # 1. Blueprint 资产 → generated_class 生成
    if isinstance(actor_asset, unreal.Blueprint):
        actor_class = actor_asset.generated_class
        if actor_class:
            spawned = unreal.EditorLevelLibrary.spawn_actor_from_class(
                actor_class, location)
            if spawned:
                unreal.log(f"assemble_actor_scene: 放置 Blueprint "
                           f"{actor_path} @ ({location.x:.1f},{location.y:.1f})")
                return spawned
        unreal.log_warning(f"资产 {actor_path} 的 Blueprint 无 generated_class")

    # 2. 直接是 Class → 生成
    if isinstance(actor_asset, unreal.Class):
        spawned = unreal.EditorLevelLibrary.spawn_actor_from_class(
            actor_asset, location)
        if spawned:
            unreal.log(f"assemble_actor_scene: 放置 Class "
                       f"{actor_path} @ ({location.x:.1f},{location.y:.1f})")
            return spawned

    # 3. StaticMesh → 放入 StaticMeshActor
    if isinstance(actor_asset, unreal.StaticMesh):
        spawned = _spawn_actor(unreal.StaticMeshActor, location)
        sm_component = spawned.get_component_by_class(unreal.StaticMeshComponent)
        if sm_component:
            sm_component.set_static_mesh(actor_asset)
        unreal.log(f"assemble_actor_scene: 放置 StaticMesh "
                   f"{actor_path} @ ({location.x:.1f},{location.y:.1f})")
        return spawned

    # 4. 兜底
    unreal.log_warning(f"资产 {actor_path} 类型 {type(actor_asset)} 无法直接放置，已生成空 Actor")
    return _spawn_actor(unreal.Actor, location)


# ---------------------------------------------------------------------------
# 动画绑定与定格
# ---------------------------------------------------------------------------
def _resolve_animation(job_config):
    """
    解析动画资产：骨架相同直接绑定，骨架不同自动 IK 重定向。
    返回可绑定到角色的 AnimSequence。
    """
    char_skel = _skeleton_of(job_config.char)
    anim_skel = _skeleton_of(job_config.anim)
    if char_skel == anim_skel:
        anim_asset = _load_asset(job_config.anim)
        unreal.log(f"_resolve_animation: 骨架相同，直接使用 {job_config.anim}")
        return anim_asset

    unreal.log(f"_resolve_animation: 骨架不同，执行 IK 重定向")
    return _retarget_animation(
        source_path=job_config.anim,
        target_skeletal_mesh_path=job_config.char,
        sample_idx=job_config.index)


def _skeleton_of(skeletal_mesh_path):
    """取骨骼网格体资产绑定的 Skeleton。"""
    asset = _load_asset(skeletal_mesh_path)
    skeleton = asset.get_editor_property("skeleton")
    if skeleton is None:
        raise RuntimeError(f"资产 {skeletal_mesh_path} 没有 Skeleton")
    return skeleton


# ---------------------------------------------------------------------------
# 动画重定向（骨架不同时）
# ---------------------------------------------------------------------------
def _retarget_animation(source_path, target_skeletal_mesh_path, sample_idx):
    """
    将源动画重定向到目标骨骼网格体骨架，返回重定向后的动画资产。

    所有重定向临时资产（IK Rig / Retargeter / 重定向动画）都放在
    /Game/retarget/sample_{idx:04d}/ 下，创建前删除同名旧资产，避免多次运行冲突。
    """
    target_mesh = _load_asset(target_skeletal_mesh_path)
    source_anim = _load_asset(source_path)

    out_dir = f"{RETARGET_DIR}/sample_{sample_idx:04d}"
    unreal.EditorAssetLibrary.make_directory(out_dir)

    target_rig = _create_ik_rig(target_mesh, f"IK_target_{sample_idx:04d}", out_dir)
    source_skel = source_anim.get_editor_property("skeleton")
    source_mesh = _find_skeletal_mesh_for_skeleton(source_skel)
    if source_mesh is None:
        source_mesh = _find_skeletal_mesh_same_dir(source_skel)
    if source_mesh is None:
        source_mesh = target_mesh
        unreal.log_warning("未找到源骨架对应网格，使用目标网格作为源（重定向可能不完整）")
    source_rig = _create_ik_rig(source_mesh, f"IK_source_{sample_idx:04d}", out_dir)

    retargeter = _create_retargeter(source_rig, target_rig, source_mesh, target_mesh,
                                    f"RTG_{sample_idx:04d}", out_dir)

    result = unreal.IKRetargetBatchOperation.duplicate_and_retarget(
        assets_to_retarget=[_asset_data_for(source_path)],
        source_mesh=source_mesh,
        target_mesh=target_mesh,
        ik_retarget_asset=retargeter,
        search="",
        replace="",
        prefix=f"s{sample_idx}_",
        suffix="",
        include_referenced_assets=True)
    if not result:
        raise RuntimeError("动画重定向失败：duplicate_and_retarget 未返回结果")

    retargeted = result[0].get_asset()
    new_path = f"{out_dir}/{source_anim.get_name()}"
    old_path = retargeted.get_path_name()
    if old_path == new_path:
        return retargeted
    # 目标已存在（多次运行复用同一 sample 目录）→ 删除旧的再重命名，避免冲突
    if unreal.EditorAssetLibrary.does_asset_exist(new_path):
        unreal.log(f"_retarget_animation: 目标 {new_path} 已存在，删除后重命名")
        unreal.EditorAssetLibrary.delete_asset(new_path)
    unreal.EditorAssetLibrary.rename_asset(old_path, new_path)
    return _load_asset(new_path)


def _create_ik_rig(skeletal_mesh, name, package_path):
    """创建 IK Rig 资源并配置骨架 + FABIK。同名旧资产先删除。"""
    asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
    full_path = f"{package_path}/{name}"
    if unreal.EditorAssetLibrary.does_asset_exist(full_path):
        unreal.EditorAssetLibrary.delete_asset(full_path)
    rig = asset_tools.create_asset(
        asset_name=name, package_path=package_path,
        asset_class=unreal.IKRigDefinition,
        factory=unreal.IKRigDefinitionFactory())
    controller = unreal.IKRigController.get_controller(rig)
    controller.set_skeletal_mesh(skeletal_mesh)
    controller.apply_auto_generated_retarget_definition()
    controller.apply_auto_fbik()
    return rig


def _create_retargeter(source_rig, target_rig, source_mesh, target_mesh, name,
                       package_path):
    """创建 IK Retargeter 并映射源/目标链。同名旧资产先删除。"""
    asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
    full_path = f"{package_path}/{name}"
    if unreal.EditorAssetLibrary.does_asset_exist(full_path):
        unreal.EditorAssetLibrary.delete_asset(full_path)
    retargeter = asset_tools.create_asset(
        asset_name=name, package_path=package_path,
        asset_class=unreal.IKRetargeter,
        factory=unreal.IKRetargetFactory())
    controller = unreal.IKRetargeterController.get_controller(retargeter)
    controller.set_ik_rig(unreal.RetargetSourceOrTarget.SOURCE, source_rig)
    controller.set_ik_rig(unreal.RetargetSourceOrTarget.TARGET, target_rig)
    controller.set_preview_mesh(unreal.RetargetSourceOrTarget.SOURCE, source_mesh)
    controller.set_preview_mesh(unreal.RetargetSourceOrTarget.TARGET, target_mesh)
    controller.auto_map_chains(unreal.AutoMapChainType.EXACT, True)
    return retargeter


def _find_skeletal_mesh_for_skeleton(skeleton):
    """根据 Skeleton 找到引用它的第一个 SkeletalMesh 资产。返回 None 表示未找到。"""
    registry = unreal.AssetRegistryHelpers.get_asset_registry()
    skeleton_path = skeleton.get_path_name()
    opts = unreal.AssetRegistryDependencyOptions()
    referencers = registry.get_referencers(skeleton_path, reference_options=opts)
    if not referencers:
        unreal.log_warning(f"_find_skeletal_mesh_for_skeleton: 无资产引用 Skeleton {skeleton_path}")
        return None
    for ref in referencers:
        assets = registry.get_assets_by_package_name(ref)
        if assets and assets[0].asset_class_path.asset_name == "SkeletalMesh":
            return unreal.load_asset(str(assets[0].package_name))
    return None


def _find_skeletal_mesh_same_dir(skeleton):
    """兜底：在 Skeleton 资产同目录下找 SkeletalMesh。"""
    registry = unreal.AssetRegistryHelpers.get_asset_registry()
    skeleton_path = skeleton.get_path_name()
    pkg_dir = skeleton_path.rsplit("/", 1)[0]
    unreal.log(f"_find_skeletal_mesh_same_dir: 在 {pkg_dir} 下找 SkeletalMesh")
    assets = registry.get_assets_by_path(pkg_dir, recursive=True)
    if not assets:
        return None
    for a in assets:
        if a.asset_class_path.asset_name == "SkeletalMesh":
            return unreal.load_asset(str(a.package_name))
    return None


def _asset_data_for(path):
    """返回资产的 AssetData，不存在时抛异常。"""
    subsystem = unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)
    asset_data = subsystem.find_asset_data(path)
    if not asset_data.is_valid():
        raise RuntimeError(f"资产不存在: {path}")
    return asset_data


# ---------------------------------------------------------------------------
# 相机组（本模块导出，供 sequence 构建使用）
# ---------------------------------------------------------------------------
def camera_placements_for(target, job_config):
    """计算 11 个相机位。"""
    return compute_placements(
        target=target,
        distance=job_config.distance,
        rotation_angle=job_config.rotation_angle,
        focal_angle=job_config.focal_angle)
