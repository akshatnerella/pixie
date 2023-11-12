import RPi.GPIO as GPIO
import time

# Replace 17 with your chosen GPIO pin for the servo
servo_pin = 17

def center_servo(pin):
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(pin, GPIO.OUT)

    pwm = GPIO.PWM(pin, 50)
    pwm.start(0)

    try:
        duty_cycle = 7.5  # Adjust this value based on your servo's specifications
        pwm.ChangeDutyCycle(duty_cycle)
        time.sleep(1)

    finally:
        pwm.stop()
        GPIO.cleanup()

def sweep_servo(pin):
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(pin, GPIO.OUT)

    pwm = GPIO.PWM(pin, 50)
    pwm.start(0)

    try:
        for angle in range(0, 181, 10):  # Move in 10-degree steps
            duty_cycle = angle / 18 + 2
            pwm.ChangeDutyCycle(duty_cycle)
            time.sleep(0.5)  # Adjust this value for the desired speed

    finally:
        pwm.stop()
        GPIO.cleanup()

# Test the centering function
center_servo(servo_pin)

# Test the sweeping function
sweep_servo(servo_pin)

#Center again to end
center_servo(servo_pin)

#Testing link
