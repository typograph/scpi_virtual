# SCPI Virtual Instrument Server

This project simulates network-connected scientific instruments supporting the SCPI standard.
It runs a webserver with a port open per instrument. Every connected user (distinguished by IP)
gets their own copy of the instrument and can interact with it independently of the others.

## Usage

```
from server import Server, Experiment
from instrument import VirtualInstrument, FloatProperty

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
                
    def sync(self, *args):
        self.instruments[self.PORT_V].voltage.value = \
            self.instruments[self.PORT_I].current.value * self.resistance

if __name__ == "__main__":

    server = Server(OhmExperiment, local=True, resistance=1e3)
    try:
        server.run()
    except Exception:
        server.shutdown_event.set()
        raise
```

We can now connect to the server and run code like

```
import pyvisa
rm = pyvisa.ResourceManager()
voltmeter = rm.open_resource('TCPIP::127.0.0.1::9001::SOCKET', read_termination='\n')
current_source = rm.open_resource('TCPIP::127.0.0.1::9002::SOCKET', read_termination='\n')
current_source.write(":CURR 3")
resistance = voltmeter.query(":VOLT?")/3
```
