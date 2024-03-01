import cv2
import time
import paths

# Load the first video
video1 = cv2.VideoCapture(paths.LOVE)

# Get the video dimensions
width = int(video1.get(cv2.CAP_PROP_FRAME_WIDTH))
height = int(video1.get(cv2.CAP_PROP_FRAME_HEIGHT))

# Create a fullscreen window
cv2.namedWindow('Fullscreen', cv2.WINDOW_NORMAL)
cv2.setWindowProperty('Fullscreen', cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

# Wait for 2 seconds
time.sleep(2)

# Load the second video
video2 = cv2.VideoCapture(paths.ANGRY)

# Loop through the frames of the first video
while video1.isOpened():
    ret1, frame1 = video1.read()
    if not ret1:
        break

    # Show the frame in fullscreen
    cv2.imshow('Fullscreen', frame1)

    # Check if 2 seconds have passed
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# Loop through the frames of the second video
while video2.isOpened():
    ret2, frame2 = video2.read()
    if not ret2:
        break

    # Show the frame in fullscreen
    cv2.imshow('Fullscreen', frame2)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# Release the video capture objects and close the windows
video1.release()
video2.release()
cv2.destroyAllWindows()