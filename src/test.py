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

    def __init__(self):
        super().__init__("Current source")

    def reset(self):
        self.current = 0

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
        self.instruments[self.PORT_V].voltage = \
            self.instruments[self.PORT_I].current * self.resistance

if __name__ == "__main__":

    server = Server(OhmExperiment, local=False, resistance=1e3)
    try:
        server.run()
    except Exception:
        server.shutdown_event.set()
        raise
