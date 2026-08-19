# -*- coding: utf-8 -*-
"""
自动清理上次执行残留的临时资产，避免多次运行互相污染。

清理范围：
1. 场景中上次 spawn 的 Actor：SkeletalMeshActor、CineCameraActor（标签含 cam_）
2. /Game/retarget/ 下所有重定向临时资产（IK Rig / Retargeter / 重定向动画）
3. /Game/LevelSequences/ 下的 MyLevelSequence_* 旧序列

在每次渲染管线启动时调用。
"""

import unreal

# 本次运行生成的资产路径
RETARGET_DIR = "/Game/retarget"
SEQUENCE_DIR = "/Game/LevelSequences"
SEQUENCE_PREFIX = "MyLevelSequence_"


def _destroy_actor(actor):
    """安全销毁 Actor。"""
    try:
        unreal.EditorLevelLibrary.destroy_actor(actor)
    except Exception as e:
        unreal.log_warning(f"cleanup: 销毁 Actor 失败 {actor}: {e}")


def cleanup_scene_actors():
    """清理场景中上次运行生成的临时 Actor（角色、相机）。"""
    actors = unreal.get_editor_subsystem(
        unreal.EditorActorSubsystem).get_all_level_actors()
    removed = 0
    for a in actors:
        label = ""
        try:
            label = a.get_actor_label() or ""
        except Exception:
            pass
        is_skeletal = isinstance(a, unreal.SkeletalMeshActor)
        is_camera = isinstance(a, unreal.CineCameraActor)
        # 相机：标签带 cam_ 前缀（管线生成）；角色：管线生成的 SkeletalMeshActor
        if is_camera and "cam_" in label.lower():
            _destroy_actor(a)
            removed += 1
        elif is_skeletal:
            # 只删管线生成的角色（避免误删关卡原有的 skeletal actor）
            _destroy_actor(a)
            removed += 1
    unreal.log(f"cleanup: 清理场景 Actor {removed} 个")


def cleanup_retarget_assets():
    """删除 /Game/retarget/ 下所有临时资产（含子目录）。"""
    _delete_directory_recursive(RETARGET_DIR)


def cleanup_sequences():
    """删除 /Game/LevelSequences/ 下本管线生成的旧序列。"""
    if not unreal.EditorAssetLibrary.does_directory_exist(SEQUENCE_DIR):
        return
    assets = unreal.EditorAssetLibrary.list_assets(
        SEQUENCE_DIR, recursive=False, include_folder=False)
    removed = 0
    for path in assets:
        name = path.rsplit("/", 1)[-1]
        if name.startswith(SEQUENCE_PREFIX):
            if unreal.EditorAssetLibrary.delete_asset(path):
                removed += 1
    unreal.log(f"cleanup: 清理旧序列 {removed} 个")


def _delete_directory_recursive(dir_path):
    """递归删除资产目录（若存在）。"""
    if not unreal.EditorAssetLibrary.does_directory_exist(dir_path):
        unreal.log(f"cleanup: 目录不存在，跳过: {dir_path}")
        return
    assets = unreal.EditorAssetLibrary.list_assets(
        dir_path, recursive=True, include_folder=False)
    removed = 0
    for path in assets:
        if unreal.EditorAssetLibrary.delete_asset(path):
            removed += 1
    unreal.log(f"cleanup: 删除 {dir_path} 下资产 {removed} 个")
    # 删除目录本身（含空子目录）
    unreal.EditorAssetLibrary.delete_directory(dir_path)


def cleanup_all():
    """执行全部清理。在每次渲染启动前调用。"""
    unreal.log("=== 清理上次执行残留 ===")
    cleanup_scene_actors()
    cleanup_retarget_assets()
    cleanup_sequences()
    unreal.log("=== 清理完成 ===")
