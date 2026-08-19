# -*- coding: utf-8 -*-
"""render_main 主流程集成测试（mock unreal）。"""
import json
import math
import os
import sys
import types

# ---------------- mock unreal ----------------
class Vector:
    def __init__(self, x=0, y=0, z=0):
        self.x, self.y, self.z = float(x), float(y), float(z)
    def __add__(self, o): return Vector(self.x + o.x, self.y + o.y, self.z + o.z)
    def __sub__(self, o): return Vector(self.x - o.x, self.y - o.y, self.z - o.z)
    def __mul__(self, s): return Vector(self.x * s, self.y * s, self.z * s)
    def __repr__(self): return 'V(%.1f,%.1f,%.1f)' % (self.x, self.y, self.z)

class Rotator:
    def __init__(self, pitch=0, yaw=0, roll=0):
        self.pitch, self.yaw, self.roll = float(pitch), float(yaw), float(roll)
    def __repr__(self): return 'R(%.1f,%.1f,%.1f)' % (self.pitch, self.yaw, self.roll)

class IntPoint:
    def __init__(self, x, y): self.x, self.y = x, y
class FrameRate:
    def __init__(self, **k): pass
class FrameNumber:
    def __init__(self, value=0): self.value = value

class MathLibrary:
    @staticmethod
    def find_look_at_rotation(cam, t):
        dx, dy, dz = t.x - cam.x, t.y - cam.y, t.z - cam.z
        return Rotator(0.0, math.degrees(math.atan2(dy, dx)) * -1.0, 0.0)

class EnumBase:
    pass

def _make_enum(name, members):
    return type(name, (EnumBase,), members)

unreal = types.ModuleType('unreal')
unreal.Vector = Vector
unreal.Rotator = Rotator
unreal.IntPoint = IntPoint
unreal.FrameRate = FrameRate
unreal.FrameNumber = FrameNumber
unreal.MathLibrary = MathLibrary
unreal.AnimationMode = _make_enum('AnimationMode', {'ANIMATION_SINGLE_NODE': 'single'})
unreal.ObjectTypeQuery = _make_enum('ObjectTypeQuery', {'OBJECT_TYPE_QUERY1': 1})
unreal.AntiAliasingMethod = _make_enum('AntiAliasingMethod', {'AAM_TSR': 'tsr', 'AAM_NONE': 'none'})
unreal.SkyLightSourceType = _make_enum('SkyLightSourceType', {'SLS_SPECIFIED_CUBEMAP': 0})
unreal.CameraFocusMethod = _make_enum('CameraFocusMethod', {'DISABLE': 0})
unreal.RetargetSourceOrTarget = _make_enum('RetargetSourceOrTarget', {'SOURCE': 0, 'TARGET': 1})
unreal.AutoMapChainType = _make_enum('AutoMapChainType', {'EXACT': 0})

unreal.log = lambda *a: None
unreal.log_warning = lambda *a: None
unreal.log_error = lambda *a: None

class Actor:
    def __init__(self):
        self._components = []
    def get_component_by_class(self, cls):
        return cls() if cls.__name__ in ('SkeletalMeshComponent', 'StaticMeshComponent') else None
class SkeletalMeshActor(Actor):
    def __init__(self):
        super().__init__()
        self.skeletal_mesh_component = SkeletalMeshComponent()
class StaticMeshActor(Actor):
    def __init__(self):
        super().__init__()
        self.static_mesh_component = StaticMeshComponent()
class CineCameraActor(Actor):
    def __init__(self):
        self.comp = CineCameraComponent()
    def get_cine_camera_component(self):
        return self.comp
    def set_actor_label(self, l): pass
class NavMeshBoundsVolume(Actor):
    def __init__(self):
        super().__init__()
        self._scale = None
    def get_actor_location(self): return Vector(0, 0, 0)
    def set_actor_scale3d(self, s): self._scale = s
    def get_actor_scale3d(self): return self._scale or Vector(1, 1, 1)
class ProceduralFoliageVolume(Actor): pass
class ProceduralFoliageBlockingVolume(Actor): pass
class SkyLight(Actor):
    def __init__(self): self.light_component = type('L', (), {})()
