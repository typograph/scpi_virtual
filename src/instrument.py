import queue
import re

class ProtocolError(ValueError):
    pass

def scpi_parse(command, parent):
    # The parsing rules are more IEEE 488.2 rather than SCPI with
    # the obvious exception of expanding short-form mnemonics to long form.
    #
    # This does not support channel lists. Ideally one would define a CFG.
    #
    parser = re.compile(r'''^ # Whole string
                            (?P<cmd>
                              (\*\w+)|
                              (:?[A-Za-z0-9]+) # First header
                              (:[A-Za-z0-9]+)*) # Any following headers
                            (?P<query>\?)?   # Optional query marker
                            (\s+             # Whitespace in front of the argument list
                              (?P<args>
                                 ([^,]+)       # First argument
                                 (,\s*([^,]+))* # Further arguments
                              )
                             )?$                # Argument list is optional''',
                        re.VERBOSE)
    m = parser.match(command)
    if m is None:
        raise ValueError(f"Unparsable `{command.decode('ascii')}`")
    cmd = m.group('cmd').strip().lower()
    if not cmd.startswith(':'):
        cmd = parent + cmd
    parent = ':'.join(cmd.split(':')[:-1])
        
    query = m.group('query') is not None
    if m.group('args') is not None:
        args = list(map(str.strip, m.group('args').split(',')))
    else:
        args = ()
    
    return parent, cmd, query, args


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

    def add_command(self, cmd, entrypoint):
        """Add a SCPI command `cmd` to the list of recognized commands.
        
        The command will be parsed and added in all versions. Short forms
        will be constructed automatically. `cmd` should not contain arguments."""
        
        locations = [self.commands]
        optional = False
        subcmds = cmd.lower().split(':')
        if subcmds[0] == '[':
            optional = True
        elif subcmds[0].startswith('*'):
            if len(subcmds) > 1:
                raise ValueError(f"Standard IEEE commands cannot contain colons")
            self.commands[subcmds[0]] = {None: entrypoint}
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
            for dct in locations:
                if tkn not in dct:
                    dct[tkn] = {}
                    if len(tkn) > 4: # adding short mnemonic
                        if tkn[3] in 'aeiouy':
                            short_tkn = tkn[:3]
                        else:
                            short_tkn = tkn[:4]
                        if short_tkn in dct:
                            raise ValueError(f'Duplicate short mnemonic {short_tkn.upper()} generated from {tkn}')
                        dct[short_tkn] = dct[tkn]
                next_locations.append(dct[tkn])
                if optional:
                    next_locations.append(dct)
                
            optional = next_optional
            locations = next_locations
            
        # All leafs found, filling in endpoints
        for dct in locations:
            if None in dct:
                raise ValueError(f'Command {cmd} already registered')
            else:
                dct[None] = entrypoint
                
    def log_error(self, message):
        self.error_log.append(message)

    def find(self, cmd):
        """Finds code responsible for the command.
        Assumes `cmd` is lowercase"""
        dct = self.commands
        if cmd.startswith('*'):
            if cmd not in dct:
                self.log_error(f"{cmd} not found")
                return None
            return dct[cmd][None]
        elif cmd.startswith(':'):
            for tkn in cmd.split(':')[1:]:
                if tkn not in dct:
                    self.log_error(f"{tkn} not found [in {cmd}]")
                    return None
                dct = dct[tkn]
        else:
            raise ValueError(f'Unsupported command form {cmd}')
        return dct[None]

    def process(self, line):# -> List[String]:
        parent = ""
        response = []
        for command in map(str.strip, line.split(';')):
            parent, cmd, query, args = scpi_parse(command, parent)
            entrypoint = self.find(cmd)
            if entrypoint is None:
                break
            try:
                if query:
                    response.append(entrypoint.get(*args))
                else:
                    response.append(entrypoint.set(*args))
            except ProtocolError as e:
                self.log_error(f'ERROR: {command} {e.msg}')
        return [r for r in response if r is not None]
                
    def process_messages(self):
        while not self.iqueue.empty():
            try:
                line = self.iqueue.get_nowait().decode('ascii')
            except queue.Empty:
                # Should not really happen since this instrument
                # is the only consumer
                break

            for resp in self.process(line):
                try:
                    if resp is not None:
                        self.oqueue.put(resp.encode("ascii") + b'\n')
                except queue.Full:
                    # The socket is not sending. Bad.
                    print(f"Queue full on {self.name}")
                    self.oqueue.join() # let's block

class ConstProperty:
    def __init__(self, value):
        self.value = str(value)
        
    def get(self, *args):
        if args:
            raise ValueError(f'arguments {args} not supported')
        else:
            return self.value
     
    def set(self, *args):
        raise ValueError('not settable')

