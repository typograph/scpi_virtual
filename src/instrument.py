import queue
import re
import scpi
import numpy as np
from enum import IntEnum

class ProtocolError(ValueError):
    pass
    
class OutOfRangeError(ProtocolError):
    pass

class InvalidArgumentError(ProtocolError):
    pass

class SCPI_receiver:

    def __init__(self, name=None):
        if name is None:
            name = 'SCPI_receiver'
        self.name = name
        self.iqueue = queue.Queue()
        self.oqueue = queue.Queue()
        self.commands = {}
        self.error_log = []
        self.lineending = b'\n'

    def add_command(self, cmd, handler, ignore_case=True):
        """Add a SCPI command `cmd` to the list of recognized commands.
        
        The command will be parsed and added in all versions. Short forms
        will be constructed automatically. `cmd` should not contain arguments."""
        
        locations = [self.commands]
        optional = False
        subcmds = cmd.split(':')
        if subcmds[0] == '[':
            optional = True
        elif subcmds[0].startswith('*'):
            if len(subcmds) > 1:
                raise ValueError(f"Standard IEEE commands cannot contain colons")
            self.commands[subcmds[0]] = {None: handler}
            return
        elif subcmds[0] != '':
            raise ValueError(f'Commands should be specified in full form from root (:A[:B]:C)')
        for tkn in subcmds[1:]:
            if len(tkn) == 0:
                raise ValueError(f'Zero-length command in {cmd}')
            next_optional = tkn[-1] == '['
            skip = int(optional) + int(next_optional)
            tkn = tkn[:len(tkn)-skip]

            if len(tkn) == 0:
                raise ValueError(f'Empty subcommand in {cmd}')
                        
            next_locations = []
            
            long_tkn = tkn.upper()
            short_tkn = None
            if ignore_case:
                if len(tkn) > 3 and tkn[3] in 'AEIOUY':
                    short_tkn = long_tkn[:3]
                elif len(tkn) > 4:
                    short_tkn = long_tkn[:4]
            elif long_tkn != tkn:
                m = re.match('[A-Z_0-9]+', tkn)
                if m:
                    short_tkn = m.group(0)
                else:
                    raise ValueError('Cannot use case in {tkn} @ {cmd}')

            for dct in locations:
                if long_tkn not in dct:
                    dct[long_tkn] = {}
                    if short_tkn is not None:
                        if short_tkn in dct:
                            raise ValueError(f'Duplicate short mnemonic {short_tkn} generated from {tkn}')
                        else:
                            dct[short_tkn] = dct[long_tkn]
                next_locations.append(dct[long_tkn])
                if optional:
                    next_locations.append(dct)
                
            optional = next_optional
            locations = next_locations
            
        # All leafs found, filling in endpoints
        for dct in locations:
            if None in dct:
                raise ValueError(f'Command {cmd} already registered')
            else:
                dct[None] = handler
                
    def log_error(self, message):
        self.error_log.append(message)

    def find(self, header, parent):
        """Finds code responsible for the command.
        Assumes `cmd` is lowercase"""
        
        def resolve(tokens):
            dct = self.commands
            # print(tokens)
            for tkn in tokens:
                if tkn not in dct:
                    return None
                dct = dct[tkn]
            if None in dct:
                return dct[None]
            return None
        
        subcmds = header.split(':')
        if not subcmds[0]: # Global command
            handler = resolve(subcmds[1:])
            if handler is None:
                raise ProtocolError(f"Unknown command `{header}`")
            return handler, subcmds[1:-1]
        elif subcmds[0][0] == '*': # Common commands
            if len(subcmds) > 1:
                raise ProtocolError(f'Invalid common command {header}')
            elif subcmds[0] in self.commands:
                # IEEE 488.2 A.1.1 (6)
                return self.commands[subcmds[0]][None], parent
            else:
                raise ProtocolError(f'Unknown command command {header}')
        else:
            handler = resolve(parent + subcmds)
            if handler is None:
                raise ProtocolError(f'Unknown command {header}')
            return handler, parent + subcmds[:-1]

    def process(self, line):
        parent = []
        for command in scpi.parse(line).commands:
            if isinstance(command, str):
                raise ProtocolError(f'Unparseable command `{command}`')

            if not command.header:
                continue

            handler, parent = self.find(command.header, parent)

            yield handler(command.query, *command.args)

    def process_messages(self):
        while not self.iqueue.empty():
            if self.oqueue.full():
                break
                
            try:
                line = self.iqueue.get_nowait().decode('latin1').upper()
            except queue.Empty:
                # Should not really happen since this instrument
                # is the only consumer
                break

            responses = []
            try:
                for response in self.process(line):
                    responses.append(response)
            except ProtocolError as e:
                self.log_error(f'ERROR: {line} {e}')
            finally:
                self.oqueue.put(';'.join(responses).encode("latin1") + b'\n')

