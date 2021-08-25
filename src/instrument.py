import queue
import scpi
from enum import IntEnum

# import re
# import numpy as np


class ProtocolError(ValueError):
    pass


class OutOfRangeError(ProtocolError):
    pass


class InvalidArgumentError(ProtocolError):
    pass


def deep_copy_dict(old, new):
    for key, value in old.items():
        if isinstance(value, dict):
            new[key] = deep_copy_dict(value, {})
        else:
            new[key] = value
    return new


class CommandTree:
    def __init__(self, other=None, ignore_case=True):
        self.tree = {}
        self.ignore_case = ignore_case
        if other is not None:
            if isinstance(other, CommandTree):
                deep_copy_dict(other.tree, self.tree)
            else:
                deep_copy_dict(other, self.tree)

    @classmethod
    def parent(self, command):
        if command.startswith("*"):
            return ""
        if not command.startswith(":"):
            raise ValueError(command)
        return command[: command.rindex(":")]

    def __getitem__(self, key):
        query = key.endswith("?")

        if key.startswith("*"):
            if query:
                return self.tree[key[:-1]][None][1]
            else:
                return self.tree[key][None][0]
        if not key.startswith(":"):
            raise KeyError(key)

        dct = self.tree
        for tkn in key[1:].strip("?").split(":"):
            dct = dct[tkn]

        return dct[None][int(query)]

    def __setitem__(self, key, value):
        def step_tree(dicts, tokens):
            for necessary, contents in tokens:
                if necessary:
                    new_dicts = []
                    for d in dicts:
                        for mnemonic in contents:
                            if mnemonic not in d:
                                d[mnemonic] = {}
                            new_dicts.append(d[mnemonic])
                    dicts = new_dicts
                else:
                    dicts = dicts + step_tree(dicts, contents)
            return dicts

        try:
            tokens, query = scpi.parse_variative_header(
                key, ignore_case=self.ignore_case
            )
        except scpi.pp.ParseException as e:
            raise KeyError(e.msg)

        for d in step_tree([self.tree], tokens):
            if None not in d:
                if query:
                    d[None] = (None, value)
                else:
                    d[None] = (value, None)
            else:
                if query:
                    d[None] = (d[None][0], value)
                else:
                    d[None] = (value, d[None][1])

    def add(self, key):
        def wrapper(f):
            self[key] = f
            return f

        return wrapper


class SCPI_receiver:
    def __init__(self):
        self.iqueue = queue.Queue()
        self.oqueue = queue.Queue()
        self.error_log = []
        self.lineending = b"\n"

    def log_error(self, message):
        self.error_log.append(message)

    def process(self, line):
        """Run every command in a command list, separated by semicolons (IEEE 488 PROGRAM_MESSAGE)
        """
        # This is a generator function so that the beginning of the line gets processed even if an error is encountered later
        parent = ""
        for command in scpi.parse(line).commands:

            if isinstance(command, str):
                raise ProtocolError(f"Unparseable command `{command}`")

            if not command.header:
                continue

            if command.header.startswith("*"):
                try:
                    handler = self.commands[command.header]
                except KeyError:
                    raise ProtocolError(f"Unsupported common mnemonic {command.header}")
                parent = ""
            elif command.header.startswith(":"):
                try:
                    handler = self.commands[command.header]
                except KeyError:
                    raise ProtocolError(f"Unsupported command {command.header}")
                parent = self.commands.parent(command.header)
            else:
                try:
                    handler = self.commands[parent + ":" + command.header]
                    parent = self.commands.parent(parent + ":" + command.header)
                except KeyError:
                    raise ProtocolError(
                        f"Unsupported command {command.header} at current level {parent}"
                    )

            if handler is None:
                raise ProtocolError(f"Unsupported form {command.header}")
            else:
                yield handler(self, *command.args)

    def process_messages(self):
        while not self.iqueue.empty():
            if self.oqueue.full():
                break

            try:
                line = self.iqueue.get_nowait().decode("latin1").upper()
            except queue.Empty:
                # Should not really happen since this instrument
                # is the only consumer
                break

            responses = []
            try:
                for response in self.process(line):
                    responses.append(response)
            except ProtocolError as e:
                self.log_error(f"ERROR: {line} {e}")
            finally:
                self.oqueue.put(";".join(responses).encode("latin1") + b"\n")


