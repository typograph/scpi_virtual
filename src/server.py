#
# A server for virtual instruments.
#
# This should support VISA SOCKET protocol (connection via <ip>::<port>::SOCKET)
#
# The server will run a number of identical parallel experiments, one for every
# connected user (ID-ed by IP address). The instruments in the experiment
# will get the requests sent to their port via their input queue and must respond 
# using the output queue.
#
# Each experiment is in a separate thread, and each port listener also has its own
# thread. Inter-thread communication is done entirely via i/o queues on the 
# individual instruments.
#

import socket
import threading
import queue
import time

class Experiment(threading.Thread):
    """The `Experiment` is a thread containing all instruments
    for a single user. All interaction between instruments should happen here.
    
    For running your own virtual experiments subclass this and add hooks that
    would connect the output of one instrument with inputs from the others.
    
    Any subclass should defive a class variable `ports` containing a list of all
    available ports (instruments).
    """

    instruments = {}

    def __init__(self, end_event):
        super().__init__(daemon=False)
        self.instruments = {}
        self.end_event = end_event
    
    def run(self):
        """This makes every instrument poll for incoming messages"""
        while not self.end_event.is_set():
            try:
                for instrument in self.instruments.values():
                    instrument.process_messages()
            except BaseException:
                self.end_event.set()
                raise

class Server:
    def __init__(self, experiment_class, local=False, **experiment_kwargs):
        self.exp_class = experiment_class
        self.exp_kwargs = experiment_kwargs

        self.sockets = {}

        hostname = 'localhost' if local else socket.gethostbyname(socket.gethostname())

        for port in self.exp_class.ports:
            self.sockets[port] = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sockets[port].settimeout(1)
            self.sockets[port].bind((hostname, port))
            print(f"Socket bound at {hostname}:{port}")

        self.experiments = {}
        self.instrulock = threading.Lock()
        self.buffer = b""
        self.shutdown_event = threading.Event()

    def run(self):
        self.shutdown_event.clear()
        for port, serversocket in self.sockets.items():
            serversocket.listen(5)
            threading.Thread(target = self.listen,
                             args = (serversocket,),
                             daemon=False).start()
        while not self.shutdown_event.is_set():
            try:
                time.sleep(0.05)
            except BaseException as e:
                self.shutdown_event.set()
                raise
                

    def instrument(self, port, address):
        with self.instrulock:
            if address not in self.experiments:
                self.experiments[address] = self.exp_class(self.shutdown_event, **self.exp_kwargs)
                self.experiments[address].start()
            try:
                return self.experiments[address].instruments[port]
            except KeyError as e:
                raise ValueError(f'No instrument found at port {port}.'
                                 f'Available ports are {tuple(self.experiments[address].instruments.keys())}')

    def listen(self, serversocket):
        print(f"Listening at {serversocket.getsockname()}")
        while not self.shutdown_event.is_set():
            # accept connections from outside
            try:
                (clientsocket, address) = serversocket.accept()
                clientsocket.settimeout(1)
                print(f"Connection from {address}")
                instrument = self.instrument(serversocket.getsockname()[1], address[0])
                threading.Thread(target = self.communicate,
                                 args = (clientsocket,instrument),
                                 daemon = False).start()
            except socket.timeout:
                pass
            except BaseException:
                self.shutdown_event.set()
                raise

# Locks
#
# The socket-listening thread needs write access to its instrument.
# A change of a parameter may trigger an experiment hook, which will write
# to the same instrument (no problem) or to a different instrument (problem,
# if another socket-listening thread tries to change that different instrument
# at the same time).
#
# The most obvious solution would be to put a lock on every instrument,
# that would be acquired by the socket thread and/or experiment as needed.
# But this is a problem, because experiment might try to lock
# the same instrument during the update loop, which will deadlock the threads.
#
# Next solution would be to lock every experiment, so that only one socket
# can talk to the experiment at a time. This might be a problem if there
# are any instruments that must be controlled in parallel. E.g. a long measurement
# on one while changing some things on the other.
#
# It should be possible to just set up a message queue and lock that.
# The socket thread will write to the input queue, and will read the
# response from the output queue. The experiment will make the instruments
# poll the queues with a certain periodicity.
#
    def communicate(self, datasocket, instrument):
        line_end_chars = instrument.lineending
        datasocket.settimeout(0.05)
        while not self.shutdown_event.is_set():
            # In case that the command is very long
            # or extremely many commands come at once
            # the buffer can store the incomplete tail
            # until the rest comes along.
            try:
                things = self.buffer + datasocket.recv(4096)
                commands = things.split(line_end_chars)
                self.buffer = commands[-1]
                for cmd in commands[:-1]:
                    try:
                        instrument.iqueue.put(cmd)
                    except queue.Full:
                        # OK, this is bad, the instrument is not processing for some reason.
                        print(f"Queue full on {instrument.name}:{datasocket.port}")
                        instrument.iqueue.join() # That might block indefinitely
                        instrument.iqueue.put(cmd)
                        
            except socket.timeout:
                pass
            except BaseException:
                self.shutdown_event.set()
                raise

            while not instrument.oqueue.empty():
                try:
                    datasocket.send(instrument.oqueue.get(timeout=0.05))
                except queue.Empty:
                    # This thread is the only consumer, so this outcome
                    # is almost impossible, but even if the queue is empty,
                    # the cycle is not going to run again
                    pass
            # It is possible that we miss the instrument response
            # But we should get it again on the next run.
