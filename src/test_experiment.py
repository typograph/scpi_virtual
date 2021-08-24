import unittest

from server import Server, Experiment
from instrument import VirtualInstrument, CommandTree, get_float_value, get_bool_value, hookable

class Voltmeter(VirtualInstrument):
    commands = CommandTree(VirtualInstrument.commands)
    
    @commands.add(':VOLTAGE?')
    def get_voltage(self):
        return '{:.2f}'.format(self.voltage)
    
    def __init__(self):
        super().__init__("Voltmeter")
        
    def reset(self):
        self.voltage = 0
        super().reset()

class CurrentSource(VirtualInstrument):

    commands = CommandTree(VirtualInstrument.commands)
    
    @commands.add(':current?')
    def get_current(self):
        return '{:.2f}'.format(self.current)
    
    @commands.add(':current')
    @hookable('current')
    def set_current(self, parsed_value):
        self.current = get_float_value(parsed_value, default=0, min_max=(-10, 10), units='A')

    @commands.add(':STATE?')
    def is_on(self):
        return str(int(self.is_on))
        
    @commands.add(':STATE')
    @hookable('state')
    def set_on(self, parsed_value):
        self.is_on = get_bool_value(parsed_value, default=False)

    def __init__(self):
        super().__init__("Current source")

    def reset(self):
        self.current = 0
        self.is_on = False

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
        self.instruments[self.PORT_I].add_hook(self.sync)
                
    def sync(self, *args):
        if self.instruments[self.PORT_I].is_on:
            self.instruments[self.PORT_V].voltage = \
                self.instruments[self.PORT_I].current * self.resistance
        else:
            self.instruments[self.PORT_V].voltage = 0


class TestHooks(unittest.TestCase):

    def setUp(self):
        self.experiment = OhmExperiment(None, 1e3)
        
    def assertRun(self, port, command, *results):
        self.assertEqual(tuple(self.experiment.instruments[port].process(command)), results)
        
    def test_creation(self):
        assert True
        
    def test_settable(self):
        self.assertRun(OhmExperiment.PORT_I, ':CURR 3A;:CURR?', None, '3.00')

    def test_synched(self):
        self.assertRun(OhmExperiment.PORT_I, ':STAT ON;:CURR 3A', None, None)
        self.assertRun(OhmExperiment.PORT_V, ':VOLT?', '3000.00')
