from subprocess import call
import time
call('cvlc testexpressions.mp4 --fullscreen --no-video-title-show --no-embedded-video --no-qt-fs-controller --qt-fullscreen-screennumber=1', shell=True)
time.wait(10)
call('cvlc testexpressions.mp4 --fullscreen --no-video-title-show --no-embedded-video --no-qt-fs-controller --qt-fullscreen-screennumber=1', shell=True)
