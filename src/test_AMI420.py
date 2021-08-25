import AMI420

import unittest
import time


class TestAMI420(unittest.TestCase):
    def setUp(self):
        self.magnet = AMI420.AMI420(1.5, 7)  # Prime factors are good

    def tearDown(self):
        self.magnet.shutdown()

    def assertRun(self, command, *results):
        self.assertEqual(tuple(self.magnet.process(command)), results)

    def test_init(self):
        self.assertRun("*IDN?", "AMERICAN MAGNETICS INC.,MODEL 420,virtual")

    def test_units(self):
        self.assertRun(":RAMP:RATE:UNITS?", "0")  # sec^-1
        self.assertRun(":FIELD:UNITS?", "0")  # kG

        self.assertRun(
            ":FIELD:PROG?;:RAMP:RATE:FIELD?;:RAMP:FIELD?",
            "0.0000",
            "0.0000",
            "0.0000,0.0000",
        )

        self.assertRun(
            "CONF:FIELD:PROG 1;:FIELD:PROG?;:RAMP:FIELD?",
            None,
            "1.0000",
            "1.0000,0.0000",
        )
        self.assertEqual(self.magnet.field_target, 0.1)

        self.assertRun(
            "CONF:RAMP:RATE:FIELD 0.3;:RAMP:RATE:FIELD?;:RAMP:FIELD?",
            None,
            "0.3000",
            "1.0000,0.3000",
        )

        self.assertRun(
            "CONF:FIELD:PROG 2kG;:FIELD:PROG?;:RAMP:FIELD?",
            None,
            "2.0000",
            "2.0000,0.3000",
        )
        self.assertEqual(self.magnet.field_target, 0.2)

        self.assertRun(
            "CONF:FIELD:PROG 2T;:FIELD:PROG?;:RAMP:FIELD?",
            None,
            "20.0000",
            "20.0000,0.3000",
        )
        self.assertEqual(self.magnet.field_target, 2.0)

        self.assertRun("CONF:FIELD:UNITS 1", None)  # T
        self.assertRun(
            ":FIELD:PROG?;:RAMP:RATE:FIELD?;:RAMP:FIELD?",
            "2.0000",
            "0.0300",
            "2.0000,0.0300",
        )
        self.assertRun(
            "CONF:FIELD:PROG 1;:FIELD:PROG?;:RAMP:FIELD?",
            None,
            "1.0000",
            "1.0000,0.0300",
        )
        self.assertRun(
            "CONF:RAMP:RATE:FIELD 0.3;:RAMP:RATE:FIELD?;:RAMP:FIELD?",
            None,
            "0.3000",
            "1.0000,0.3000",
        )

        self.assertRun("CONF:RAMP:RATE:UNITS 1", None)  # min^-1
        self.assertRun(
            ":FIELD:PROG?;:RAMP:RATE:FIELD?;:RAMP:FIELD?",
            "1.0000",
            "18.0000",
            "1.0000,18.0000",
        )
        self.assertRun(
            "CONF:RAMP:RATE:FIELD 0.3kG/min;:RAMP:RATE:FIELD?;:RAMP:FIELD?",
            None,
            "0.0300",
            "1.0000,0.0300",
        )
        self.assertRun(
            "CONF:RAMP:RATE:FIELD 0.3kG/s;:RAMP:RATE:FIELD?;:RAMP:FIELD?",
            None,
            "1.8000",
            "1.0000,1.8000",
        )

        self.assertRun(
            ":CURR:PROG?;:RAMP:RATE:CURR?;:RAMP:CURR?",
            "0.6667",
            "1.2000",
            "0.6667,1.2000",
        )

        self.assertRun(
            ":CONF:CURR:PROG 1;:CURR:PROG?;:RAMP:RATE:CURR?;:RAMP:CURR?",
            None,
            "1.0000",
            "1.2000",
            "1.0000,1.2000",
        )
        self.assertRun(
            ":FIELD:PROG?;:RAMP:RATE:FIELD?;:RAMP:FIELD?",
            "1.5000",
            "1.8000",
            "1.5000,1.8000",
        )

        self.assertRun(
            ":CONF:RAMP:RATE:CURR 1;:CURR:PROG?;:RAMP:RATE:CURR?;:RAMP:CURR?",
            None,
            "1.0000",
            "1.0000",
            "1.0000,1.0000",
        )
        self.assertRun(
            ":FIELD:PROG?;:RAMP:RATE:FIELD?;:RAMP:FIELD?",
            "1.5000",
            "1.5000",
            "1.5000,1.5000",
        )

        self.assertRun(
            ":CONF:RAMP:CURR 1.5A,10A/s;:CURR:PROG?;:RAMP:RATE:CURR?;:RAMP:CURR?",
            None,
            "1.5000",
            "600.0000",
            "1.5000,600.0000",
        )
        self.assertRun(
            ":FIELD:PROG?;:RAMP:RATE:FIELD?;:RAMP:FIELD?",
            "2.2500",
            "900.0000",
            "2.2500,900.0000",
        )

    def test_ramp(self):
        self.assertRun(":CONF:RAMP:FIELD 1T,10T/min", None)
        self.assertRun(":STATE?", "9")
        self.assertEqual(self.magnet.field, 0)
        self.assertRun(":RAMP;:FIELD:MAG?", None, "0.0000")
        time.sleep(0.1)
        self.assertRun(":STATE?", "1")
        while tuple(self.magnet.process(":STATE?")) == ("1",):
            time.sleep(0.1)
        self.assertRun(":STATE?;:FIELD:MAG?", "2", "10.0000")
        self.assertRun(":ZERO", None)
        time.sleep(0.1)
        while tuple(self.magnet.process(":STATE?")) == ("6",):
            time.sleep(0.1)
        self.assertRun(":STATE?;:FIELD:MAG?", "9", "0.0000")
        self.assertRun(":PAUSE", None)
        time.sleep(1)
        self.assertRun(":STATE?", "2")
        self.assertNonEqual(tuple(self.magnet.process(":FIELD:MAGNET?")), ("0.0000",))
        self.assertNonEqual(tuple(self.magnet.process(":FIELD:MAGNET?")), ("10.0000",))