class ExtProperty:
    def __init__(self, getter = None, setter = None):
        super().__init__()
        self.getter = getter
        self.setter = setter
        
    def get(self, *args):
        if self.getter is None:
            raise ValueError('query form not supported')
        else:
            return self.getter(*args)
     
    def set(self, *args):
        if self.setter is None:
            raise ValueError('not settable')
        else:
            return self.setter(*args)

class Property:
    def __init__(self, getter=None, setter=None):
        self.getter = getter
        self.setter = setter
        self.set_hooks = []
        
    def add_set_hook(self, hook):
        """After the value is set, any hooks added through this function
        will be run in the order they were added"""
        self.set_hooks.append(hook)
        
    def set(self, *args):
        """This will be called when `<command> <args>` arrives to the instrument.
        Any output will be reported to the user."""
        if self.setter is None:
            raise ValueError('not settable')
            
        result = self.setter(*args)
        for hook in self.set_hooks:
            hook(*args)
        return result

    def get(self, *args):
        """This will be called when `<command>? <args>` arrives to the instrument.
        All output will be reported back to the user."""
        if self.getter is None:
            raise ValueError('query form not supported')
        else:
            return self.getter(*args)

class FloatProperty(Property):
    """Class for a typical settable/queriable value
    Supports MIN/MAX values with `min_max` and UP/DOWN with `steppable`"""
    def __init__(self, unit, readonly=False, setonly=False, min_max=False, steppable=False, default_value=0):
        if readonly:
            super().__init__(self.getter)
        elif setonly:
            super().__init__(setter=self.setter)
        else:
            super().__init__(self.getter, self.setter)

        self.unit = unit
        self.min_max = min_max
        self.steppable = steppable
        self.value = default_value
        if steppable:
            self.step = 0
        self.default_value = default_value
        
    def setter(self, *args):
        if len(args) == 0:
            raise ValueError(f"{self.command} takes one parameter")
        if len(args) > 1:
            raise ValueError(f"{self.command} takes only one parameter")

        str_value = args[0].lower()
        
        if str_value == 'max' or str_value == 'maximum':
            if self.min_max:
                self.value = self.min_max[1]
            else:
                raise ProtocolError("no known maximum value")
        elif str_value == 'min' or str_value == 'minimum':
            if self.min_max:
                self.value = self.min_max[0]
            else:
                raise ProtocolError("no known minimum value")
        elif str_value == 'up':
            if self.steppable:
                self.value += self.step
            else:
                raise ProtocolError("not steppable")
        elif str_value == 'down':
            if self.steppable:
                self.value -= self.step
            else:
                raise ProtocolError("not steppable")
        else:
            if self.unit is not None and str_value.endswith(self.unit.lower()):
                    value, unit = str_value.split()
                    try:
                        self.value = float(value)
                    except ValueError:
                        raise ProtocolError("Value formal mismatch '{value}'")
            else:
                try:
                    self.value = float(str_value)
                except ValueError:
                    raise ProtocolError("Value formal mismatch '{value}'")
                    
        if self.min_max:
            if self.value < self.min_max[0]:
                self.value = self.min_max[0]
            elif self.value > self.min_max[1]:
                self.value = self.min_max[1]
        
    def getter(self, *args):
        if args:
            raise ValueError(f"{self.command}? takes no parameters")
        return f"{self.value:g}"

class VirtualInstrument(SCPI_receiver):
    """This is a SCPI_receiver with an ability to answer to common IEEE 9887 commands"""
    
    def __init__(self, name):
        super().__init__(name)
        self.add_command("*IDN", ConstProperty(name))
        self.add_command("*RST", ExtProperty(setter=self.reset))
        self.add_command("*TST", ExtProperty(getter=self.test))
        self.add_command("*OPC", ExtProperty(self.qsync, self.sync))
        self.add_command("*WAI", ExtProperty(setter=self.wait))
        self.add_command("*CLS", ExtProperty(setter=self.clear_status))
        self.add_command("*ESE", ExtProperty(getter=self.se_status, setter=self.enable_se_status))
        self.add_command("*ESR", ExtProperty(getter=self.se_register))
        self.add_command("*SRE", ExtProperty(getter=self.qservice_request, setter=self.service_request))
        self.add_command("*STB", ExtProperty(getter=self.status_byte))
        self.add_command("*ERR", ExtProperty(getter=self.last_error))
        self.error_index = 0
    
    def reset(self): pass
    def test(self): pass
    def qsync(self): pass
    def sync(self): pass
    def wait(self): pass
    def test(self): pass
    def clear_status(self): pass
    def se_status(self): pass
    def enable_se_status(self): pass
    def se_register(self): pass
    def qservice_request(self): pass
    def service_request(self): pass
    def status_byte(self): pass
    def last_error(self):
        if self.error_index < len(self.error_log):
            self.error_index += 1
            return self.error_log[self.error_index-1]
        else:
            return "No errors"