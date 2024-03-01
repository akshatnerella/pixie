import time
import vlc

instance = vlc.Instance("--verbose=0","--no-xlib", "--no-video-title-show", "--no-osd", "--no-snapshot-preview", "--vout mmal_vout")
media_list = instance.media_list_new(['/assets/expressions/angry.mp4', 'assets/expressions/excited.mp4'])
list_player = instance.media_list_player_new()
list_player.set_media_list(media_list)

list_player.set_playback_mode(vlc.PlaybackMode.loop)
list_player.play()

while True:
    time.sleep(300)