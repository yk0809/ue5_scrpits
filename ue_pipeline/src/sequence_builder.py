# -*- coding: utf-8 -*-
"""
Level Sequence 构建：一个 sequence、一个相机，遍历 11 个相机位各渲染一帧。

实现（与用户确认）：
- 创建 1 个 CineCameraActor（spawnable 绑定）
- 序列共 11 帧，该相机的 3D 变换轨道写入 11 个关键帧（位置+旋转）
- 一个 CameraCut section 绑定该相机，覆盖整个序列
- MRQ 渲染整个序列 → 每帧渲染一帧 → 共 11 张图
  （帧 0 = 中心相机位，帧 1~10 = 环绕相机位）

相机配置：固定分辨率一致，焦距/光圈/后处理统一设置（保证各张图视觉一致）。
"""

import unreal

SEQUENCE_DIR = "/Game/LevelSequences"
FRAMERATE = 240
WARM_UP_FRAMES = 32

# 相机内参
CAMERA_FOCAL_LENGTH = 35.0
CAMERA_SENSOR_WIDTH = 50.0
CAMERA_SENSOR_HEIGHT = 50.0
CAMERA_APERTURE = 5.6


def build_sequence(asset_name, placements, target, sample_idx=0,
                   char_actor=None, anim_asset=None, anim_point=0.0):
    """
    构建一个包含 11 帧相机轨迹的 LevelSequence（单个相机）。

    若提供 char_actor + anim_asset，角色以 spawnable 加入序列，
    并用序列动画轨道定格到 anim_point 帧（不播放，直接停在该姿态）。

    参数:
        asset_name (str): 序列资源名
        placements (list[(Vector, Rotator)]): 11 个相机位
        target (Vector): 目标位置（校验用）
        sample_idx (int): 样本索引
        char_actor (Actor|None): 角色 actor（spawnable 用）
        anim_asset (AnimSequenceBase|None): 动画资产
        anim_point (float): 动画定格百分位 0~1

    返回:
        unreal.LevelSequence: 创建的序列资产（已保存）
    """
    if not unreal.EditorAssetLibrary.does_directory_exist(SEQUENCE_DIR):
        unreal.EditorAssetLibrary.make_directory(SEQUENCE_DIR)

    asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
    sequence = asset_tools.create_asset(
        asset_name=asset_name,
        package_path=SEQUENCE_DIR,
        asset_class=unreal.LevelSequence,
        factory=unreal.LevelSequenceFactoryNew())

    total_frames = len(placements)  # 11
    sequence.set_display_rate(unreal.FrameRate(numerator=FRAMERATE, denominator=1))
    sequence.set_tick_resolution_directly(
        unreal.FrameRate(numerator=FRAMERATE * 100, denominator=1))
    sequence.set_playback_start_seconds(0.0)
    sequence.set_playback_end_seconds(float(total_frames) / FRAMERATE)

    # 角色以 spawnable 加入序列 + 动画轨道定格（若有）
    if char_actor is not None and anim_asset is not None:
        _add_char_animation(sequence, char_actor, anim_asset, anim_point,
                            total_frames)

    # 创建 1 个相机
    camera_actor = _spawn_camera(placements[0][0], placements[0][1], sample_idx)
    binding = sequence.add_spawnable_from_instance(camera_actor)
    binding.set_name("cam_main")
    binding_id = sequence.get_binding_id(binding)

    # 3D 变换轨道：11 个关键帧，每帧一个相机位
    transform_track = binding.add_track(unreal.MovieScene3DTransformTrack)
    transform_section = transform_track.add_section()
    channels = transform_section.get_all_channels()

    for idx, (cam_pos, cam_rot) in enumerate(placements):
        frame_number = unreal.FrameNumber(idx)
        for c_idx, value in enumerate((cam_pos.x, cam_pos.y, cam_pos.z)):
            channels[c_idx].add_key(frame_number, value)
        for c_idx, value in enumerate((cam_rot.roll, cam_rot.pitch, cam_rot.yaw)):
            channels[c_idx + 3].add_key(frame_number, value)

    # 一个 CameraCut section 覆盖整个序列，绑定该相机
    camera_cut_track = sequence.add_track(unreal.MovieSceneCameraCutTrack)
    camera_cut_section = camera_cut_track.add_section()
    camera_cut_section.set_range_seconds(
        -float(WARM_UP_FRAMES) / FRAMERATE, float(total_frames) / FRAMERATE)
    camera_cut_section.set_camera_binding_id(binding_id)

    unreal.EditorAssetLibrary.save_loaded_asset(sequence)
    unreal.log(f"build_sequence: 已保存 {sequence.get_path_name()} "
               f"({total_frames} 帧轨迹, 1 相机)")
    return sequence


