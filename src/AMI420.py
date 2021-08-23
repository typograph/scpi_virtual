import instrument
import datetime
import enum
import threading
import time
import queue

def get_float_value(*args, **kwargs):
    try:
        return instrument.get_float_value(*args, **kwargs)
    except instrument.OutOfRangeError:
        raise instrument.ProtocolError('-105,"Out of range"')
    except instrument.InvalidArgumentError:
        raise instrument.ProtocolError('-102,"Invalid argument"')

class AMI420_RampThread(threading.Thread):
    class State(enum.IntEnum):
        RAMPING = 1
        HOLDING = 2
        PAUSED = 3
        MANUAL_UP_RAMPING = 4
        MANUAL_DOWN_RAMPING = 5
        ZEROING = 6
        QUENCHED = 7
        HEATING = 8
        AT_ZERO = 9

    def __init__(self, magnet):
        super().__init__()
        self.magnet = magnet
        self.ramp_button = threading.Event()
        self.pause_button = threading.Event()
#        self.incr_button = threading.Event()
#        self.decr_button = threading.Event()
        self.zero_button = threading.Event()
        self.quench_event = threading.Event()
        self.shutdown = threading.Event()
        self.state_change = threading.Event()
        self.state = self.State.AT_ZERO
        self.msgs = queue.Queue()
        
        self.tick = 0.05

    def run(self):
        while not self.shutdown.is_set():
            if self.ramp_button.is_set():
                self.msgs.put("RAMP button")
                self.ramp_button.clear()
                self.state = self.State.RAMPING
                self.ramp(self.magnet.field_target)
            elif self.pause_button.is_set():
                self.msgs.put("PAUSE button")
                self.pause_button.clear()
                self.state = self.State.HOLDING
            elif self.zero_button.is_set():
                self.msgs.put("ZERO button")
                self.zero_button.clear()
                self.state = self.State.ZEROING
                self.ramp(0)
            elif self.quench_event.is_set():
                self.msgs.put("QUENCH!")
                self.quench_event.clear()
                self.state_change.clear()
                self.state = self.State.QUENCHED
                self.magnet.field = 0
                self.magnet.voltage = 0
            else:
                time.sleep(self.tick)
                
    def ramp(self, target):
        self.state_change.clear()
        self.msgs.put(f"Starting a ramp to {target}")
        while not self.state_change.is_set():
            direction = -1 if self.magnet.field > target else 1
            dB = min(self.magnet.field_rate * self.tick,
                     abs(self.magnet.field - target))
            self.magnet.field += dB * direction
            self.magnet.voltage = dB * direction / self.tick * self.magnet.inductance / self.magnet.coil_constant
            self.msgs.put(f'Field: {self.magnet.field}, voltage: {self.magnet.voltage}')
            if self.magnet.field == target:
                self.state = self.State.AT_ZERO if target == 0 else self.State.HOLDING
                return
            time.sleep(self.tick)
        self.state_change.clear()

