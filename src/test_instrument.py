import instrument
import unittest

def thandler_getter(command):
    def handle(query, *args):
        if query:
            return command
        else:
            raise instrument.ProtocolError(f'Command {command} not found')
    return handle

def thandler_setter(command):
    def handle(query, *args):
        if not query:
            return command
        else:
            raise instrument.ProtocolError(f'Command {command}? not found')
    return handle

def thandler_gs(command):
    def handle(query, *args):
        return command
    return handle

class TestReceiver(instrument.SCPI_receiver):
    def __init__(self):
        super().__init__()

    def add_gs(self, command):
        self.add_command(command, thandler_gs(command))
        
        
class TestTreeResolution(unittest.TestCase):

    def setUp(self):
        self.receiver = instrument.SCPI_receiver()
        self.receiver.add_gs = lambda command:self.receiver.add_command(command, thandler_gs(command))
        
        self.receiver.add_gs(':FREQUENCY:START')
        self.receiver.add_gs(':FREQUENCY:STOP')
        self.receiver.add_gs(':FREQUENCY:SLEW')
        self.receiver.add_gs(':FREQUENCY:SLEW:AUTO')
        self.receiver.add_gs(':FREQUENCY:BANDWIDTH')
        self.receiver.add_gs(':POWER:START')
        self.receiver.add_gs(':POWER:STOP')
        self.receiver.add_gs(':BAND')
    
    def assertRun(self, command, *results):
        self.assertEqual(tuple(self.receiver.process(command)), results)
        
    def assertFail(self, command):
        with self.assertRaises(instrument.ProtocolError):
            for resp in self.receiver.process(command):
                print(resp)
    
    def test1(self):
        self.assertRun('FREQ:STAR 3 MHZ;STOP 5 MHZ', ':FREQUENCY:START', ':FREQUENCY:STOP')
        
    def test2(self):
        self.assertRun('FREQ:STAR 3 MHZ;:FREQ:STOP 5 MHZ', ':FREQUENCY:START', ':FREQUENCY:STOP')
        
    def test3(self):
        self.assertFail('FREQ:STAR 3 MHZ;POW:STOP 5 DBM')
        
    def test4(self):
        self.assertRun('FREQ:STAR 3 MHZ;SLEW:AUTO ON',  ':FREQUENCY:START', ':FREQUENCY:SLEW:AUTO')

    def test5(self):
        self.assertFail('FREQ:SLEW:AUTO ON;STOP 5 MHZ')

    def test6(self):
        self.assertFail('FREQ:SLEW 3 MHZ/S;AUTO ON')
        
    def test7(self):
        self.assertRun('FREQ:START 3 MHZ;BAND 1 MHZ',  ':FREQUENCY:START', ':FREQUENCY:BANDWIDTH')
        
    def test8(self):
        self.assertRun('FREQ:START 3 MHz;:BAND A',  ':FREQUENCY:START', ':BAND')
        
    def test9(self):
        self.assertFail('FREQ:SLEW:AUTO ON;3 MHZ/S')
    