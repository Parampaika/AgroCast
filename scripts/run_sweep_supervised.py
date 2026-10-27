"""Перезапускает перебор, пока он не завершится успешно (докачка продолжает с места остановки).
Тихий режим: приоритет BelowNormal, без окон, временные файлы на D."""
import os, subprocess, sys, time
ROOT = r"D:\Vault\6_projects\rshb_yield_forecast"
args = sys.argv[1:]
env = dict(os.environ, TEMP=ROOT + r"\data\tmp", TMP=ROOT + r"\data\tmp", JOBLIB_TEMP_FOLDER=ROOT + r"\data\tmp",
           OMP_NUM_THREADS="2")
flags = subprocess.BELOW_NORMAL_PRIORITY_CLASS | subprocess.CREATE_NO_WINDOW
for n in range(15):
    with open(ROOT + r"\data\model\v2\sweep_stdout.txt", "ab") as out:
        rc = subprocess.call(["uv", "run", "python", "-I", "-X", "utf8", "src/model/sweep.py"] + args,
                             cwd=ROOT, stdout=out, stderr=subprocess.STDOUT, env=env, creationflags=flags)
    if rc == 0:
        break
    time.sleep(20)