import subprocess
import time
p = subprocess.Popen('cvlc testexpressions.mp4 --fullscreen --no-video-title-show --no-embedded-video --no-qt-fs-controller --qt-fullscreen-screennumber=1', shell=True)
time.sleep(1)
p.terminate()
time.sleep(1)
subprocess.Popen('cvlc testexpressions.mp4 --fullscreen --no-video-title-show --no-embedded-video --no-qt-fs-controller --qt-fullscreen-screennumber=1', shell=True)