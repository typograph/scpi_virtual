import unittest

from server import Server, Experiment
from instrument import VirtualInstrument, FloatProperty, BoolProperty

class Voltmeter(VirtualInstrument):
    def __init__(self):
        super().__init__("Voltmeter")
        self.voltage = FloatProperty('V', readonly=True)
        self.add_command(":voltage", self.voltage)

class CurrentSource(VirtualInstrument):
    def __init__(self):
        super().__init__("Current source")
        self.current = FloatProperty('A')
        self.add_command(":current", self.current)
        self.is_on = BoolProperty()
        self.add_command(":STATE", self.is_on)

class OhmExperiment(Experiment):
    ports = (PORT_V := 9001,
             PORT_I := 9002)

    def __init__(self, client_ip, resistance):
        super().__init__(client_ip)
        self.resistance = resistance
        self.instruments = {
            self.PORT_V: Voltmeter(),
            self.PORT_I: CurrentSource()
            }
        self.instruments[self.PORT_I].current.add_set_hook(self.sync)
        self.instruments[self.PORT_I].is_on.add_set_hook(self.sync)
                
    def sync(self, *args):
        if self.instruments[self.PORT_I].is_on.value:
            self.instruments[self.PORT_V].voltage.value = \
                self.instruments[self.PORT_I].current.value * self.resistance
        else:
            self.instruments[self.PORT_V].voltage.value = 0


class TestHooks(unittest.TestCase):

    def setUp(self):
        self.experiment = OhmExperiment(None, 1e3)
        
    def assertRun(self, port, command, *results):
        self.assertEqual(tuple(self.experiment.instruments[port].process(command)), results)
        
    def test_creation(self):
        assert True
        
    def test_settable(self):
        self.assertRun(OhmExperiment.PORT_I, ':CURR 3A;:CURR?', None, '3')

    def test_settable(self):
        self.assertRun(OhmExperiment.PORT_I, ':STAT ON;:CURR 3A', None, None)
        self.assertRun(OhmExperiment.PORT_V, ':VOLT?', '3000')
