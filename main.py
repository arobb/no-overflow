# No Overflow - Turn off a switch before a liquid level rises too high
# 19 Aug 2018
# @author Andy Robb andy@andyrobb.com

import board
from digitalio import DigitalInOut, Direction, Pull
from analogio import AnalogIn
import adafruit_dotstar as dotstar
import pulseio
import time


######################### SETTINGS ##############################

# Brightness value 0.0 to 1.0
ledBrightness = 1.0

# Info threshold
infoThresholdVolts = 2.00

# Notification threshold volts
# noticeThresholdVolts = 1.90
noticeThresholdVolts = 2.12

# Warning threshold volts
# warnThresholdVolts = 2.10
warnThresholdVolts = 2.20

# Power switch values
acPowerOn = False
acPowerOff = not acPowerOn

######################### PINS ##############################

# Notification LED
dot = dotstar.DotStar(board.APA102_SCK, board.APA102_MOSI, 1)

# Fluid reading: Analog input on D0
analog1in = AnalogIn(board.D0)

# Power control: Digital output on D3
switch = DigitalInOut(board.D3)
switch.direction = Direction.OUTPUT
switch.value = acPowerOn

# Piezo
piezo = pulseio.PWMOut(board.A4, duty_cycle=0, frequency=440, variable_frequency=True)

######################### HELPERS ##############################

# My queue
class Queue(object):
    def __init__(self, max=None):
        self.max = max
        self.store = []
        
    def __repr__(self):
        return self.store
        
    def __len__(self):
        return len(self.store)
        
    def __iter__(self):
        return iter(self.store)
        
    def append(self,newElem):
        # print("add: "+str(newElem))
        
        if self.max is not None:
            # Reduce by one so we make room for new value
            neededLen = self.max-1
            if len(self) > neededLen:
                while True:
                    self.popleft()
                    if len(self) <= neededLen:
                        break
            
        self.store.append(newElem)
        
    def popleft(self):
        value = self.store[0]
        del self.store[0]
        return value

# Average an iterable
def avg(iter):
    sum = 0
    for index, value in enumerate(iter):
        sum += value
    return sum / float(len(iter))

# Helper to convert analog input to voltage
def getVoltage(pin):
    return (pin.value * 3.3) / 65536

# Helper to give us a nice color swirl
def wheel(pos):
    # Input a value 0 to 255 to get a color value.
    # The colours are a transition r - g - b - back to r.
    if (pos < 0):
        return [0, 0, 0]
    if (pos > 255):
        return [0, 0, 0]
    if (pos < 85):
        return [int(pos * 3), int(255 - (pos*3)), 0]
    elif (pos < 170):
        pos -= 85
        return [int(255 - pos*3), 0, int(pos*3)]
    else:
        pos -= 170
        return [0, int(pos*3), int(255 - pos*3)]

# Color reference
colors = {
    "orange": 52
  , "yellow": 43
  , "red": 85
  , "blue": 170
  , "green": 255
}

# Set specific colors
def getColorValue(color):
    colorValue = colors[color]
    colorValueSafe = wheel(colorValue)
    return colorValueSafe
    
# Play tones
def playTones():
    for f in (523, 440):
        piezo.frequency = f
        piezo.duty_cycle = 65536 // 4  # On 50%
        time.sleep(0.25)  # On for 1/4 second
        piezo.duty_cycle = 0  # Off
        time.sleep(0.05)  # pause between notes

# Class for handling the power switch
class AcPower(object):
    def __init__(self, switch):
        # Cool off period
        self.coolOffSeconds = 60
        
        # Power off time reference
        self.powerOffTime = -1
        
        # Switch object
        self.switch = switch
        
    # Are we cooling off
    def isCoolingOff(self):
        if time.monotonic() - self.powerOffTime < self.coolOffSeconds:
            return True
        else:
            return False

    # Power off AC
    def turnAcOff(self):
        # Set the power off time only if the immediately preceding state
        # is ON
        if self.switch.value is True or self.powerOffTime == -1:
            self.powerOffTime = time.monotonic()
        
        # Turn the switch off
        self.switch.value = acPowerOff
        
        return self.powerOffTime
        
    def turnAcOn(self):
        if not self.isCoolingOff():
            self.switch.value = acPowerOn

