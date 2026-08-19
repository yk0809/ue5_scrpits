# -*- coding: utf-8 -*-
"""用引擎跑 multiframe_test.py 验证脚本。"""
import subprocess
import sys

ENGINE = r"D:\pc_program\UE\UE_5.5\Engine\Binaries\Win64\UnrealEditor-Cmd.exe"
PROJECT = r"D:\ue_dir\demo1\我的项目3\我的项目3.uproject"
SCRIPT = r"D:\ue_dir\ue_pipeline\tests\multiframe_test.py"

cmd = [ENGINE, PROJECT, "-ExecutePythonScript=" + SCRIPT]
print("[INFO] 执行:", " ".join(cmd))
proc = subprocess.Popen(cmd)
try:
    proc.wait(timeout=300)
    print(f"[INFO] 退出码: {proc.returncode}")
except subprocess.TimeoutExpired:
    proc.kill()
    print("[TIMEOUT] 300s 超时")
    sys.exit(2)