class SkeletalMeshComponent:
    def __init__(self):
        self.animation_mode = None
        self.animation_data = None
        self.pos = None
        self.rate = None
    def set_skeletal_mesh_asset(self, m): self.mesh = m
    def set_position(self, pos, fire_notifies=True): self.pos = pos
    def set_play_rate(self, rate): self.rate = rate
    def get_editor_property(self, n): return getattr(self, n)
    def set_editor_property(self, n, v): setattr(self, n, v)
class StaticMeshComponent:
    def set_static_mesh(self, m): self.mesh = m
class CameraFocusSettings:
    def __init__(self, **kw): self.__dict__.update(kw)
class CineCameraComponent:
    def __init__(self):
        self.current_focal_length = 0.0
        self.current_aperture = 0.0
        self.aspect_ratio = 0.0
        self.filmback = type('F', (), {'sensor_width': 0.0, 'sensor_height': 0.0})()
        self.focus_settings = None
        self.post_process_settings = type('P', (), {'override_motion_blur_amount': False})()
        self.override_custom_near_clipping_plane = False
        self.custom_near_clipping_plane = 0.0
    def get_editor_property(self, n): return getattr(self, n)
    def set_editor_property(self, n, v): setattr(self, n, v)

unreal.Actor = Actor
unreal.SkeletalMeshActor = SkeletalMeshActor
unreal.StaticMeshActor = StaticMeshActor
unreal.CineCameraActor = CineCameraActor
unreal.RecastNavMesh = type('RecastNavMesh', (), {})
unreal.NavMeshBoundsVolume = NavMeshBoundsVolume
unreal.ProceduralFoliageVolume = ProceduralFoliageVolume
unreal.ProceduralFoliageBlockingVolume = ProceduralFoliageBlockingVolume
unreal.SkyLight = SkyLight
unreal.SkeletalMeshComponent = SkeletalMeshComponent
unreal.StaticMeshComponent = StaticMeshComponent
unreal.CameraFocusSettings = CameraFocusSettings
unreal.CineCameraComponent = CineCameraComponent

class EditorActorSubsystem:
    def __init__(self):
        # 预置一个 NavMeshBoundsVolume，使 NavMesh 随机采样可走通
        self.actors = [NavMeshBoundsVolume()]
    def get_all_level_actors(self): return self.actors
class UnrealEditorSubsystem:
    def get_editor_world(self): return _World()
class EditorAssetSubsystem:
    def find_asset_data(self, p):
        return type('D', (), {'is_valid': lambda self: True})()

class MoviePipelineQueueSubsystem:
    def __init__(self):
        self.queue = MoviePipelineQueue()
        self.executor = None
    def get_queue(self): return self.queue
    def render_queue_with_executor_instance(self, e): self.executor = e
class MoviePipelineQueue:
    def __init__(self): self.jobs = []
    def delete_all_jobs(self): self.jobs = []
    def allocate_new_job(self, cls):
        j = MoviePipelineExecutorJob(); self.jobs.append(j); return j
class MoviePipelineExecutorJob:
    def __init__(self):
        self.cfg = MoviePipelinePrimaryConfig()
        self.sequence = None
        self.map = None
        self.job_name = None
    def set_editor_property(self, n, v): setattr(self, n, v)
    def get_configuration(self): return self.cfg
class MoviePipelinePrimaryConfig:
    def __init__(self): self.settings = {}
    def find_or_add_setting_by_class(self, cls):
        key = cls.__name__
        if key not in self.settings:
            self.settings[key] = cls()
        return self.settings[key]
class _Setting:
    def __init__(self):
        self.cvars = []
    def set_editor_property(self, n, v): setattr(self, n, v)
    def add_or_update_console_variable(self, c, v): self.cvars.append((c, v))
class MoviePipelineOutputSetting(_Setting):
    def __init__(self):
        super().__init__()
        self.output_directory = unreal.DirectoryPath
        self.output_resolution = None
        self.file_name_format = ''
        self.zero_pad_frame_numbers = 0
        self.flush_disk_writes_per_shot = False
class MoviePipelineAntiAliasingSetting(_Setting): pass
class MoviePipelineCameraSetting(_Setting): pass
class MoviePipelineConsoleVariableSetting(_Setting): pass
class MoviePipelineDeferredPassBase(_Setting): pass
class MoviePipelineImageSequenceOutput_PNG(_Setting): pass
class MoviePipelineImageSequenceOutput_EXR(_Setting): pass
class MoviePipelinePostProcessPass(_Setting):
    def __init__(self, enabled=True, material=None, high_precision_output=False, name=''):
        super().__init__()
        self.enabled = enabled
        self.material = material
        self.high_precision_output = high_precision_output
        self.name = name
