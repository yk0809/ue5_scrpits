# -*- coding: utf-8 -*-
"""
Movie Render Queue 渲染：把 LevelSequence 队列化并批量渲染。

配置与参考脚本 rendering_script_trajectory_static_pure_scene.py 保持一致：
- 每个 sequence 配两个 job：
  1. RGB job：PNG 输出 + TSR 抗锯齿（参考 setup_rgb_job）
  2. Depth job：EXR 输出 + 关抗锯齿 + WorldDepth 深度材质 pass（参考 setup_depth_job）
- 共享配置 common_fig：2048x2048、zero_pad=3、file_name_format="{frame_number}"、
  flush_disk_writes_per_shot、render_all_cameras、控制台变量
- 批量入队全部 sequence 的 job 后一次性用 PIEExecutor 渲染
"""

import unreal

# 输出分辨率
IMAGE_WIDTH = 2048
IMAGE_HEIGHT = 2048

# 深度材质（MRQ 插件自带，插件 Content 挂载为 /MovieRenderPipeline）
DEPTH_MATERIAL_PATH = "/MovieRenderPipeline/Materials/MovieRenderQueue_WorldDepth"

# 保存 executor 引用，避免 Python GC 提前回收导致回调丢失（参考脚本 SubsystemExecutor）
_subsystem_executor = None


def _on_queue_finished(executor, success):
    """MRQ 渲染结束回调（参考脚本 OnQueueFinishedCallback）。"""
    global _subsystem_executor
    unreal.log(f"MRQ 渲染完成, success={success}")
    if _subsystem_executor is not None:
        del _subsystem_executor
    _subsystem_executor = None
    unreal.EditorPythonScripting.set_keep_python_script_alive(False)


def _configure_anti_aliasing(config, enabled):
    """
    抗锯齿配置（参考 setup_anti_aliasing）。
    enabled=True → TSR, spatial=16；enabled=False → 关闭 AA。
    """
    aa_setting = config.find_or_add_setting_by_class(unreal.MoviePipelineAntiAliasingSetting)
    if enabled:
        aa_setting.override_anti_aliasing = True
        aa_setting.anti_aliasing_method = unreal.AntiAliasingMethod.AAM_TSR
        aa_setting.spatial_sample_count = 16
        aa_setting.temporal_sample_count = 1
    else:
        aa_setting.override_anti_aliasing = True
        aa_setting.anti_aliasing_method = unreal.AntiAliasingMethod.AAM_NONE
        aa_setting.spatial_sample_count = 1
        aa_setting.temporal_sample_count = 1
    aa_setting.use_camera_cut_for_warm_up = True
    aa_setting.render_warm_up_frames = True
    return aa_setting


def _configure_common(job, output_dir):
    """所有 job 共享的通用配置（参考 common_fig）。"""
    config = job.get_configuration()

    output_setting = config.find_or_add_setting_by_class(unreal.MoviePipelineOutputSetting)
    output_setting.output_resolution = unreal.IntPoint(IMAGE_WIDTH, IMAGE_HEIGHT)
    output_setting.output_directory.set_editor_property("path", output_dir)
    output_setting.zero_pad_frame_numbers = 3
    output_setting.file_name_format = "{frame_number}"
    output_setting.flush_disk_writes_per_shot = True

    camera_setting = config.find_or_add_setting_by_class(unreal.MoviePipelineCameraSetting)
    camera_setting.render_all_cameras = True

    cvar_setting = config.find_or_add_setting_by_class(unreal.MoviePipelineConsoleVariableSetting)
    for cmd, value in _CONSOLE_VARS:
        cvar_setting.add_or_update_console_variable(cmd, value)

    deferred_pass = config.find_or_add_setting_by_class(unreal.MoviePipelineDeferredPassBase)
    deferred_pass.set_editor_property("disable_multisample_effects", True)


def _setup_rgb_job(job):
    """RGB job：PNG 输出 + TSR 抗锯齿（参考 setup_rgb_job）。"""
    config = job.get_configuration()
    _configure_anti_aliasing(config, enabled=True)
    png = config.find_or_add_setting_by_class(unreal.MoviePipelineImageSequenceOutput_PNG)
    png.set_editor_property("write_alpha", False)


