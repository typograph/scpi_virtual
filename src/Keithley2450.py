import datetime
import enum
import threading
import time

import instrument
from instrument import hookable, ProtocolError
from instrument import VirtualInstrument as VI
from instrument import CommandTree as CT


def not_implemented_write(self):
    pass
    
def not_implemented_query(self):
    return ''

class Keithley2450(VI):
    commands = CT(VI.commands)
    defaults = dict(VI.defaults)
    
    commands[':SYStem:LFRequency?'] = not_implemented_query
    commands[':SYStem:BEEPer'] = not_implemented_write

    CommLanguage = instrument.scpi_enum('Language', ('SCPI', 'SCPI2400', 'TSP'))
    defaults['communication_language'] = CommLanguage.SCPI
    commands['*LANG?'] = lambda s:s.communication_language.name
    commands['*LANG'] = not_implemented_write
    
    TerminalSide = instrument.scpi_enum('TerminalSide', ('FRONT', 'BACK'))
    defaults['terminal_side'] = TerminalSide.FRONT
    commands[':ROUTe:TERMinals?'] = lambda s:s.terminal_side.name
    @commands.add(':ROUTe:TERMimals')
    @hookable('terminal_side')
    def set_terminal_side(self, side):
        self.terminal_side = instrument.get_symbol_value(TerminalSide, side)

    commands[":SENSe[1]:COUNt?"] = not_implemented_query
    commands[":SENSe[1]:COUNt"] = not_implemented_write
    commands[":SENSe[1]:AZERo:ONCE"] = not_implemented_write
    
