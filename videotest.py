import subprocess
import time
p = subprocess.Popen('cvlc assets/expressions/happy.mp4 --fullscreen --no-video-title-show --no-embedded-video --no-qt-fs-controller --qt-fullscreen-screennumber=1', shell=True)
time.sleep(2)
p.terminate()
time.sleep(2)
x = subprocess.Popen('cvlc assets/expressions/love.mp4 --fullscreen --no-video-title-show --no-embedded-video --no-qt-fs-controller --qt-fullscreen-screennumber=1', shell=True)
time.sleep(2)
x.terminate()