class AMI420(instrument.VirtualInstrument):
    """A virtual Americal Magnetics, Inc. Model 420 power supply programmer.
    
    Following changes have been made due to the nature of this library.
    * Error buffer never overflows
    * Boolean parameters accept `ON` and `OFF`
    * All parameters accept `DEFault`
    * It's not possible to turn the device off
    * One can set values explicitely specifying units (G/MIN is not a problem)
    """

    def add_notimplemented(self, command, readonly=False, writeonly=False):
        def handler(query, *args):
            if query:
                if writeonly:
                    self.log_error(f'{command} has no query form')
                else:
                    self.log_error(f'{command}? not implemented')
                    return '0'
            else:
                if readonly:
                    self.log_error(f'{command} has no write form')
                else:
                    self.log_error(f'{command} not implemented')
        self.add_command(command, handler, ignore_case=False)

    def add_constant(self, command, value):
        def handler(query, *args):
            if query:
                return value
            else:
                self.log_error(f'{command} has no write form')
        self.add_command(command, handler, ignore_case=False)
        
    def add_readonly(self, command, getter):
        def handler(query, *args):
            if query:
                return getter(*args)
            else:
                self.log_error(f'{command} has no write form')
        self.add_command(command, handler, ignore_case=False)

    def add_writeonly(self, command, setter):
        def handler(query, *args):
            if query:
                self.log_error(f'{command} has no query form')            
            else:
                return setter(*args)
        self.add_command(command, handler, ignore_case=False)

    def add_dummywriteonly(self, command):
        def handler(query, *args):
            if query:
                self.log_error(f'{command} has no query form')            
        self.add_command(command, handler, ignore_case=False)

    def add_dblproperty(self, name, command, default, min_max, units=None, fstr='{:.4f}'):
        """This adds a property writable at `:CONFIGURE:command`
        and readable at `command`, as per AMI430 spec."""
        self.__dict__[name] = default
        
        def read_handler(query):
            if not query:
                raise instrument.ProtocolError('-101,"Unrecognized command"')
            if isinstance(units, dict):
                factor = units[None]()
            else:
                factor = 1
            return fstr.format(self.__dict__[name]/factor)
            
        self.add_command(command, read_handler, ignore_case=False)

        def write_handler(query, parse_value):
            if query:
                raise instrument.ProtocolError('-201,"Unrecognized query"')
            self.__dict__[name] = get_float_value(parse_value, min_max, units=units)
                        
        self.add_command(':CONFigure' + command, write_handler, ignore_case=False)

    def add_dblboolproperty(self, name, command, default=False):
        """This adds a boolean property writable at `:CONFIGURE:command`
        and readable at `command`, as per AMI430 spec."""
        self.__dict__[name] = default
        
        def read_handler(query):
            if not query:
                raise instrument.ProtocolError('-101, "Unrecognized command"')
            return str(int(self.__dict__[name]))
            
        self.add_command(command, read_handler, ignore_case=False)

        def write_handler(query, parse_value):
            if query:
                raise instrument.ProtocolError('-201, "Unrecognized query"')
            if parse_value.getName() == "symbol":
                if parse_value.symbol == 'ON':
                    self.__dict__[name] = True
                elif parse_value.symbol == 'OFF':
                    self.__dict__[name] = False
                elif parse_value.symbol == 'DEF' or parse_value.symbol == 'DEFAULT':
                    self.__dict__[name] = default
                else:
                    raise instrument.ProtocolError('-103,"Non-boolean argument"')
            elif parse_value.getName() == "number":
                if parse_value.number.value > 1 or parse_value.number.value < 0:
                    raise instrument.ProtocolError('-103,"Non-boolean argument"')
                self.__dict__[name] = self.value = (parse_value.number.value != 0)
            else:
                raise instrument.ProtocolError('-103,"Non-boolean argument"')
                        
        self.add_command(':CONFigure' + command, write_handler, ignore_case=False)

    def runtime(self):
        delta = datetime.datetime.now() - self.poweron_time
        delta = delta.seconds
        return f'{delta//3600:02d}:{(delta//60)%60:02d}:{delta%60:02d}'

    def reset(self):
        super().reset()
        self.reset_time()
        
    def reset_time(self):
        self.poweron_time = datetime.datetime.now()

    def __init__(self, coil_constant, inductance):

        self.coil_constant = coil_constant
        self.inductance = inductance

        super().__init__('AMERICAN MAGNETICS INC.,MODEL 420,virtual')
        
# System-Related Commands
        self.add_constant('*TST', value='1')

        self.add_dummywriteonly(':SYSTem:LOCal')
        self.add_dummywriteonly(':SYSTem:REMote')

        self.reset_time()
        self.add_readonly(':SYSTem:TIME', getter=self.runtime)
        self.add_writeonly(':SYSTem:TIME:RESet', setter=self.reset_time)

# Already implemented in baseclass
#        self.add_notimplemented(':SYSTem:ERRor', readonly=True)
#        self.add_notimplemented('*STB', readonly=True)
#        self.add_notimplemented('*SRE') # <enable_value>
#        self.add_notimplemented('*CLS', writeonly=True)
#        self.add_notimplemented('*ESR', readonly=True)
#        self.add_notimplemented('*ESE') # <enable_value>
#        self.add_notimplemented('*PSC', readonly=True) # {0|1}
#        self.add_notimplemented('*OPC')

        # These can only be set via front panel...
        self.add_constant(':SUPPly:VOLTage:MINimum', '-10')
        self.add_constant(':SUPPly:VOLTage:MAXimum', '10')
        self.add_constant(':SUPPly:CURRent:MINimum', '-100')
        self.add_constant(':SUPPly:CURRent:MAXimum', '100')
        
        # Custom power supply
        self.add_constant(':SUPPly:TYPE', '9')
        # -10 -- 10
        self.add_constant(':SUPPly:MODE', '3')

        self.add_dblproperty('stability', ':STABility', default=0.0, min_max=(0.0,100.0))

#   No, the users cannot change the coil
        self.add_notimplemented(':CONFigure:COILconst', writeonly=True) # <value (kG/A, T/A)>
        self.add_readonly(':COILconst', lambda:f'{coil_constant/self.field_unit_multiplier():.2f}')

