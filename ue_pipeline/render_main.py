# -*- coding: utf-8 -*-
"""
渲染管线主入口。

用法（在 UE 5.5.4 编辑器中）：
    UnrealEditor-Cmd.exe 工程.uproject \
        -ExecutePythonScript="D:/ue_dir/ue_pipeline/Scripts/render_main.py" \
        -config="D:/ue_dir/ue_pipeline/Scripts/example_config.json"

流程：
    1. 解析 JSON 配置（config_parser）
    2. 逐 job：
       a. 加载关卡 + HDR 环境光（scene_assembler.load_scene / setup_hdr_environment）
       b. 装配场景、取得目标位置（按 render_type 分发）
       c. 计算 11 相机位（camera_rig）
       d. 构建 LevelSequence（sequence_builder）
    3. 全部 job 后统一提交 MRQ 批量渲染（mrq_renderer.render_sequences）
    4. 保持脚本存活，等待渲染完成回调
"""

import os
import sys
import traceback

import unreal

# 工程根目录 = 本文件（render_main.py）所在目录
_PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
# 源码在 src/ 子目录
_SRC_DIR = os.path.join(_PROJECT_DIR, "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

# 强制重新加载管线模块：编辑器里 Python 模块一旦 import 会被缓存，
# 不重启时直接跑 render_main 会用到旧版。这里先弹出缓存再 import。
_PIPELINE_MODULES = [
    "config_parser", "cleanup", "target_sampler", "camera_rig",
    "scene_assembler", "sequence_builder", "mrq_renderer",
]
for _mod in _PIPELINE_MODULES:
    sys.modules.pop(_mod, None)

from config_parser import load_config
from cleanup import cleanup_all
from scene_assembler import (
    load_scene, setup_hdr_environment,
    assemble_pure_scene, assemble_char_anim_scene, assemble_actor_scene,
    camera_placements_for,
)
from sequence_builder import build_sequence
from mrq_renderer import render_sequences

# 渲染模式 → 装配函数
_ASSEMBLERS = {
    "pure_scene": assemble_pure_scene,
    "char_anim_scene": assemble_char_anim_scene,
    "actor_scene": assemble_actor_scene,
}


def _parse_args():
    """
    解析 config 路径。

    优先顺序：
    1. 环境变量 RENDER_CONFIG（run_render.bat 里 set）
    2. 命令行 -config=xxx
    3. 默认用脚本同目录的 example_config.json（编辑器内直接执行方便）
    """
    env_config = os.environ.get("RENDER_CONFIG")
    if env_config:
        return env_config
    for arg in sys.argv:
        if arg.startswith("-config="):
            return arg[len("-config="):]
    default_config = os.path.join(_PROJECT_DIR, "configs", "example_config.json")
    if os.path.exists(default_config):
        unreal.log(f"未指定 config，使用默认: {default_config}")
        return default_config
    raise RuntimeError("缺少 config 路径：请设置环境变量 RENDER_CONFIG 或传 -config=")


def _build_job_sequence(job_config, index, use_hdr=False):
    """
    为单个 job 完成场景装配并构建 LevelSequence。

    返回:
        (unreal.LevelSequence, str): 序列资产, 输出目录
    """
    world = load_scene(job_config.scene)

    # use_hdr=True 时设置 HDR 环境光（SkyLight + HDR cubemap，参考脚本 setup_level_light）
    if use_hdr:
        setup_hdr_environment(world)

    assembler = _ASSEMBLERS[job_config.render_type]
    result = assembler(job_config, world)

    # 不同模式返回结构不同：
    # pure_scene / actor_scene → target (Vector)
    # char_anim_scene → (target, char_actor, anim_asset)
    if job_config.render_type == "char_anim_scene":
        target, char_actor, anim_asset = result
    else:
        target = result
        char_actor, anim_asset = None, None

    placements = camera_placements_for(target, job_config)

    sequence = build_sequence(
        asset_name=f"MyLevelSequence_{index:04d}",
        placements=placements,
        target=target,
        sample_idx=index,
        char_actor=char_actor,
        anim_asset=anim_asset,
        anim_point=job_config.anim_point)
    return sequence, job_config.output_dir


def main():
    config_path = _parse_args()
    unreal.log(f"=== 渲染管线启动: {config_path} ===")

    # 清理上次执行残留（场景 Actor、重定向资产、旧序列）
    cleanup_all()

    config = load_config(config_path)
    unreal.log(f"render_type={config.render_type} use_hdr={config.use_hdr} "
               f"jobs={len(config.jobs)}")

    sequences = []
    for index, job in enumerate(config.jobs):
        try:
            unreal.log(f"===== 样本 {index + 1}/{len(config.jobs)} "
                       f"({job.render_type}) =====")
            seq, output_dir = _build_job_sequence(job, index, use_hdr=config.use_hdr)
            sequences.append((seq, output_dir))
        except Exception:
            unreal.log_error(f"样本 {index} 处理失败，跳过")
            traceback.print_exc()
            continue

    if not sequences:
        raise RuntimeError("没有成功构建任何渲染 job，退出")

    unreal.log(f"构建完成 {len(sequences)} 个 job，提交 MRQ 渲染...")
    render_sequences(sequences)


if __name__ == "__main__":
    # 保持脚本存活到渲染异步完成（回调里 set_keep_python_script_alive(False)）
    unreal.EditorPythonScripting.set_keep_python_script_alive(True)
    try:
        main()
    except Exception as e:
        unreal.log_error(f"渲染管线失败: {e}")
        traceback.print_exc()
        unreal.EditorPythonScripting.set_keep_python_script_alive(False)
        sys.exit(1)
