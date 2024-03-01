import subprocess
import time
import paths

VLC_PARAMS_INIT = ' --fullscreen --no-video-title-show --no-audio --no-embedded-video --no-qt-fs-controller --mouse-hide-timeout=1 --qt-fullscreen-screennumber=1'
VLC_PARAMS_ADD = ' --fullscreen --no-video-title-show --no-audio --no-embedded-video --no-qt-fs-controller --mouse-hide-timeout=1 --qt-fullscreen-screennumber=1 --playlist-enqueue'

p = subprocess.Popen('cvlc' + VLC_PARAMS_ADD + paths.LOVE, shell=True)
time.sleep(10)
#p.terminate()
#time.sleep(0.001)
x = subprocess.Popen('cvlc' + VLC_PARAMS_ADD + paths.ANGRY, shell=True)
time.sleep(5)
x.terminate()