#    SenseFunction = instrument.scpi_enum('SenseFunction', ('Current', 'Resistance', 'Voltage'))
#    defaults['sense_function'] = SenseFunction.VOLTAGE
    commands[":SENSe[1]:FUNC"] = not_implemented_write
    commands[":SENSe[1]:FUNC?"] = lambda s:'"VOLT:DC"'#s.sense_function.name

    for _sense_function in ('Current[:DC]','Voltage[:DC]', 'Resistance'):
        for _i_user in range(1,6):
            commands[f':SENSE[1]:{_sense_function}:DELay:USER{_i_user}?'] = not_implemented_query
            commands[f':SENSE[1]:{_sense_function}:DELay:USER{_i_user}'] = not_implemented_write
        commands[f':SENSe[1]:{_sense_function}:RSENse'] = not_implemented_write
        commands[f':SENSe[1]:{_sense_function}:RSENse?'] = not_implemented_query
        commands[f':SENSe[1]:{_sense_function}:RANGe'] = not_implemented_write
        commands[f':SENSe[1]:{_sense_function}:RANGe?'] = not_implemented_query
        commands[f':SENSe[1]:{_sense_function}:RANGe:AUTO'] = not_implemented_write
        commands[f':SENSe[1]:{_sense_function}:RANGe:AUTO?'] = not_implemented_query
        commands[f':SENSe[1]:{_sense_function}:NPLCycles?'] = not_implemented_query
        commands[f':SENSe[1]:{_sense_function}:NPLCycles'] = not_implemented_write
        commands[f':SENSe[1]:{_sense_function}:AZERo?'] = not_implemented_query
        commands[f':SENSe[1]:{_sense_function}:AZERo'] = not_implemented_write

    del _sense_function

    SourceFunction = instrument.scpi_enum('SourceFunction', ('Current', 'Voltage'))
    defaults['source_function'] = SourceFunction.CURRENT
    commands[":SOURce[1]:FUNCtion[:ON]"] = not_implemented_write
    commands[":SOURce[1]:FUNCtion[:ON]?"] = lambda s:'CURR'#s.source_function.name

    defaults['current'] = 0
    @commands.add(f":SOURce[1]:CURRent[:LEVel][:IMMediate][:AMPLitude]")
    @hookable('current')
    def set_source_current(self, value):
        self.current = instrument.get_float_value(value, units='A', default=0, min_max=(-10, 10))
        
    commands[f":SOURce[1]:CURRent[:LEVel][:IMMediate][:AMPLitude]?"] = lambda s:f'{s.current:.4f}'
    
    defaults['voltage'] = 0
    commands[f":SOURce[1]:VOLTage[:LEVel][:IMMediate][:AMPLitude]"] = not_implemented_write
    commands[f":SOURce[1]:VOLTage[:LEVel][:IMMediate][:AMPLitude]?"] = not_implemented_query


    for _source_function in ('Current','Voltage'):
        for _i_user in range(1,6):
            commands[f":SOURce[1]:{_source_function}:DELay:USER{_i_user}?"] = not_implemented_query
            commands[f":SOURce[1]:{_source_function}:DELay:USER{_i_user}"] = not_implemented_write

        commands[f":SOURce[1]:{_source_function}:RANGe"] = not_implemented_write
        commands[f":SOURce[1]:{_source_function}:RANGe?"] = not_implemented_query
        commands[f":SOURce[1]:{_source_function}:RANGe:AUTO"] = not_implemented_write
        commands[f":SOURce[1]:{_source_function}:RANGe:AUTO?"] = not_implemented_query
        
        commands[f":SOURce[1]:{_source_function}:VLIM"] = not_implemented_write
        commands[f":SOURce[1]:{_source_function}:VLIM?"] = not_implemented_query
        commands[f":SOURce[1]:{_source_function}:VLIM:TRIPped?"] = not_implemented_query

        commands[f":SOURce[1]:{_source_function}:ILIM"] = not_implemented_write
        commands[f":SOURce[1]:{_source_function}:ILIM?"] = not_implemented_query
        commands[f":SOURce[1]:{_source_function}:ILIM:TRIPped?"] = not_implemented_query

        commands[f":SOURce[1]:{_source_function}:DELay?"] = not_implemented_query
        commands[f":SOURce[1]:{_source_function}:DELay"] = not_implemented_write
        commands[f":SOURce[1]:{_source_function}:DELay:AUTO?"] = not_implemented_query
        commands[f":SOURce[1]:{_source_function}:DELay:AUTO"] = not_implemented_write

        commands[f":SOURce[1]:{_source_function}:READ:BACK?"] = not_implemented_query
        commands[f":SOURce[1]:{_source_function}:READ:BACK"] = not_implemented_write

        commands[f":SOURce[1]:SWEep:{_source_function}:LINear"] = not_implemented_write
        
    del _source_function
    del _i_user

    @commands.add(":TRACe:MAKE")
    def make_trace(self, buffer_name, size, style):
        pass
    
    @commands.add(":TRACe:POINts?")
    def get_trace_points(self, buffer_name):
        return ''
        
    @commands.add(":TRACe:POINts")
    def set_trace_points(self, buffer_name):
        pass
        
    @commands.add(":TRACe:ACTual?")
    def actual_trace(self, buffer_name):
        return ''

    @commands.add(":TRACe:DATA?")
    def get_trace_data(self, start, end, buffer_name):
        return ''

    @commands.add(":TRACe:CLEar")
    def clear_trace(self, buffer_name):
        pass

    @commands.add(":TRACe:TRIGger")
    def trigger_trace(self, buffer_name):
        pass

    @commands.add(":TRACe:DELete")
    def delete_trace(self, buffer_name):
        pass

    defaults['buffers'] = {}

    BufferElement = instrument.scpi_enum('BufferElement', ('DATE', 'FORMatted', 'FRACtional',
                                                          'READing', 'RELative', 'SEConds',
                                                          'SOURce', 'SOURFORMatted', 'SOURSTATus',
                                                          'SOURUNIT', 'STATus', 'TIME', 'TSTamp',
                                                          'UNIT'), ignore_case=False)

    @commands.add(":FETCh?")
    def fetch(self, *args):
    
        mapper = {
            self.BufferElement.DATE: lambda d:f'{d[0]:%D}',
            self.BufferElement.FORMATTED: lambda d:f'{d[2]:.4f}',
            self.BufferElement.FRACTIONAL: lambda d:0,
            self.BufferElement.READING: lambda d:f'{d[2]:.5f}',
            self.BufferElement.RELATIVE: lambda d:f'{(datetime.datetime.now() - d[0]).seconds}',
            self.BufferElement.SECONDS: lambda d:f'{d[0].timestamp():d}',
            self.BufferElement.SOURCE: lambda d:f'{d[1]:.5f}',
            self.BufferElement.SOURFORMATTED: lambda d:f'{d[1]:.4f}',
            self.BufferElement.SOURSTATUS: '0',
            self.BufferElement.SOURUNIT: 'A',
            self.BufferElement.STATUS: '0',
            self.BufferElement.TIME: lambda d:f'{d[0]:%H:%M:%S}',
            self.BufferElement.TSTAMP: lambda d:f'{d[0].timestamp():d}',
            self.BufferElement.UNIT: lambda d:'V',
            }
    
        if args:
            buffer_name, *elements = args
            if buffer_name.getName() != 'string':
                raise ProtocolError(f"Invalid argument format {buffer_name}")
            buffer_name = buffer_name.string
        else:
            buffer_name = 'DEFBUFFER1'
            elements = []
            
        if buffer_name not in self.buffers:
            raise ProtocolError(f"Unknown buffer {buffer_name}, available {list(self.buffers)}")
            
        if not self.buffers[buffer_name]:
            raise ProtocolError(f"Empty buffer {buffer_name}")
        
        if not elements:
            return mapper[self.BufferElement.READING](self.buffers[buffer_name][-1])
            
        mapped_elements = map(lambda e:mapper[insrument.get_symbol_value(self.BufferElement, e)](self.buffers[buffer_name][-1]),
                              elements)
        
        return ','.join(mapped_elements)

    @commands.add(":MEASure?")
    def measure(self, *args):
        if args:
            buffer_name = args[0]
            if buffer_name.getName() != 'string':
                raise ProtocolError(f"Invalid argument format {buffer_name}")
            buffer_name = buffer_name.string
        else:
            buffer_name = 'DEFBUFFER1'
            
        if buffer_name not in self.buffers:
            self.buffers[buffer_name] = []
            
        self.buffers[buffer_name].append((datetime.datetime.now(), self.current, self.voltage))
    
        return self.fetch(*args)

    defaults['output_on'] = False
    commands[":OUTPut[1][:STATe]?"] = lambda s:str(int(s.output_on))
    @commands.add(":OUTPut[1][:STATe]")
    def set_output_on(self, state):
        self.output_on = instrument.get_bool_value(state)
        
    commands[":ABORt"] = not_implemented_write
    commands[":INITiate"] = not_implemented_write
    commands[":STATus:CLEar"] = not_implemented_write
    commands[":SYSTem:CLEar"] = not_implemented_write

    def __init__(self):    
        super().__init__("Keithley 2450, virtual")
        