def _add_char_animation(sequence, char_actor, anim_asset, anim_point, total_frames):
    """
    把角色作为 spawnable 加入序列，用序列动画轨道定格到 anim_point 帧。

    定格方式：动画轨道 start_frame_offset = 目标帧、play_rate=0 → 直接停在目标姿态。
    section 覆盖整个序列时间（total_frames 帧），保证多帧序列全程保持同一姿态。
    """
    # 角色 spawnable 绑定
    char_binding = sequence.add_spawnable_from_instance(char_actor)
    char_binding.set_name("spawn_char")

    # 序列动画轨道
    anim_track = char_binding.add_track(unreal.MovieSceneSkeletalAnimationTrack)
    anim_section = anim_track.add_section()
    # section 覆盖整个序列时间（负 warmup 到结束），多帧序列全程生效
    anim_section.set_range_seconds(
        -float(WARM_UP_FRAMES) / FRAMERATE, float(total_frames) / FRAMERATE)

    # 计算定格帧号
    play_len = anim_asset.get_play_length()
    target_time = anim_point * play_len
    freeze_frame = unreal.AnimationLibrary.get_frame_at_time(anim_asset, target_time)

    params = anim_section.get_editor_property("params")
    params.set_editor_property("animation", anim_asset)
    params.set_editor_property("start_frame_offset", unreal.FrameNumber(freeze_frame))
    params.set_editor_property("end_frame_offset", unreal.FrameNumber(freeze_frame))
    # play_rate=0 冻结，不播放
    params.set_editor_property("play_rate", unreal.MovieSceneTimeWarpVariant(0.0))
    anim_section.set_editor_property("params", params)

    unreal.log(f"_add_char_animation: 角色 spawnable + 动画轨道定格 "
               f"{anim_asset.get_name()} 帧 {freeze_frame} (play_rate=0)")


def _spawn_camera(cam_pos, cam_rot, sample_idx):
    """创建并配置 CineCameraActor，返回 actor。"""
    camera_actor = unreal.EditorLevelLibrary.spawn_actor_from_class(
        unreal.CineCameraActor, cam_pos, cam_rot)
    camera_actor.set_actor_label(f"cam_main_{sample_idx:04d}")

    component = camera_actor.get_cine_camera_component()
    component.current_focal_length = CAMERA_FOCAL_LENGTH
    component.current_aperture = CAMERA_APERTURE
    component.aspect_ratio = 1.0
    component.filmback.sensor_width = CAMERA_SENSOR_WIDTH
    component.filmback.sensor_height = CAMERA_SENSOR_HEIGHT
    component.focus_settings = unreal.CameraFocusSettings(
        focus_method=unreal.CameraFocusMethod.DISABLE)

    # 后处理：关运动模糊，保证静帧干净
    pp_settings = component.get_editor_property("post_process_settings")
    pp_settings.override_motion_blur_amount = True
    pp_settings.motion_blur_amount = 0.0
    pp_settings.override_motion_blur_max = True
    pp_settings.motion_blur_max = 0.0
    component.set_editor_property("post_process_settings", pp_settings)

    component.override_custom_near_clipping_plane = True
    component.custom_near_clipping_plane = 0.0
    return camera_actor