class MoviePipelinePIEExecutor:
    def __init__(self, subsys):
        self.subsys = subsys
        self.on_executor_finished_delegate = type('Delegate', (), {
            'add_callable_unique': lambda self, cb: None})()

class _TransformSection:
    def set_range_seconds(self, *a): pass
    def get_all_channels(self):
        # 6 个通道：位置 3 + 旋转 3
        return [_Channel(), _Channel(), _Channel(), _Channel(), _Channel(), _Channel()]
class _Channel:
    def add_key(self, *a): pass
class _Track:
    def add_section(self):
        return _TransformSection()
class _Binding:
    def set_name(self, *a): pass
    def add_track(self, cls):
        return _Track()
class _CamCutSection:
    def set_range_seconds(self, *a): pass
    def set_camera_binding_id(self, *a): pass
class _CamCutTrack:
    def add_section(self):
        return _CamCutSection()

class LevelSequence:
    def __init__(self, name):
        self.name = name
    def get_path_name(self): return '/Game/LevelSequences/' + self.name
    def get_name(self): return self.name
    def set_display_rate(self, r): pass
    def set_tick_resolution_directly(self, r): pass
    def set_playback_start_seconds(self, s): pass
    def set_playback_end_seconds(self, s): pass
    def add_track(self, cls):
        if getattr(cls, '__name__', '') == 'MovieSceneCameraCutTrack':
            return _CamCutTrack()
        return _Track()
    def add_spawnable_from_instance(self, obj):
        return _Binding()
    def get_binding_id(self, b): return 'BID'

unreal.EditorActorSubsystem = EditorActorSubsystem
unreal.UnrealEditorSubsystem = UnrealEditorSubsystem
unreal.EditorAssetSubsystem = EditorAssetSubsystem
unreal.MoviePipelineQueueSubsystem = MoviePipelineQueueSubsystem
unreal.MoviePipelineQueue = MoviePipelineQueue
unreal.MoviePipelineExecutorJob = MoviePipelineExecutorJob
unreal.MoviePipelinePrimaryConfig = MoviePipelinePrimaryConfig
unreal.MoviePipelineOutputSetting = MoviePipelineOutputSetting
unreal.MoviePipelineAntiAliasingSetting = MoviePipelineAntiAliasingSetting
unreal.MoviePipelineCameraSetting = MoviePipelineCameraSetting
unreal.MoviePipelineConsoleVariableSetting = MoviePipelineConsoleVariableSetting
unreal.MoviePipelineDeferredPassBase = MoviePipelineDeferredPassBase
unreal.MoviePipelineImageSequenceOutput_PNG = MoviePipelineImageSequenceOutput_PNG
unreal.MoviePipelineImageSequenceOutput_EXR = MoviePipelineImageSequenceOutput_EXR
unreal.MoviePipelinePostProcessPass = MoviePipelinePostProcessPass
unreal.MoviePipelinePIEExecutor = MoviePipelinePIEExecutor
unreal.LevelSequence = LevelSequence
unreal.MovieSceneCameraCutTrack = type('MovieSceneCameraCutTrack', (), {})
unreal.MovieScene3DTransformTrack = type('MovieScene3DTransformTrack', (), {})

# get_editor_subsystem 返回单例，保证测试与管线内部共享同一实例
_SUBSYSTEM_SINGLETONS = {}
def _get_editor_subsystem(cls):
    name = cls.__name__
    if name not in _SUBSYSTEM_SINGLETONS:
        _SUBSYSTEM_SINGLETONS[name] = globals()[name]()
    return _SUBSYSTEM_SINGLETONS[name]
unreal.get_editor_subsystem = _get_editor_subsystem
class _Skeleton:
    def get_path_name(self): return '/Game/Skeletons/Skel'
_SKELETON_SINGLETON = _Skeleton()
class _AnimSeq:
    def __init__(self):
        self.skeleton = _SKELETON_SINGLETON
    def get_name(self): return 'Anim'
    def get_play_length(self): return 2.0
    def get_path_name(self): return '/Game/Animations/Anim'
class _SkelMesh:
    def __init__(self):
        self.skeleton = _SKELETON_SINGLETON
    def get_name(self): return 'SkelMesh'
    def get_path_name(self): return '/Game/Characters/SkelMesh'
