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
            dB = min(
                self.magnet.field_rate * self.tick, abs(self.magnet.field - target)
            )
            self.magnet.field += dB * direction
            self.magnet.voltage = (
                dB
                * direction
                / self.tick
                * self.magnet.inductance
                / self.magnet.coil_constant
            )
            self.msgs.put(f"Field: {self.magnet.field}, voltage: {self.magnet.voltage}")
            if self.magnet.field == target:
                self.state = self.State.AT_ZERO if target == 0 else self.State.HOLDING
                return
            time.sleep(self.tick)
        self.state_change.clear()


def dummy_write(self, *args):
    pass


def not_implemented(self, *args):
    raise ProtocolError(f"not implemented")


class AMI420(instrument.VirtualInstrument):
    """A virtual Americal Magnetics, Inc. Model 420 power supply programmer.
    
    Following changes have been made due to the nature of this library.
    * Error buffer never overflows
    * Boolean parameters accept `ON` and `OFF`
    * All parameters accept `DEFault`
    * It's not possible to turn the device off
    * One can set values explicitely specifying units (G/MIN is not a problem)
    """

    commands = instrument.CommandTree(
        instrument.VirtualInstrument.commands, ignore_case=False
    )

    # System-Related Commands

    commands["*TST?"] = lambda s: "1"
    commands[":SYSTem:LOCal"] = dummy_write
    commands[":SYSTem:REMote"] = dummy_write

    # Already `implemented` in baseclass
    #        self.add_notimplemented(':SYSTem:ERRor', readonly=True)
    #        self.add_notimplemented('*STB', readonly=True)
    #        self.add_notimplemented('*SRE') # <enable_value>
    #        commands['*CLS'] = not_implemented
    #        self.add_notimplemented('*ESR', readonly=True)
    #        self.add_notimplemented('*ESE') # <enable_value>
    #        self.add_notimplemented('*PSC', readonly=True) # {0|1}
    #        self.add_notimplemented('*OPC')

    commands["*ETE"] = not_implemented  # <enable_value>
    commands["*ETE?"] = not_implemented  # <enable_value>
    commands["*TRG"] = not_implemented

    @commands.add(":SYSTem:TIME?")
    def runtime(self):
        delta = datetime.datetime.now() - self.poweron_time
        delta = delta.seconds
        return f"{delta//3600:02d}:{(delta//60)%60:02d}:{delta%60:02d}"

    @commands.add(":SYSTem:TIME:RESet")
    def reset_time(self):
        self.poweron_time = datetime.datetime.now()

    # These can only be set via front panel...
    commands[":SUPPly:VOLTage:MINimum"] = lambda s: "-10"
    commands[":SUPPly:VOLTage:MAXimum"] = lambda s: "10"
    commands[":SUPPly:CURRent:MINimum"] = lambda s: "-100"
    commands[":SUPPly:CURRent:MAXimum"] = lambda s: "100"

    # Custom power supply
    commands[":SUPPly:TYPE"] = lambda s: "9"
    # -10 -- 10
    commands[":SUPPly:MODE"] = lambda s: "3"

    @commands.add(":STABility?")
    def get_stability(self):
        return "{:.4f}".format(self.stability)

    @commands.add(":CONFigure:STABility")
    def set_stability(self, parsed_value):
        self.stability = get_float_value(
            parsed_value, default=0.0, min_max=(0.0, 100.0)
        )

    @commands.add(":CURRent:LIMit?")
    def get_current_limit(self):
        return "{:.4f}".format(self.current_limit)

    @commands.add(":CONFigure:CURRent:LIMit")
    def set_current_limit(self, parsed_value):
        self.current_limit = get_float_value(
            parsed_value, default=100.0, min_max=(0, 100), units="A"
        )

    commands[":CONFigure:COILconst"] = not_implemented

    @commands.add(":COILconst")
    def get_coil_constant(self):
        return "{:.4f}".format(self.coil_constant / self.field_unit_multiplier())

    #   No, the users cannot change the coil
    commands[":CONFigure:COILconst"] = not_implemented  # <value (kG/A, T/A)>

    # This device has no absorber
    commands[":CONFigure:ABsorber"] = not_implemented  # {0,1}
    commands[":ABsorber"] = lambda s: "0"

    # Switch Heater Commands and Queries

    # This device has no persistent switch
    commands[":CONFigure:PSwitch"] = not_implemented  # {0|1}

    commands[":VOLTage:PSwitch"] = lambda s: "0"
    commands[":PSwitch?"] = lambda s: "0"

    @commands.add(":PSwitch")
    def get_pswitch(self, parsed_value):
        self.log_error(f"No persistent switch installed")

    commands[":CONFigure:PSwitch:CURRent"] = not_implemented  # <current (A)>
    commands[":PSwitch:CURRent"] = lambda s: "0"
    commands[":CONFigure:PSwitch:TIME"] = not_implemented  # <time (sec)>
    commands[":PSwitch:TIME"] = lambda s: "0"

    RAMP_RATE_SECONDS = False
    RAMP_RATE_MINUTES = True

    FIELD_KILOGAUSS = False
    FIELD_TESLA = True

    def field_unit_multiplier(self):
        if self.field_units == self.FIELD_TESLA:
            return 1
        elif self.field_units == self.FIELD_KILOGAUSS:
            return 0.1
        else:
            raise ValueError(f"Unknown field units {self.field_units}")

    def ramp_unit_multiplier(self):
        if self.ramp_rate_units == self.RAMP_RATE_SECONDS:
            return 1
        elif self.ramp_rate_units == self.RAMP_RATE_MINUTES:
            return 1 / 60
        else:
            raise ValueError(f"Unknown ramp rate units {self.ramp_rate_units}")

    @commands.add(":RAMP:RATE:UNITS?")
    def get_ramp_rate_units(self):
        return str(int(self.ramp_rate_units))

    @commands.add(":CONFigure:RAMP:RATE:UNITS")
    def set_ramp_rate_units(self, parsed_value):
        self.ramp_rate_units = instrument.get_bool_value(parsed_value)

    @commands.add(":FIELD:UNITS?")
    def get_field_units(self):
        return str(int(self.field_units))

    @commands.add(":CONFigure:FIELD:UNITS")
    def set_field_units(self, parsed_value):
        self.field_units = instrument.get_bool_value(parsed_value)

    # Ramp Target/Rate Configuration Commands and Queries

    @commands.add(":VOLTage:LIMit?")
    def get_voltage_limit(self):
        return "{:.4f}".format(self.voltage_limit)

    @commands.add(":CONFigure:VOLTage:LIMit")
    def set_voltage_limit(self, parsed_value):  # <voltage (V)>
        self.voltage_limit = get_float_value(
            parsed_value, default=10.0, min_max=(0, 10)
        )

    @commands.add(":FIELD:PROGram?")
    def get_field_target(self):
        return "{:.4f}".format(self.field_target / self.field_unit_multiplier())

    @commands.add(":CONFigure:FIELD:PROGram")
    def set_field_target(self, parsed_value):  # <field (kG, T)>
        self.field_target = get_float_value(
            parsed_value,
            default=0,
            min_max=(-100 * self.coil_constant, 100 * self.coil_constant),
            units={"T": 1, "G": 1e-4, None: self.field_unit_multiplier},
        )

    @commands.add(":RAMP:RATE:FIELd?")
    def get_field_rate(self):
        return f"{self.field_rate/self.ramp_unit_multiplier()/self.field_unit_multiplier():.4f}"

    @commands.add(":CONFigure:RAMP:RATE:FIELd")
    def set_field_rate(self, rate):
        units = {
            "G/s": 1e-4,
            "G/min": 1e-4 / 60,
            "T/s": 1,
            "T/min": 1 / 60,
            None: lambda: self.ramp_unit_multiplier() * self.field_unit_multiplier(),
        }

        self.field_rate = get_float_value(rate, (0, 1000), units=units)

    @commands.add(":RAMP:FIELd?")
    def get_field_ramp(self):
        return (
            f"{self.field_target/self.field_unit_multiplier():.4f},"
            + self.get_field_rate()
        )

    @commands.add(
        ":CONFigure:RAMP:FIELd"
    )  # <field (kG, T)>, <rate (kG/s, kG/min, T/s, T/min)>
    def set_field_ramp(self, field, field_rate):
        self.set_field_target(field)
        self.set_field_rate(field_rate)

    @commands.add(":CURRent:PROGram?")
    def get_current_target(self):
        return f"{self.field_target/self.coil_constant:.4f}"

    @commands.add(":CONFigure:CURRent:PROGram")
    def set_current_target(self, value):  # <current (A)>
        self.field_target = (
            get_float_value(value, min_max=(-100, 100), units="A") * self.coil_constant
        )

    @commands.add(":RAMP:RATE:CURRent?")
    def get_current_rate(self):
        return "{:.4f}".format(
            self.field_rate
            / self.ramp_unit_multiplier()
            / self.field_unit_multiplier()
            / self.coil_constant
        )

    @commands.add(":CONFigure:RAMP:RATE:CURRent")  # <rate (A/s, A/min)>
    def set_current_rate(self, rate):
        self.field_rate = (
            get_float_value(
                rate,
                min_max=(0, 1000),
                units={"A/s": 1, "A/min": 1 / 60, None: self.ramp_unit_multiplier},
            )
            * self.coil_constant
        )

    @commands.add(":RAMP:CURRent?")
    def get_current_ramp(self):
        return (
            "{:.4f},".format(
                self.field_target / self.field_unit_multiplier() / self.coil_constant
            )
            + self.get_current_rate()
        )

    @commands.add(":CONFigure:RAMP:CURRent")  # <current (A)><rate (A/s, A/min)>
    def set_current_ramp(self, current, current_rate):
        self.set_current_target(current)
        self.set_current_rate(current_rate)

    # Ramping State Commands and Queries

    @commands.add(":RAMP")
    def start_ramp(self):
        self.ramp_thread.ramp_button.set()
        self.ramp_thread.state_change.set()

    @commands.add(":PAUSE")
    def pause_ramp(self):
        self.ramp_thread.pause_button.set()
        self.ramp_thread.state_change.set()

    commands[":UP"] = not_implemented
    commands[":DOWN"] = not_implemented

    @commands.add(":ZERO")
    def zero_ramp(self):
        self.ramp_thread.zero_button.set()
        self.ramp_thread.state_change.set()

    @commands.add(":STATE?")
    def get_ramp_state(self):
        return str(int(self.ramp_thread.state))

    # Measurement Commands and Queries

    @commands.add(":VOLTage:MAGnet?")
    # In our ideal universe, the supply voltage drops only in the magnet
    @commands.add(":VOLTage:SUPPly?")
    def get_voltage(self):
        return f"{self.voltage:.4f}"

    @commands.add(":CURRent:MAGnet?")
    @commands.add(":CURRent:SUPPly?")
    def get_current(self):
        return f"{self.field/self.coil_constant:.4f}"

    @commands.add(":FIELD:MAGnet?")
    def get_field(self):
        return f"{self.field/self.field_unit_multiplier():.4f}"

    # Protection Setup Configuration Commands and Queries
    @commands.add(":QUench:DETect?")
    def get_quench_detect(self):
        return str(int(self.quench_detect))

    @commands.add(":CONFigure:QUench:DETect")
    def set_quench_detect(self, parsed_value):
        self.quench_detect = instrument.get_bool_value(parsed_value, default=True)

    @commands.add(":QUench?")
    def quenched(self):
        return (
            "1" if self.ramp_thread.state == AMI420_RampThread.State.QUENCHED else "0"
        )

    @commands.add(":QUench")
    def quench(self, parsed_value):
        if instrument.get_bool_value(parsed_value):
            if self.ramp_thread.state != AMI420_RampThread.State.QUENCHED:
                self.ramp_thread.quench_event.set()
                self.ramp_thread.state_change.set()
        elif self.ramp_thread.state == AMI420_RampThread.State.QUENCHED:
            # There's no state change event since the thread is in the main loop here.
            self.ramp_thread.pause_button.set()

    @commands.add("*RST")
    def reset(self):
        self.reset_time()

        self.voltage = 0
        self.field = 0

        self.stability = 0.0
        self.voltage_limit = 10.0
        self.current_limit = 100.0

        self.ramp_rate_units = self.RAMP_RATE_SECONDS
        self.field_units = self.FIELD_KILOGAUSS

        self.field_target = 0.0
        self.field_rate = 0.0
        self.quench_detect = False

        super().reset()

    def __init__(self, coil_constant, inductance):

        self.coil_constant = coil_constant
        self.inductance = inductance

        super().__init__("AMERICAN MAGNETICS INC.,MODEL 420,virtual")

        self.ramp_thread = AMI420_RampThread(self)
        self.ramp_thread.start()

    def shutdown(self):
        self.ramp_thread.shutdown.set()
        self.ramp_thread.state_change.set()
        self.ramp_thread.join()

    def __del__(self):
        self.shutdown()
