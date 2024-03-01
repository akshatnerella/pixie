import subprocess
import time
import paths

VLC_PARAMS = ' --fullscreen --no-video-title-show --no-audio --no-embedded-video --no-qt-fs-controller --mouse-hide-timeout=1 --qt-fullscreen-screennumber=1'

p = subprocess.Popen('cvlc' + paths.SAD + VLC_PARAMS, shell=True)
time.sleep(5)
p.terminate()
#time.sleep(0.001)
x = subprocess.Popen('cvlc' + paths.ANGRY + VLC_PARAMS, shell=True)
time.sleep(5)
#p.terminate()
x.terminate()