class _StaticMeshAsset:
    def get_name(self): return 'StaticMesh'
    def is_a(self, cls): return cls.__name__ == 'StaticMesh'
class _BlueprintAsset:
    def __init__(self):
        self.generated_class = type('BPClass', (), {})
    def get_name(self): return 'BP_Thing'
unreal.AnimSequence = _AnimSeq
unreal.SkeletalMesh = _SkelMesh
unreal.StaticMesh = _StaticMeshAsset
unreal.Blueprint = _BlueprintAsset
unreal.Class = type('Class', (), {})

# load_asset 按路径返回假对象
def _load_asset_mock(path):
    if 'Anim' in path: return _AnimSeq()
    if 'Char' in path or 'SKM' in path: return _SkelMesh()
    if 'Actor' in path: return _StaticMeshAsset()
    if 'BP' in path: return _BlueprintAsset()
    return None
unreal.load_asset = _load_asset_mock
class _World:
    def get_path_name(self): return '/Game/CurrentMap'
unreal.EditorLevelLibrary = type('ELL', (), {
    'spawn_actor_from_class': lambda cls, loc, rot=None: cls(),
    'get_editor_world': lambda: _World(),
    'load_level': lambda p: None,
    'get_all_level_actors': lambda: [],
    'destroy_actor': lambda a: None,
})
unreal.EditorAssetLibrary = type('EAL', (), {
    'list_assets': lambda self, *a, **k: [],
    'make_directory': lambda self, p: None,
    'does_directory_exist': lambda self, p: True,
    'load_asset': lambda self, p: None,
    'save_loaded_asset': lambda self, a: None,
    'delete_asset': lambda self, p: True,
    'delete_directory': lambda self, p: True,
})()
unreal.AssetToolsHelpers = type('ATH', (), {
    'get_asset_tools': lambda self: type('AT', (), {
        'create_asset': lambda self, **k: LevelSequence(k['asset_name'])})()})()
unreal.GameplayStatics = type('GS', (), {
    'set_global_time_dilation': lambda self, *a: None})()
unreal.NavigationSystemV1 = type('NS', (), {
    'get_random_location_in_navigable_radius': lambda self, *a, **k: Vector(10, 20, 30)})()
unreal.SystemLibrary = type('SL', (), {
    'sphere_overlap_actors': lambda self, **k: [],
    'execute_console_command': lambda self, *a, **k: None})()
unreal.EditorPythonScripting = type('EPS', (), {
    'set_keep_python_script_alive': lambda self, v: None})()
class SoftObjectPath:
    def __init__(self, p): self.path = p
unreal.SoftObjectPath = SoftObjectPath
unreal.LevelSequenceFactoryNew = lambda: None
unreal.IKRigDefinition = _Setting
unreal.IKRigDefinitionFactory = lambda: None
unreal.IKRigController = type('IKRC', (), {
    'get_controller': lambda r: type('C', (), {
        'set_skeletal_mesh': lambda *a: None,
        'apply_auto_generated_retarget_definition': lambda *a: None,
        'apply_auto_fbik': lambda *a: None})()})()
unreal.IKRetargeter = _Setting
unreal.IKRetargetFactory = lambda: None
unreal.IKRetargeterController = type('IKTC', (), {
    'get_controller': lambda r: type('C', (), {
        'set_ik_rig': lambda *a: None,
        'set_preview_mesh': lambda *a: None,
        'auto_map_chains': lambda *a: None})()})()
unreal.IKRetargetBatchOperation = type('IKB', (), {
    'duplicate_and_retarget': lambda **k: None})()
unreal.AssetRegistryHelpers = type('ARH', (), {'get_asset_registry': lambda: None})()
unreal.SingleAnimationPlayData = _Setting
unreal.DirectoryPath = type('DP', (), {
    'set_editor_property': lambda self, n, v: setattr(self, n, v)})()
unreal.Transform = lambda *a, **k: None

sys.modules['unreal'] = unreal

# ---------------- 加载管线模块 ----------------
import os

_SRC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src")
_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(mod):
    # render_main 在根目录，其余模块在 src/
    if mod == 'render_main':
        base = _ROOT_DIR
    else:
        base = _SRC_DIR
    path = os.path.join(base, mod + '.py')
    spec = importlib.util.spec_from_file_location(mod, path)
    m = importlib.util.module_from_spec(spec)
    # 注册到 sys.modules，使模块间 `from X import` 复用同一实例
    sys.modules[mod] = m
    spec.loader.exec_module(m)
    return m

