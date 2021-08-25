import server
import instrument
import unittest
import threading
import pyvisa

PORT = 9001


class Dummy(instrument.VirtualInstrument):
    def __init__(self):
        super().__init__("Dummy")


class DummyExperiment(server.Experiment):
    ports = (9001,)

    def __init__(self, client_ip):
        super().__init__(client_ip)
        self.instruments = {
            PORT: Dummy(),
        }


class ServerTest(unittest.TestCase):
    def setUp(self):
        self.server = server.Server(DummyExperiment, local=True)
        self.thread = threading.Thread(target=self.server.run)
        self.thread.start()
        self.rm = pyvisa.ResourceManager()

    def test_connection(self):
        inst = self.rm.open_resource(
            f"TCPIP::127.0.0.1::{PORT}::SOCKET", read_termination="\n"
        )
        inst.close()

    def test_connection(self):
        inst = self.rm.open_resource(
            f"TCPIP::127.0.0.1::{PORT}::SOCKET", read_termination="\n"
        )
        self.assertEqual(inst.query("*IDN?"), "Dummy")
        inst.close()

    def tearDown(self):
        self.server.shutdown_event.set()
        self.thread.join()
