'''
Created on 07-01-2016

@author: Rodrigo Parra
'''

import sys
import datetime
import time

from twisted.internet import defer
from twisted.internet.protocol import DatagramProtocol
from twisted.internet import reactor
from twisted.python import log
from twisted.internet.task import cooperate
from sense_hat import SenseHat
from evdev import InputDevice, list_devices, ecodes

import txthings.resource as resource
import txthings.coap as coap

import functools
# from multiprocessing import Process
from threading import Thread

JOYSTICK_DEVICE_NAME = 'Raspberry Pi Sense HAT Joystick'
sense = SenseHat()
sense.clear((0, 255, 0))


class LEDDisplayResource (resource.CoAPResource):
    """
    Resource mapping for the LED display of the Sense Hat.
    Supports GET and PUT requests.
    """

    def __init__(self, color="green"):
        resource.CoAPResource.__init__(self)
        self.color = color
        self.colors = {'red': (255, 0, 0), 'green': (0, 255, 0), 'orange': (255, 165, 0)}
        self.visible = True

    def render_GET(self, request):
        response = coap.Message(code=coap.CONTENT, payload=self.color)
        return defer.succeed(response)

    def render_PUT(self, request):
        print 'PUT payload: ' + request.payload
        payload = ""
        if request.payload in self.colors.keys():
            self.color = request.payload
            sense.clear(self.colors[self.color])
            payload = "Color updated succesfully"
        else:
            sense.clear()
            payload = "Invalid color parameter"
            print payload

        response = coap.Message(code=coap.CHANGED, payload=payload)
        return defer.succeed(response)


class JoystickResource (resource.CoAPResource):
    """
    Resource mapping for the joystick of the Sense Hat.
    Supports GET requests.
    """

    def __init__(self, state="down"):
        resource.CoAPResource.__init__(self)
        self.state = state
        self.visible = True
        devices = [InputDevice(fn) for fn in list_devices()]
        self.device = [d for d in devices if d.name == JOYSTICK_DEVICE_NAME][0]
        self.tstamp = time.time()

    def render_GET(self, request):
        response = coap.Message(code=coap.CONTENT, payload=self.state)
        return defer.succeed(response)

    def event_loop(self):
        for event in self.device.read_loop():
            current_time = time.time()
            if current_time - self.tstamp > 1:
                self.__event_check(event)
                self.tstamp = current_time

    def __event_check(self, event):
        flag = False
        if event.type == ecodes.EV_KEY:
            # key down and state up
            if (event.value == 1 and self.state == 'up'):
                # print "from " + self.state + " to down"
                self.state = 'down'
                # LED to green
                sense.clear((0, 255, 0))
                flag = True
            # key up and state down
            if (event.value == 2 and self.state == 'down'):
                # print "from " + self.state + " to up"
                self.state = 'up'
                # LED to red
                sense.clear((255, 0, 0))
                flag = True
            if flag:
                print "state changed to " + self.state
                self.updatedState()
                flag = False
            # print event.value


class CoreResource(resource.CoAPResource):
    """
    Example Resource that provides list of links hosted by a server.
    Normally it should be hosted at /.well-known/core

    Resource should be initialized with "root" resource, which can be used
    to generate the list of links.

    For the response, an option "Content-Format" is set to value 40,
    meaning "application/link-format". Without it most clients won't
    be able to automatically interpret the link format.

    Notice that self.visible is not set - that means that resource won't
    be listed in the link format it hosts.
    """

    def __init__(self, root):
        resource.CoAPResource.__init__(self)
        self.root = root

    def render_GET(self, request):
        data = ["led", "joystick"]
        self.root.generateResourceList(data, "")
        payload = ",".join(data)
        print payload
        response = coap.Message(code=coap.CONTENT, payload=payload)
        response.opt.content_format = coap.media_types_rev['application/link-format']
        return defer.succeed(response)


def _joystick_event_loop(obj):
    obj.event_loop()

# Resource tree creation

log.startLogging(sys.stdout)
root = resource.CoAPResource()
well_known = resource.CoAPResource()
root.putChild('.well-known', well_known)
core = CoreResource(root)
well_known.putChild('core', core)

led = LEDDisplayResource()
root.putChild('led', led)

# Joystick implementation requires additional complexity because it
# involves an event loop which has to run outside of Twisted's loop.
# Using functools.partial allows passing an instance method to multiprocessing
# as described in http://goo.gl/xdA3S4

joystick = JoystickResource()
_bound_joystick_event_loop = functools.partial(_joystick_event_loop, joystick)
p = Thread(target=_bound_joystick_event_loop)
p.daemon = True
p.start()
root.putChild('joystick', joystick)

endpoint = resource.Endpoint(root)
reactor.listenUDP(coap.COAP_PORT, coap.Coap(endpoint))  # , interface="::")
reactor.run()
