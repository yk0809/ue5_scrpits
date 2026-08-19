import argparse
import sys

import unreal

# ============================================================
# 动画序列截帧工具（UE 5.5）
#
# 功能：给定一个动画序列，在指定位置（0~1 小数 * 总时长 = 截取时刻）截取一帧，
#       将该帧所有骨骼的局部姿态提取出来，写入一个新的单帧动画序列资产并保存。
#
# 用法（在 UE 5.5 编辑器的 Python 命令行 / 或 -run=pythonscript 下执行）：
#   python cut_animation_frame.py --anim /Game/Animations/MyAnim --ratio 0.5 [--output /Game/Animations/MyAnim_cut]
#
# 说明：
#   - --ratio 为 0~1 之间的小数，对应要截取的那一帧在整段动画中的比例。
#   - 实际目标帧 = round(ratio * (总帧数 - 1))，会 clamp 到 [0, 总帧数-1]。
#   - 输出动画帧率、骨架与源动画一致，数据为单帧（1 个关键帧）。
#
# API 依据：本项目 ue-api-version skill —— 以下 unreal.* 均已在
#   UE 5.5 生成的 unreal.py stub 中核实存在：
#     unreal.AnimationLibrary.get_bone_poses_for_frame / get_animation_track_names / get_num_frames
#     unreal.AnimSequenceFactory + target_skeleton
#     unreal.AssetToolsHelpers.get_asset_tools().create_asset
#     anim_seq.controller (unreal.AnimationDataController):
#       set_frame_rate / set_number_of_frames / add_bone_track / set_bone_track_keys
#     unreal.FrameRate(numerator, denominator) / unreal.FrameNumber(value)
# ============================================================


def _log(msg):
    unreal.log("[截帧工具] " + str(msg))


def _get_anim_asset(anim_asset_path):
    asset = unreal.EditorAssetLibrary.load_asset(anim_asset_path)
    if asset is None:
        raise RuntimeError(f"无法加载动画资产: {anim_asset_path}")
    if not isinstance(asset, unreal.AnimSequence):
        raise RuntimeError(f"资产不是 AnimSequence: {anim_asset_path} -> {asset.__class__.__name__}")
    return asset


def _create_output_sequence(output_path, source_seq):
    """用 AnimSequenceFactory 创建一个新的单帧动画资产，绑定与源动画相同的骨架。"""
    skeleton = source_seq.get_editor_property("skeleton")
    if skeleton is None:
        raise RuntimeError("源动画没有骨架，无法截取骨骼姿态")

    if unreal.EditorAssetLibrary.does_asset_exist(output_path):
        _log(f"输出资产已存在，将直接复用并覆盖数据: {output_path}")
    else:
        factory = unreal.AnimSequenceFactory()
        factory.set_editor_property("target_skeleton", skeleton)

        asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
        new_asset = asset_tools.create_asset(
            unreal.Paths.get_base_filename(output_path),
            unreal.Paths.get_path(output_path),
            unreal.AnimSequence,
            factory,
        )
        if new_asset is None:
            raise RuntimeError(f"创建动画资产失败: {output_path}")
        _log(f"已创建新动画资产: {output_path}")

    seq = unreal.EditorAssetLibrary.load_asset(output_path)
    if seq is None:
        raise RuntimeError(f"无法加载输出资产: {output_path}")
    return seq


def _read_bone_poses(source_seq, frame, bone_names, extract_root_motion):
    """读取指定帧所有骨骼的局部姿态（Local Space）。

    返回 (bone_names, positions, rotations, scales) 三个并行列表。
    get_bone_poses_for_frame 返回与 bone_names 一一对应的 Array[Transform]。
    """
    transforms = unreal.AnimationLibrary.get_bone_poses_for_frame(
        source_seq, bone_names, frame, extract_root_motion
    )
    positions = []
    rotations = []
    scales = []
    for t in transforms:
        positions.append(unreal.Vector(t.translation.x, t.translation.y, t.translation.z))
        rotations.append(unreal.Quat(t.rotation.x, t.rotation.y, t.rotation.z, t.rotation.w))
        scales.append(unreal.Vector(t.scale3d.x, t.scale3d.y, t.scale3d.z))
    return positions, rotations, scales