import importlib.util
config_parser = _load('config_parser')
camera_rig = _load('camera_rig')
target_sampler = _load('target_sampler')
scene_assembler = _load('scene_assembler')
sequence_builder = _load('sequence_builder')
mrq_renderer = _load('mrq_renderer')
render_main = _load('render_main')

# ---------------- 运行主流程 ----------------
cfg = {
    'use_hdr': True,
    'render_type': 'pure_scene',
    'params': [
        {'scene': '/Game/Maps/A', 'output_dir': 'D:/out/a',
         'distance': 180, 'rotation_angle': 160, 'focal_angle': 3},
        {'scene': '/Game/Maps/B', 'output_dir': 'D:/out/b',
         'distance': 200, 'rotation_angle': 90, 'focal_angle': 4},
        {'scene': '/Game/Maps/C', 'output_dir': 'D:/out/c',
         'char': '/Game/Characters/SKM_Manny', 'anim': '/Game/Animations/Jog',
         'anim_point': 0.23, 'distance': 180, 'rotation_angle': 30, 'focal_angle': 3.5},
        {'scene': '/Game/Maps/D', 'output_dir': 'D:/out/d',
         'actor': '/Game/Actor/Thing', 'distance': 170, 'rotation_angle': 200, 'focal_angle': 4},
    ],
}
with open('_tmp_cfg.json', 'w') as f:
    json.dump(cfg, f)
sys.argv = ['render_main.py', '-config=_tmp_cfg.json']

render_main.main()
os.remove('_tmp_cfg.json')

# ---------------- 断言 ----------------
# render_main 会强制重载模块，从 sys.modules 拿最新的 mrq_renderer 实例
import mrq_renderer as _mrq
subsys = _mrq._subsystem_executor.subsys
n_jobs = len(subsys.queue.jobs)
# 4 个 sequence × 2 job（RGB+Depth）= 8 个 job
assert n_jobs == 8, '应提交 8 个 job (4 sequence × RGB+Depth), got %d' % n_jobs
print('PASS: 提交 %d 个 job（4 sequence × RGB+Depth）' % n_jobs)

# 校验每个 sequence 的 RGB job 和 Depth job 成对出现
job_names = [j.job_name for j in subsys.queue.jobs]
assert sum(1 for n in job_names if 'rgb' in n) == 4, '应有 4 个 RGB job'
assert sum(1 for n in job_names if 'depth' in n) == 4, '应有 4 个 Depth job'
print('PASS: RGB job ×4, Depth job ×4 成对')

# RGB job：PNG 输出 + TSR 抗锯齿
rgb_job = subsys.queue.jobs[0]
rgb_cfg = rgb_job.get_configuration()
out = rgb_cfg.settings['MoviePipelineOutputSetting']
aa = rgb_cfg.settings['MoviePipelineAntiAliasingSetting']
cam = rgb_cfg.settings['MoviePipelineCameraSetting']
assert out.output_resolution.x == 2048
assert out.file_name_format == '{frame_number}'
assert aa.spatial_sample_count == 16, 'RGB: TSR spatial=16'
assert aa.temporal_sample_count == 1
assert aa.anti_aliasing_method == 'tsr'
assert cam.render_all_cameras is True, 'render_all_cameras=True'
assert 'MoviePipelineImageSequenceOutput_PNG' in rgb_cfg.settings, 'RGB job → PNG'
print('PASS: RGB job 输出/AA/PNG 配置正确')

# Depth job：EXR 输出 + 关抗锯齿
depth_job = subsys.queue.jobs[1]
depth_cfg = depth_job.get_configuration()
depth_aa = depth_cfg.settings['MoviePipelineAntiAliasingSetting']
assert depth_aa.spatial_sample_count == 1, 'Depth: 关抗锯齿'
assert depth_aa.anti_aliasing_method == 'none'
assert 'MoviePipelineImageSequenceOutput_EXR' in depth_cfg.settings, 'Depth job → EXR'
print('PASS: Depth job 关AA/EXR 配置正确')

print('PASS: cvar 数量 =', len(rgb_cfg.settings['MoviePipelineConsoleVariableSetting'].cvars))
print('PASS: executor 已提交 =', subsys.executor is not None)