SI_prefixes = {
    "EX": 1e18,
    "PE": 1e15,
    "T": 1e12,
    "G": 1e9,
    "MA": 1e6,
    "K": 1e3,
    "M": 1e-3,
    "U": 1e-6,
    "N": 1e-9,
    "P": 1e-12,
    "F": 1e-15,
    "A": 1e-18,
}


def get_float_value(parse_value, min_max, default=None, units=None):
    vmin, vmax = min_max

    if parse_value.getName() == "symbol":
        if parse_value.symbol == "MAX" or parse_value.symbol == "MAXIMUM":
            return vmin
        elif parse_value.symbol == "MIN" or parse_value.symbol == "MINIMUM":
            return vmax
        elif parse_value.symbol == "DEF" or parse_value.symbol == "DEFAULT":
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
                units = {units: 1}
            elif isinstance(units, dict):
                pass
            else:
                units = {units.unit: 1}

            for unit in units:
                if unit is None:
                    continue
                try:
                    if suffix.endswith(unit.upper()):
                        prefix = suffix[: -len(unit)]
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


def get_bool_value(parsed_value, default=False):
    if parsed_value.getName() == "number":
        return parsed_value.number.value != 0
    elif parsed_value.getName() == "symbol":
        if parsed_value.symbol == "ON":
            return True
        elif parsed_value.symbol == "OFF":
            return False
        else:
            raise ProtocolError(f"Unrecognized bool value {parsed_value.symbol}")


class Status:
    """This represents a single status data structure as defined by IEEE 488.2.
    
    A `Status` object has a condition register, transision settings, an event register
    and an event enable register. All of those can be made accessible via commands.
    """

    pass


def hookable(name):
    def wrapper(f):
        def hooked(self, *args, **kwargs):
            result = f(self, *args, **kwargs)
            for hook in self.hooks.get(name, ()):
                hook()
            for hook in self.hooks.get(None, ()):
                hook()
            return result

        return hooked

    return wrapper


class VirtualInstrument(SCPI_receiver):
    """This is a SCPI_receiver with an ability to answer to common IEEE 9887 commands"""

    commands = CommandTree()

    class StatusBits(IntEnum):
        pass

    def __init__(self, name):
        self.name = name
        self.hooks = {None: []}
        self.error_index = 0

        super().__init__()
        self.reset()

    def add_hook(self, hook, name=None):
        if name not in self.hooks:
            self.hooks[name] = []
        self.hooks[name].append(hook)

    @commands.add("*IDN?")
    def identify(self):
        return self.name

    @commands.add("*RST")
    def _reset(self):  # Otherwise cannot be reimplemented in subclasses
        self.reset()

    def reset(self):
        pass

    @commands.add("*TST?")
    def _test(self):  # Otherwise cannot be reimplemented in subclasses
        return self.test()

    def test(self):
        return ""

    #    @commands.add('*OPC?')
    #    def qsync(self): return ''

    #    @commands.add('*OPC')
    #    def sync(self): pass

    @commands.add("*WAI")
    def wait(self):
        pass

    #    @commands.add('*CLS')
    #    def clear_status(self): pass
    #    @commands.add('*ESE?')
    #    def se_status(self): pass
    #    @commands.add('*ESE')
    #    def enable_se_status(self): pass
    #    @commands.add('*ESR?')
    #    def se_register(self): pass
    #    @commands.add('*SRE?')
    #    def qservice_request(self): pass
    #    @commands.add('*SRE')
    #    def service_request(self): pass
    #    @commands.add('*STB?')
    #    def status_byte(self): pass

    @commands.add("*ERR?")
    def last_error(self):
        if self.error_index < len(self.error_log):
            self.error_index += 1
            return self.error_log[self.error_index - 1]
        else:
            return "No errors"