def symbol(value):
    """A SCPI handler for a symbol value"""
    def handle(query, *args):
        if not query: 
            raise ProtocolError('not settable')
        if args:
            raise ProtocolError(f'arguments {args} not supported')
        else:
            return value
    return handle

def make_handler(getter=None, setter=None, set_hooks=None):
    """Combines query and command functions to a single function"""
    def handle(query, *args):
        if query:
            if getter is None:
                raise ProtocolError('query form not supported')
            else:
                return getter(*args)
        else:
            if setter is None:
                raise ProtocolError('not settable')
            else:
                response = setter(*args)
                for hook in set_hooks:
                    hook()
                return response
    return handle

SI_prefixes = {'EX':1e18,
               'PE':1e15,
               'T':1e12,
               'G':1e9,
               'MA':1e6,
               'K':1e3,
               'M':1e-3,
               'U':1e-6,
               'N':1e-9,
               'P':1e-12,
               'F':1e-15,
               'A':1e-18}

def get_float_value(parse_value, min_max, default=None, units=None):
    vmin, vmax = min_max

    if parse_value.getName() == "symbol":
        if parse_value.symbol == 'MAX' or parse_value.symbol == 'MAXIMUM':
            return vmin
        elif parse_value.symbol == 'MIN' or parse_value.symbol == 'MINIMUM':
            return vmax
        elif parse_value.symbol == 'DEF' or parse_value.symbol == 'DEFAULT':
            if default is None:
                raise InvalidArgumentError()
            else:
                return default
        else:
            raise InvalidArgumentError()
    elif parse_value.getName() == "number":
        factor = 1
        suffix = parse_value.number.suffix.upper()
        if suffix:
            if units is None:
                raise InvalidArgumentError()
            elif isinstance(units, str):
                units = {units:1}
            elif isinstance(units, dict):
                pass
            else:
                units = {units.unit:1}

            for unit in units:
                if unit is None:
                    continue
                try:
                    if suffix.endswith(unit.upper()):
                        prefix = suffix[:-len(unit)]
                        if prefix:
                            factor = SI_prefixes[prefix] * units[unit]
                        else:
                            factor = units[unit]
                        break
                except KeyError:
                    continue
            else:
                raise InvalidArgumentError()
        elif isinstance(units, dict):
            factor = units[None]()
                    
        value = parse_value.number.value * factor
        if value < vmin or value > vmax:
            raise OutOfRangeError()
        return value
    else:
        raise InvalidArgumentError()

class Property:
    """The equivalent of `make_handler` in class form"""
    def __init__(self):        
        self.set_hooks = []

    def getter(self):
        raise ProtocolError('query form not supported')

    def setter(self):
        raise ProtocolError('not settable')
    
    def __call__(self, query, *args):
        if query:
            # This will be called when `<command>? <args>` arrives to the instrument. All output will be reported back to the user.
            return self.getter(*args)
        else:
            # This will be called when `<command> <args>` arrives to the instrument. Any output will be reported to the user.
            result = self.setter(*args)
            for hook in self.set_hooks:
                hook(*args)
            return result
    
    def add_set_hook(self, hook):
        """After the value is set, any hooks added through this function
        will be run in the order they were added"""
        self.set_hooks.append(hook)
        

class BoolProperty(Property):
    def __init__(self, readonly=False, setonly=False, default_value=False):
        super().__init__()
        if readonly:
            self.setter = super().setter
        elif setonly:
            self.getter = super().getter

        self.value = default_value
        self.default_value = default_value

    def getter(self):
        return '1' if self.value else '0'

    def setter(self, value):
        if value.getName() == 'number':
            self.value = (value.number.value != 0)
        elif value.getName() == 'symbol':
            if value.symbol == 'ON':
                self.value = True
            elif value.symbol == 'OFF':
                self.value = False
            else:
                raise ProtocolError(f"Unrecognized bool value {value.symbol}")