# This device has no absorber
        self.add_notimplemented(':CONFigure:ABsorber', writeonly=True) # {0,1}
        self.add_readonly(':ABsorber', '0')

# This device has no persistent switch
        self.add_notimplemented(':CONFigure:PSwitch', writeonly=True) # {0|1}
        self.add_command(':PSwitch', self.manage_pswitch, ignore_case=False)
        self.add_constant(':VOLTage:PSwitch', '0')
        self.add_notimplemented(':CONFigure:PSwitch:CURRent', writeonly=True) # <current (A)>
        self.add_constant(':PSwitch:CURRent', '0')
        self.add_notimplemented(':CONFigure:PSwitch:TIME', writeonly=True) # <time (sec)>
        self.add_constant(':PSwitch:TIME', '0')

# Protection Setup Configuration Commands and Queries
        self.add_dblproperty('current_limit', ':CURRent:LIMit', default=100.0, min_max=(0, 100), units='A')

        self.add_dblboolproperty('quench_detect', ':QUench:DETect', default=True)
        self.add_command(':QUench', self.quench_command, ignore_case=False)

        self.RAMP_RATE_SECONDS = False
        self.RAMP_RATE_MINUTES = True
        self.add_dblboolproperty('ramp_rate_units', ':RAMP:RATE:UNITS')

        self.FIELD_KILOGAUSS = False
        self.FIELD_TESLA = True
        self.add_dblboolproperty('field_units', ':FIELD:UNITS')

# Ramp Target/Rate Configuration Commands and Queries
        self.add_dblproperty('voltage_limit', ':VOLTage:LIMit',
                             default=10.0, min_max=(0,10)) # <voltage (V)>
                             
        self.add_dblproperty('field_target',
                             ':FIELD:PROGram',
                             default=0,
                             min_max=(-100*self.coil_constant, 100*self.coil_constant),
                             units={'T':1,
                                    'G':1e-4,
                                     None:self.field_unit_multiplier}) # <field (kG, T)>

        self.add_writeonly(':CONFigure:CURRent:PROGram', setter=self.set_target_current) # <current (A)>
        self.add_readonly(':CURRent:PROGram', getter=lambda: f'{self.field_target/self.coil_constant:.4f}')

        self.field_rate = 0

        self.add_writeonly(':CONFigure:RAMP:RATE:FIELd', setter=self.set_field_rate) # <rate (kG/s, kG/min, T/s, T/min)>
        self.add_readonly(':RAMP:RATE:FIELd',
                          getter=self.get_field_rate) # <segment ID>
        self.add_writeonly(':CONFigure:RAMP:RATE:CURRent',
                           setter=self.set_current_rate) # <rate (A/s, A/min)>
        self.add_readonly(':RAMP:RATE:CURRent',
                          getter=lambda:'{:.4f}'.format(self.field_rate / self.ramp_unit_multiplier()
                                                                        / self.field_unit_multiplier()
                                                                        / self.coil_constant))

        self.add_writeonly(':CONFigure:RAMP:FIELd', setter=self.set_field_ramp) # <field (kG, T)>, <rate (kG/s, kG/min, T/s, T/min)>
        self.add_readonly(':RAMP:FIELd', getter=self.get_field_ramp) # <segment ID>
        self.add_writeonly(':CONFigure:RAMP:CURRent', setter=self.set_current_ramp) # <current (A)><rate (A/s, A/min)>
        self.add_readonly(':RAMP:CURRent', getter=self.get_current_ramp)

        
# Measurement Commands and Queries
        self.voltage = 0
        self.field = 0

        self.add_readonly(':VOLTage:MAGnet', getter=lambda:f'{self.voltage:.4f}')
# In our ideal universe, the supply voltage drops only in the magnet
        self.add_command(':VOLTage:SUPPly', self.commands['VOLTAGE']['MAGNET'])
        self.add_readonly(':CURRent:MAGnet', getter=lambda:f'{self.field/self.coil_constant:.4f}')
        self.add_command(':CURRent:SUPPly', self.commands['CURRENT']['MAGNET'])
        self.add_readonly(':FIELD:MAGnet', getter=lambda:f'{self.field/self.field_unit_multiplier():.4f}')

# Ramping State Commands and Queries

        self.ramp_thread = AMI420_RampThread(self)
        self.ramp_thread.start()

        self.add_writeonly(':RAMP', lambda:(self.ramp_thread.ramp_button.set() or self.ramp_thread.state_change.set()))
        self.add_writeonly(':PAUSE', lambda:(self.ramp_thread.pause_button.set() or self.ramp_thread.state_change.set()))
