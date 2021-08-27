from server import Server, Experiment
from instrument import VirtualInstrument, CommandTree, get_float_value, get_bool_value, hookable

from Keithley2450 import Keithley2450
from AMI420 import AMI420

class QHEExperiment(Experiment):
    ports = (PORT_K := 9001,
             PORT_M := 9002)

    def __init__(self, client_ip, diode_isat, diode_breakdown):
        super().__init__(client_ip)
#        self.resistance = resistance
        self.diode_isat = diode_isat
        self.diode_breakdown = diode_breakdown
        self.instruments = {
            self.PORT_K: Keithley2450(),
            self.PORT_M: AMI420(0.1, 0.4)
            }
        self.instruments[self.PORT_M].add_hook(self.sync)
        self.ami = self.instruments[self.PORT_M]
        self.instruments[self.PORT_K].add_hook(self.sync)
        self.kei = self.instruments[self.PORT_K]
                
    def sync(self, *args):
        if self.kei.terminal_side == Keithley2450.TerminalSide.Front:
            if self.kei.current < self.diode_isat * (np.exp(diode_breakdown*11600/300) - 1):
                self.kei.voltage = self.diode_breakdown
            else:
                self.kei.voltage = \
                    (np.log(self.kei.current/self.diode_isat) + 1)*300/11600
        else:
            pass

if __name__ == "__main__":

    import sys

    server = Server(QHEExperiment, local=False, ip=sys.argv[1] if len(sys.argv) > 1 else None, diode_isat=2e-3, diode_breakdown=-5.0)
    try:
        server.run()
    except Exception:
        server.shutdown_event.set()
        raise
