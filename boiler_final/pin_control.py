import RPi.GPIO as GPIO

def toggle_pin(pin):
	current_state = GPIO.input(pin)
	if current_state == GPIO.HIGH:
		GPIO.output(pin, GPIO.LOW)
	else:
		GPIO.output(pin, GPIO.HIGH)
