# -*- coding: utf-8 -*-
"""
定格验证（同相机两帧渲染对比）：
序列 2 帧，相机完全静止，角色动画 play_rate=0 定格在 anim_point。

如果帧 0 和帧 1 渲染图（角色区域）像素完全一致 → 角色姿态定格生效。
若动画在播放，两帧姿态会不同，像素必然不同。
"""
import unreal


def log(msg):
    unreal.log(f"[FREEZE2] {msg}")


def main():
    unreal.EditorLevelLibrary.load_level("/Game/TopDown/Maps/TopDownMap")
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()

    # 1. spawn 角色
    skel_mesh = unreal.load_asset("/Game/Characters/Mannequins/Meshes/SKM_Manny")
    actor = unreal.EditorLevelLibrary.spawn_actor_from_class(
        unreal.SkeletalMeshActor, unreal.Vector(1500, 1500, 10))
    comp = actor.get_component_by_class(unreal.SkeletalMeshComponent)
    comp.set_skeletal_mesh_asset(skel_mesh)

    anim = unreal.load_asset("/Game/Characters/Mannequin_UE4/Animations/Jog_Fwd")
    play_len = anim.get_play_length()
    anim_point = 0.5
    freeze_frame = unreal.AnimationLibrary.get_frame_at_time(anim, anim_point * play_len)
    log(f"动画 {anim.get_name()} 时长={play_len:.3f}s, anim_point={anim_point}, 定格帧={freeze_frame}")

    # 2. 构建序列（2 帧，相机静止）
    seq_dir = "/Game/LevelSequences"
    if not unreal.EditorAssetLibrary.does_directory_exist(seq_dir):
        unreal.EditorAssetLibrary.make_directory(seq_dir)
    seq_name = "Freeze2_Seq"
    seq_full = f"{seq_dir}/{seq_name}"
    if unreal.EditorAssetLibrary.does_asset_exist(seq_full):
        unreal.EditorAssetLibrary.delete_asset(seq_full)

    total_frames = 2
    FRAMERATE = 240
    sequence = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        asset_name=seq_name, package_path=seq_dir,
        asset_class=unreal.LevelSequence,
        factory=unreal.LevelSequenceFactoryNew())
    sequence.set_display_rate(unreal.FrameRate(numerator=FRAMERATE, denominator=1))
    sequence.set_playback_end_seconds(float(total_frames) / FRAMERATE)

    # 角色 spawnable + 动画轨道定格
    char_binding = sequence.add_spawnable_from_instance(actor)
    char_binding.set_name("spawn_char")
    anim_track = char_binding.add_track(unreal.MovieSceneSkeletalAnimationTrack)
    anim_section = anim_track.add_section()
    anim_section.set_range_seconds(0.0, float(total_frames) / FRAMERATE)
    params = anim_section.get_editor_property("params")
    params.set_editor_property("animation", anim)
    params.set_editor_property("start_frame_offset", unreal.FrameNumber(freeze_frame))
    params.set_editor_property("end_frame_offset", unreal.FrameNumber(freeze_frame))
    params.set_editor_property("play_rate", unreal.MovieSceneTimeWarpVariant(0.0))
    anim_section.set_editor_property("params", params)
    log(f"角色动画轨道: 定格帧={freeze_frame}, play_rate=0, section覆盖{total_frames}帧")

    # 相机：静止，写入 3D 变换轨道关键帧（每帧相同位置，确保相机完全不动）
    cam = unreal.EditorLevelLibrary.spawn_actor_from_class(
        unreal.CineCameraActor, unreal.Vector(1500, 1800, 150))
    cam_rot = unreal.MathLibrary.find_look_at_rotation(
        unreal.Vector(1500, 1800, 150), unreal.Vector(1500, 1500, 10))
    cam.set_actor_location_and_rotation(
        unreal.Vector(1500, 1800, 150), cam_rot, False, True)
    cam_binding = sequence.add_spawnable_from_instance(cam)
    cam_binding.set_name("cam_main")
    cam_bid = sequence.get_binding_id(cam_binding)

    # 相机 3D 变换轨道：两帧写入相同位置/旋转
    cam_transform = cam_binding.add_track(unreal.MovieScene3DTransformTrack)
    cam_section = cam_transform.add_section()
    cam_channels = cam_section.get_all_channels()
    cam_loc = unreal.Vector(1500, 1800, 150)
    for f in range(total_frames):
        fn = unreal.FrameNumber(f)
        for ci, v in enumerate((cam_loc.x, cam_loc.y, cam_loc.z)):
            cam_channels[ci].add_key(fn, v)
        for ci, v in enumerate((cam_rot.roll, cam_rot.pitch, cam_rot.yaw)):
            cam_channels[ci + 3].add_key(fn, v)

    cut_track = sequence.add_track(unreal.MovieSceneCameraCutTrack)
    cut_section = cut_track.add_section()
    cut_section.set_range_seconds(0.0, float(total_frames) / FRAMERATE)
    cut_section.set_camera_binding_id(cam_bid)

    unreal.EditorAssetLibrary.save_loaded_asset(sequence)
    log(f"序列已保存: {sequence.get_path_name()}, {total_frames} 帧, 相机静止")

    # 3. MRQ 渲染 2 帧
    subsystem = unreal.get_editor_subsystem(unreal.MoviePipelineQueueSubsystem)
    queue = subsystem.get_queue()
    queue.delete_all_jobs()
    job = queue.allocate_new_job(unreal.MoviePipelineExecutorJob)
    job.set_editor_property("job_name", "freeze2")
    job.sequence = unreal.SoftObjectPath(sequence.get_path_name())
    job.map = unreal.SoftObjectPath(world.get_path_name())
    cfg = job.get_configuration()
    out = cfg.find_or_add_setting_by_class(unreal.MoviePipelineOutputSetting)
    out.output_resolution = unreal.IntPoint(512, 512)
    out.output_directory.set_editor_property("path", "D:/output/freeze2")
    out.file_name_format = "{frame_number}"
    out.zero_pad_frame_numbers = 3
    cfg.find_or_add_setting_by_class(unreal.MoviePipelineImageSequenceOutput_PNG)
    aa = cfg.find_or_add_setting_by_class(unreal.MoviePipelineAntiAliasingSetting)
    aa.override_anti_aliasing = True
    aa.anti_aliasing_method = unreal.AntiAliasingMethod.AAM_TSR
    aa.spatial_sample_count = 16
    aa.temporal_sample_count = 1

    def on_finished(executor, success):
        log(f"渲染完成 success={success}")
        unreal.EditorPythonScripting.set_keep_python_script_alive(False)

    global executor_ref
    executor_ref = unreal.MoviePipelinePIEExecutor(subsystem)
    executor_ref.on_executor_finished_delegate.add_callable_unique(on_finished)
    subsystem.render_queue_with_executor_instance(executor_ref)
    log("渲染已提交（2 帧，相机静止）")


if __name__ == "__main__":
    unreal.EditorPythonScripting.set_keep_python_script_alive(True)
    main()
