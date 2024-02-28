import numpy as np
import cv2

cap = cv2.VideoCapture('testexpressions.mp4')

while True:
    ret, frame = cap.read()
    cv2.namedWindow('output', cv2.WINDOW_NORMAL)  # Create a resizable window
    cv2.setWindowProperty('output', cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)  # Set the window to full screen
    cv2.imshow('output', frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
