
import pygame
import sys
from pygame.locals import *
import time

# Initialize Pygame
pygame.init()

# Set the screen size to match the display resolution
screen_info = pygame.display.Info()
screen_width = screen_info.current_w
screen_height = screen_info.current_h
screen = pygame.display.set_mode((screen_width, screen_height), FULLSCREEN)

# Set the background color to black
background_color = (0, 0, 0)
screen.fill(background_color)

# Set the eye colors and outline color
eye_color = (0, 0, 0)
outline_color = (255, 255, 255)

# Set the eye positions and radius
eye_radius = 50
left_eye_pos = (screen_width // 2 - 150, screen_height // 2)
right_eye_pos = (screen_width // 2 + 150, screen_height // 2)

# Set the blinking interval in seconds
blink_interval = 1

# Start the main loop
running = True
last_blink_time = time.time()

while running:
    # Handle events
    for event in pygame.event.get():
        if event.type == QUIT or (event.type == KEYDOWN and event.key == K_ESCAPE):
            running = False

    # Clear the screen
    screen.fill(background_color)

    # Calculate the time since the last blink
    current_time = time.time()
    time_since_last_blink = current_time - last_blink_time

    # Draw the eyes
    if time_since_last_blink >= blink_interval:
        # Draw the eyes with the outline
        pygame.draw.circle(screen, outline_color, left_eye_pos, eye_radius + 5)
        pygame.draw.circle(screen, outline_color, right_eye_pos, eye_radius + 5)
        # Draw the eyes without the outline
        pygame.draw.circle(screen, eye_color, left_eye_pos, eye_radius)
        pygame.draw.circle(screen, eye_color, right_eye_pos, eye_radius)
        # Update the last blink time
        last_blink_time = current_time

    # Update the display
    pygame.display.flip()

# Quit Pygame
pygame.quit()
sys.exit()