#        self.add_writeonly(':UP', lambda:(self.ramp_thread.incr_button.set() or self.ramp_thread.state_change.set()))
#        self.add_writeonly(':DOWN', lambda:(self.ramp_thread.decr_button.set() or self.ramp_thread.state_change.set()))
        self.add_notimplemented(':UP', writeonly=True)
        self.add_notimplemented(':DOWN', writeonly=True)
        self.add_writeonly(':ZERO', lambda:self.ramp_thread.zero_button.set() or self.ramp_thread.state_change.set())
        self.add_readonly(':STATE', lambda:str(int(self.ramp_thread.state)))

# Switch Heater Commands and Queries


        self.add_notimplemented('*ETE') # <enable_value>
        self.add_notimplemented('*TRG', writeonly=True)

    def shutdown(self):
        self.ramp_thread.shutdown.set()
        self.ramp_thread.state_change.set()
        self.ramp_thread.join()

    def __del__(self):
        self.shutdown()
    
    def field_unit_multiplier(self):
        if self.field_units == self.FIELD_TESLA:
            return 1
        elif self.field_units == self.FIELD_KILOGAUSS:
            return 0.1
        else:
            raise ValueError(f'Unknown field units {self.field_units}')

    def ramp_unit_multiplier(self):
        if self.ramp_rate_units == self.RAMP_RATE_SECONDS:
            return 1
        elif self.ramp_rate_units == self.RAMP_RATE_MINUTES:
            return 1/60
        else:
            raise ValueError(f'Unknown ramp rate units {self.ramp_rate_units}')
    
    def get_field_rate(self):
        return f'{self.field_rate/self.ramp_unit_multiplier()/self.field_unit_multiplier():.4f}'

    def get_field_ramp(self):
        return f'{self.field_target/self.field_unit_multiplier():.4f},' + self.get_field_rate()

    def get_current_rate(self):
        return '{:.4f}'.format(self.field_rate / self.ramp_unit_multiplier()
                                               / self.field_unit_multiplier()
                                               / self.coil_constant)
    def get_current_ramp(self):
        return '{:.4f},'.format(self.field_target / self.field_unit_multiplier()
                                                  / self.coil_constant) + self.get_current_rate()
                                                  
    def set_field_ramp(self, field, field_rate):
        self.field_target = get_float_value(field,
                                            default=0,
                                            min_max=(-100*self.coil_constant, 100*self.coil_constant),
                                            units={'T':1,
                                                   'G':1e-4,
                                                   None:self.field_unit_multiplier})
        self.set_field_rate(field_rate)
        
    def set_current_ramp(self, current, current_rate):
        self.field_target = get_float_value(current,
                                            default=0,
                                            min_max=(-100, 100),
                                            units='A')*self.coil_constant
                                     
        self.set_current_rate(current_rate)
    
                                                  
    def set_target_current(self, value):
        self.field_target = get_float_value(value, min_max=(-100,100), units='A')*self.coil_constant
    
    def set_current_rate(self, rate):
        self.field_rate = get_float_value(rate, min_max=(0,1000),
                                               units={'A/s':1,
                                                      'A/min':1/60,
                                                      None:self.ramp_unit_multiplier})*self.coil_constant
        
    def set_field_rate(self, rate):
        units = {'G/s':1e-4,
                 'G/min':1e-4/60,
                 'T/s':1,
                 'T/min':1/60,
                 None:lambda:self.ramp_unit_multiplier()*self.field_unit_multiplier()}
                 
        self.field_rate = get_float_value(rate, (0, 1000), units=units)

    def manage_pswitch(self, query, *args):
        if query and not args:
            return '0'
        elif not query and len(args) == 1:
            self.log_error(f'No persistent switch installed')
        else:
            raise instrument.ProtocolError('-102,"Invalid argument"')
            
    def quench_command(self, query, *args):
        if query and not args:
            return '1' if self.ramp_thread.state == AMI420_RampThread.State.QUENCHED else '0'
        elif not query and len(args) == 1:
            if get_bool_value(args[0]):
                if self.ramp_thread.state != AMI420_RampThread.State.QUENCHED:
                    self.ramp_thread.quench_event.set()
                    self.ramp_thread.state_change.set()
            elif self.ramp_thread.state == AMI420_RampThread.State.QUENCHED:
                # There's no state change event since the thread is in the main loop here.
                self.ramp_thread.pause_button.set()
        else:
            raise instrument.ProtocolError('-102,"Invalid argument"')