def extract_frame(source_seq, ratio, output_path):
    """从源动画中按 ratio 截取一帧，写入新的单帧动画序列。"""
    if not (0.0 <= ratio <= 1.0):
        raise RuntimeError(f"ratio 必须在 0~1 之间，收到: {ratio}")

    # 源动画信息（用 AnimationLibrary 的稳定类方法，不依赖 data_model 属性）
    total_seconds = unreal.AnimationLibrary.get_sequence_length(source_seq)
    num_frames = unreal.AnimationLibrary.get_num_frames(source_seq)
    _log(f"源动画: 总时长={total_seconds}s, 帧数={num_frames}")

    # 目标帧 = round(ratio * (总帧数-1))，clamp 到有效范围
    target_frame = int(round(ratio * (num_frames - 1))) if num_frames > 1 else 0
    target_frame = max(0, min(num_frames - 1, target_frame))
    _log(f"ratio={ratio} -> 目标帧 {target_frame}/{num_frames - 1}")

    # 读取所有骨骼轨道名
    bone_names = unreal.AnimationLibrary.get_animation_track_names(source_seq)
    if not bone_names:
        raise RuntimeError("源动画没有骨骼轨道，无法截取")
    _log(f"骨骼轨道数: {len(bone_names)}")

    # 读取目标帧的所有骨骼姿态（extract_root_motion=True 保留根骨骼位移，
    # 否则有 root motion 的动画（如跑步）会丢失根骨骼平移导致角色姿态异常）
    positions, rotations, scales = _read_bone_poses(
        source_seq, target_frame, bone_names, extract_root_motion=True)

    # 创建输出资产
    output_seq = _create_output_sequence(output_path, source_seq)

    # 通过 controller 写入数据（UE 5.5 官方动画数据写入接口）
    controller = output_seq.controller
    if controller is None:
        raise RuntimeError("无法获取输出动画的 AnimationDataController（controller 属性为 None）")

    # 帧率：按源动画首末帧时间间隔推算，秒转帧率（fps）
    fps = 30.0
    if num_frames > 1:
        t0 = unreal.AnimationLibrary.get_time_at_frame(source_seq, 0)
        t1 = unreal.AnimationLibrary.get_time_at_frame(source_seq, num_frames - 1)
        if t1 > t0:
            fps = (num_frames - 1) / (t1 - t0)
    _log(f"推算帧率: {fps:.2f} fps")
    controller.set_frame_rate(unreal.FrameRate(int(round(fps)), 1))
    controller.set_number_of_frames(unreal.FrameNumber(1))

    for i, bone in enumerate(bone_names):
        controller.add_bone_curve(bone)
        controller.set_bone_track_keys(
            bone,
            [positions[i]],
            [rotations[i]],
            [scales[i]],
        )
    _log("关键帧写入完成")

    # 保存
    saved = unreal.EditorAssetLibrary.save_asset(output_path, only_if_is_dirty=True)
    if not saved:
        raise RuntimeError(f"保存资产失败: {output_path}")
    _log(f"完成！单帧动画已保存: {output_path}")
    return output_path


def main():
    parser = argparse.ArgumentParser(description="动画序列截帧工具（UE 5.5）")
    parser.add_argument("--anim", required=True, help="源动画资产路径，如 /Game/Animations/MyAnim")
    parser.add_argument("--ratio", required=True, type=float, help="截取位置（0~1 小数），乘以总帧数得到截取帧")
    parser.add_argument("--output", default=None, help="输出动画资产路径（默认在源动画同目录生成 _cut 后缀）")
    args = parser.parse_args()

    if not (0.0 <= args.ratio <= 1.0):
        _log(f"[错误] ratio 必须在 0~1 之间，收到: {args.ratio}")
        sys.exit(1)

    source_seq = _get_anim_asset(args.anim)

    if args.output is None:
        # 源路径形如 /Game/Dir/Anim.Anim，需去掉 ".对象名" 部分
        base = args.anim.rsplit("/", 1)[-1]
        if "." in base:
            base = base.split(".", 1)[0]
        dir_part = args.anim.rsplit("/", 1)[0] if "/" in args.anim else ""
        args.output = f"{dir_part}/{base}_cut" if dir_part else f"{base}_cut"

    extract_frame(source_seq, args.ratio, args.output)
    _log("全部完成")


if __name__ == "__main__":
    main()
