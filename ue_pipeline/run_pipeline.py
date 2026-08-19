# -*- coding: utf-8 -*-
"""
管线启动器：用 Python subprocess 直接启动 UnrealEditor 渲染管线（不经 bat）。

直接执行引擎命令：
    UnrealEditor-Cmd.exe <工程.uproject> -ExecutePythonScript=<render_main.py>

config 通过环境变量 RENDER_CONFIG 传给 render_main（render_main 从环境变量读取）。

用法:
    python run_pipeline.py [config.json] [超时秒数]

默认:
    config: <工程根>/configs/example_config.json
    超时: 1200 秒
"""
import os
import subprocess
import sys
import time

# 路径常量
ENGINE = r"D:\pc_program\UE\UE_5.5\Engine\Binaries\Win64\UnrealEditor-Cmd.exe"
PROJECT = r"D:\ue_dir\demo1\我的项目3\我的项目3.uproject"
SCRIPT = r"D:\ue_dir\ue_pipeline\render_main.py"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONFIG = os.path.join(SCRIPT_DIR, "configs", "example_config.json")
LOG_PATH = os.path.join(SCRIPT_DIR, "_pipeline_run.log")


def _is_engine_running():
    """检查是否有 UnrealEditor 进程在运行（命令行模式 UnrealEditor-Cmd.exe）。"""
    try:
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq UnrealEditor-Cmd.exe", "/NH"],
            capture_output=True, text=True, timeout=10).stdout
        return "UnrealEditor-Cmd.exe" in out
    except Exception:
        return False


def main():
    config = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_CONFIG
    timeout = int(sys.argv[2]) if len(sys.argv) > 2 else 1200

    if not os.path.exists(ENGINE):
        print(f"[ERROR] 引擎不存在: {ENGINE}")
        return 1
    if not os.path.exists(PROJECT):
        print(f"[ERROR] 工程不存在: {PROJECT}")
        return 1
    if not os.path.exists(config):
        print(f"[ERROR] 配置不存在: {config}")
        return 1

    # 构建引擎命令行
    cmd = [ENGINE, PROJECT, "-ExecutePythonScript=" + SCRIPT]
    print(f"[INFO] Engine: {ENGINE}")
    print(f"[INFO] Project: {PROJECT}")
    print(f"[INFO] Script: {SCRIPT}")
    print(f"[INFO] Config: {config}")
    print(f"[INFO] 超时: {timeout}s，日志: {LOG_PATH}")
    print(f"[INFO] 执行: {' '.join(cmd)}")

    # 设置 config 环境变量（引擎子进程继承）
    env = dict(os.environ)
    env["RENDER_CONFIG"] = config

    t0 = time.time()
    with open(LOG_PATH, "w", encoding="utf-8", errors="replace") as logf:
        proc = subprocess.Popen(
            cmd,
            stdout=logf,
            stderr=subprocess.STDOUT,
            cwd=SCRIPT_DIR,
            env=env,
            shell=False,
        )
        # 引擎启动后 Popen 返回；轮询引擎进程直到结束或超时
        deadline = time.time() + timeout
        engine_saw_running = False
        while time.time() < deadline:
            if _is_engine_running():
                engine_saw_running = True
                time.sleep(10)
            elif engine_saw_running:
                print(f"[INFO] 引擎已退出，耗时 {time.time() - t0:.1f}s")
                break
            else:
                # 引擎可能还在启动，短暂等待后重查
                time.sleep(5)

        # 引擎进程是否提前异常退出
        if proc.poll() is not None and proc.returncode != 0 and not engine_saw_running:
            print(f"[ERROR] 引擎提前退出，返回码={proc.returncode}")
            return proc.returncode

        if time.time() >= deadline:
            print(f"[TIMEOUT] {timeout}s 超时，引擎仍在运行")
            return 2

    print(f"[INFO] 管线结束，耗时 {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