class FloatProperty(Property):
    """Class for a typical settable/queriable value
    Supports MIN/MAX values with `min_max` and UP/DOWN with `steppable`"""

    def __init__(self, unit, readonly=False, setonly=False, min_max=False, steppable=False, default_value=0):
        super().__init__()
        if readonly:
            self.setter = super().setter
        elif setonly:
            self.getter = super().getter

        self.unit = unit.upper()
        self.min_max = min_max
        self.steppable = steppable
        self.value = default_value
        if steppable:
            self.step = 0
        self.default_value = default_value
        
    def setter(self, parse_value):
    
        if parse_value.getName() == "symbol":
            if parse_value.symbol == 'MAX' or parse_value.symbol == 'MAXIMUM':
                if self.min_max:
                    self.value = self.min_max[1]
                else:
                    raise ProtocolError("no known maximum value")
            elif parse_value.symbol == 'MIN' or parse_value.symbol == 'MINIMUM':
                if self.min_max:
                    self.value = self.min_max[0]
                else:
                    raise ProtocolError("no known minimum value")
            elif parse_value.symbol == 'UP':
                if self.steppable:
                    self.value += self.step
                else:
                    raise ProtocolError("not steppable")
            elif parse_value.symbol == 'DOWN':
                if self.steppable:
                    self.value -= self.step
                else:
                    raise ProtocolError("not steppable")
            elif parse_value.symbol == 'DEF' or parse_value.symbol == 'DEFAULT':
                self.value = self.default_value
            elif parse_value.symbol == 'INF' or parse_value.symbol == 'INFINITY':
                self.value = np.inf
            elif parse_value.symbol == 'NINF' or parse_value.symbol == 'NINFINITY':
                self.value = -np.inf
            elif parse_value.symbol == 'NAN':
                self.value = np.nan
            else:
                raise ProtocolError(f"Unrecognized value {parse_value.symbol}")
        elif parse_value.getName() == "number":
            factor = 1
            suffix = parse_value.number.suffix
            if suffix:
                if suffix.endswith(self.unit):
                    prefix = suffix[:-len(self.unit)]
                    if prefix:
                        if suffix == 'MOHM' or suffix == 'MHZ':
                            factor = 1e6
                        else:
                            factor = SI_prefixes[prefix] 
            self.value = parse_value.number.value * factor
        else:
            raise ProtocolError("not a float value {parse_value}")
                    
        if self.min_max:
            if self.value < self.min_max[0]:
                self.value = self.min_max[0]
            elif self.value > self.min_max[1]:
                self.value = self.min_max[1]
        
    def getter(self, *args):
        if args:
            raise ProtocolError(f"query takes no parameters (got `{args[0]}`)")
        return f"{self.value:g}"

class Status:
    """This represents a single status data structure as defined by IEEE 488.2.
    
    A `Status` object has a condition register, transision settings, an event register
    and an event enable register. All of those can be made accessible via commands.
    """
    pass

class VirtualInstrument(SCPI_receiver):
    """This is a SCPI_receiver with an ability to answer to common IEEE 9887 commands"""
    
    class StatusBits(IntEnum):
        pass
    
    def __init__(self, name):
        super().__init__(name)
        self.add_command("*IDN", symbol(name))
#        self.add_command("*RST", make_handler(setter=self.reset))
#        self.add_command("*TST", make_handler(getter=self.test))
#        self.add_command("*OPC", make_handler(self.qsync, self.sync))
#        self.add_command("*WAI", make_handler(setter=self.wait))
#        self.add_command("*CLS", make_handler(setter=self.clear_status))
#        self.add_command("*ESE", make_handler(getter=self.se_status, setter=self.enable_se_status))
#        self.add_command("*ESR", make_handler(getter=self.se_register))
#        self.add_command("*SRE", make_handler(getter=self.qservice_request, setter=self.service_request))
#        self.add_command("*STB", make_handler(getter=self.status_byte))
        self.add_command("*ERR", make_handler(getter=self.last_error))
        self.error_index = 0
    
#    def reset(self): pass
#    def test(self): pass
#    def qsync(self): pass
#    def sync(self): pass
#    def wait(self): pass
#    def test(self): pass
#    def clear_status(self): pass
#    def se_status(self): pass
#    def enable_se_status(self): pass
#    def se_register(self): pass
#    def qservice_request(self): pass
#    def service_request(self): pass
#    def status_byte(self): pass
    def last_error(self):
        if self.error_index < len(self.error_log):
            self.error_index += 1
            return self.error_log[self.error_index-1]
        else:
            return "No errors"