import subprocess
import time
p = subprocess.Popen('vlc -L -f assets/expressions/sad.mp4', shell=True)
time.sleep(2)
p.terminate()
time.sleep(0.01)
x = subprocess.Popen('cvlc assets/expressions/love.mp4 --fullscreen --no-video-title-show --no-embedded-video --no-qt-fs-controller --qt-fullscreen-screennumber=1', shell=True)
time.sleep(2)
x.terminate()