# normal, notice, warning
class State(object):
    def __init__(self, infoThreshold, noticeThreshold, warningThreshold):
        self.state = "normal"
        self.infoThreshold = infoThreshold
        self.noticeThreshold = noticeThreshold
        self.warningThreshold = warningThreshold
        
    def getState(self):
        return self.state
        
    def applyInputs(self, *inputs):
        normal = []
        info = []
        notice = []
        warning = []
        
        if len(inputs) < 1:
            return
        
        # Apply booleans based on each input
        for input in inputs:
            if input < self.infoThreshold:
                normal.append(True)
                info.append(False)
                notice.append(False)
                warning.append(False)
                
            elif input >= self.infoThreshold \
            and input < self.noticeThreshold:
                normal.append(False)
                info.append(True)
                notice.append(False)
                warning.append(False)
                
            elif input >= self.noticeThreshold \
            and input < self.warningThreshold:
                normal.append(False)
                info.append(False)
                notice.append(True)
                warning.append(False)
                
            elif input >= self.warningThreshold:
                normal.append(False)
                info.append(False)
                notice.append(False)
                warning.append(True)
                
        # Combine input results
        def reduceAnd(results):
            if len(results) < 1:
                return None
                
            output = True
            for r in results:
                output = output and r
                
            return output
        
        # Determine whether a state change should happen
        if reduceAnd(normal):
            self.state = "normal"
                
        elif reduceAnd(info):
            self.state = "info"
                
        elif reduceAnd(notice):
            self.state = "notice"
                
        elif reduceAnd(warning):
            self.state = "warning"

######################### MAIN LOOP ##############################

# Initialize averaging list
recentLevels = Queue(max=10)

# Initialize an AcPower instance
acPower = AcPower(switch)

# State management
state = State(infoThresholdVolts, noticeThresholdVolts, warnThresholdVolts)

while True:
    # Check input voltage
    liquidLevelVolts = getVoltage(analog1in)
    print("D0: %0.3f" % liquidLevelVolts)
    
    recentLevels.append(liquidLevelVolts)
    print("Avg: %0.3f" % avg(recentLevels))
    
    state.applyInputs(liquidLevelVolts, avg(recentLevels))
    print(state.getState())
    
    # Check for normal values
    # if liquidLevelVolts < noticeThresholdVolts:
    if state.getState() == "normal":
        # Shut off LED
        dot.brightness = 0.0
        dot.show()
        
        # Make sure switch power is normal
        acPower.turnAcOn()
    
    # Check for info
    # elif liquidLevelVolts >= infoThresholdVolts \
    # and liquidLevelVolts < noticeThresholdVolts:
    elif state.getState() == "info":
        dot.brightness = ledBrightness
        dot[0] = getColorValue("orange")
        dot.show()
        
        # Notification threshold should still keep power on
        acPower.turnAcOn()
        
    # Check for notice
    # elif liquidLevelVolts >= noticeThresholdVolts \
    # and liquidLevelVolts < warnThresholdVolts:
    elif state.getState() == "notice":
        dot.brightness = ledBrightness
        dot[0] = getColorValue("orange")
        dot.show()
        
        # Play tones on the piezo
        # playTones()
        
        # Notification threshold should still keep power on
        acPower.turnAcOn()
        
    # Check for warning
    # elif liquidLevelVolts >= warnThresholdVolts:
    elif state.getState() == "warning":
        dot.brightness = ledBrightness
        dot[0] = getColorValue("red")
        dot.show()

        # Play tones on the piezo
        # playTones()
        
        # Turn off AC
        powerOffTime = acPower.turnAcOff()
        print("Power off time: %d" % powerOffTime)
        
    else:
        dot.brightness = ledBrightness
        dot[0] = getColorValue("blue")
        dot.show()

    # Sleep for 500ms
    time.sleep(0.25)

    # Always turn off LED (so it flashes)
    dot.brightness = 0.0
    dot.show()
    
    # Sleep at end of cycle
    time.sleep(0.50)