def _setup_depth_job(job):
    """Depth job：EXR 输出 + 关抗锯齿 + WorldDepth 深度材质（参考 setup_depth_job）。"""
    config = job.get_configuration()
    _configure_anti_aliasing(config, enabled=False)
    exr = config.find_or_add_setting_by_class(unreal.MoviePipelineImageSequenceOutput_EXR)
    exr.set_editor_property("multilayer", False)

    depth_material = unreal.load_asset(DEPTH_MATERIAL_PATH)
    depth_pass = unreal.MoviePipelinePostProcessPass(
        enabled=True,
        material=depth_material,
        high_precision_output=True,
        name='Depths')
    deferred_pass = config.find_or_add_setting_by_class(unreal.MoviePipelineDeferredPassBase)
    deferred_pass.additional_post_process_materials = [depth_pass]


def _add_job(queue, sequence, output_dir, job_name, setup_func):
    """向队列添加一个渲染 job（参考 add_job）。"""
    job = queue.allocate_new_job(unreal.MoviePipelineExecutorJob)
    job.set_editor_property("job_name", job_name)
    job.sequence = unreal.SoftObjectPath(sequence.get_path_name())
    job.map = unreal.SoftObjectPath(
        unreal.EditorLevelLibrary.get_editor_world().get_path_name())

    _configure_common(job, output_dir)
    setup_func(job)
    return job


def render_sequences(sequences):
    """
    批量渲染所有序列（参考 render_queues）。
    每个 sequence 配两个 job：RGB(PNG) + Depth(EXR)。

    参数:
        sequences (list[(unreal.LevelSequence, str)]): (序列, 输出目录) 列表

    返回:
        None。渲染异步进行，完成时触发 on_executor_finished_delegate。
    """
    global _subsystem_executor
    subsystem = unreal.get_editor_subsystem(unreal.MoviePipelineQueueSubsystem)
    queue = subsystem.get_queue()
    queue.delete_all_jobs()

    for idx, (sequence, output_dir) in enumerate(sequences):
        suffix = output_dir.rstrip("/").split("/")[-1]
        _add_job(queue, sequence, output_dir,
                 job_name=f"render_rgb_{idx:04d}_{suffix}",
                 setup_func=_setup_rgb_job)
        _add_job(queue, sequence, output_dir,
                 job_name=f"render_depth_{idx:04d}_{suffix}",
                 setup_func=_setup_depth_job)

    _subsystem_executor = unreal.MoviePipelinePIEExecutor(subsystem)
    _subsystem_executor.on_executor_finished_delegate.add_callable_unique(_on_queue_finished)
    subsystem.render_queue_with_executor_instance(_subsystem_executor)
    unreal.log(f"render_sequences: 已提交 {len(sequences) * 2} 个 job ({len(sequences)} sequence × RGB+Depth) 批量渲染")


# 渲染相关控制台变量（参考 common_fig）
_CONSOLE_VARS = (
    ("r.MotionBlurQuality", 0.0),
    ("r.MotionBlur.Amount", 0.0),
    ("r.MotionBlur.Max", 0.0),
    ("r.DefaultFeature.MotionBlur", 0.0),
    ("r.AllowOcclusionQueries", 0.0),
    ("r.ScreenPercentage", 100.0),
    ("sg.ViewDistanceQuality", 4.0),
    ("sg.TextureQuality", 4.0),
    ("sg.ShadowQuality", 4.0),
    ("sg.ReflectionQuality", 4.0),
    ("sg.GlobalIlluminationQuality", 4.0),
    ("r.Nanite", 1.0),
    ("r.HZBOcclusion", 0.0),
    ("r.HZB.Build", 0.0),
    ("r.HZB.VisibilityTest", 0.0),
    ("r.SceneCapture.CaptureSceneDepth", 1.0),
    ("r.SceneCapture.DepthMultiplier", 1.0),
    ("r.SceneCapture.ChunkSize", 0.0),
    ("r.Lumen.HZB", 0.0),
    ("r.Lumen.Reflections.HZB", 0.0),
)
