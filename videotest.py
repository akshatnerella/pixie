import subprocess
import time

params = ' --fullscreen --repeat --no-video-title-show --no-audio --no-embedded-video --no-qt-fs-controller --qt-fullscreen-screennumber=1 --vout mmal_vout'

p = subprocess.Popen('cvlc assets/expressions/sad.mp4' + params, shell=True)
time.sleep(2)
p.terminate()
time.sleep(0.01)
x = subprocess.Popen('cvlc assets/expressions/love.mp4' + params, shell=True)
time.sleep(2)
x.terminate()
