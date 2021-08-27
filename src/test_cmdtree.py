import instrument

import unittest

class TestCommandTree(unittest.TestCase):
    
    def test_parser(self):
        self.assertEqual(
            instrument.scpi.parse_variative_header('*IDN?'),
            ([(True, {'*IDN'})],
             True)
            )

        self.assertEqual(
            instrument.scpi.parse_variative_header(':FRequency:STOP', ignore_case=True),
            ([(True, {'FREQ', 'FREQUENCY'}),
              (True, {'STOP'})],
             False)
            )

        self.assertEqual(
            instrument.scpi.parse_variative_header(':FRequency:STOP', ignore_case=False),
            ([(True, {'FR', 'FREQUENCY'}),
              (True, {'STOP'})],
             False)
            )

        self.assertEqual(
            instrument.scpi.parse_variative_header(':CONFigure:VOLTage[:DC]'),
            ([(True, {'CONF', 'CONFIGURE'}),
              (True, {'VOLT', 'VOLTAGE'}),
              (False, [(True, {'DC'})])],
             False)
            )

        self.assertEqual(
            instrument.scpi.parse_variative_header(':SENSE[1]:VOLTage?'),
            ([(True, {'SENS', 'SENSE', 'SENSE1'}),
              (True, {'VOLT', 'VOLTAGE'})],
             True)
            )

        # Please find a more convoluted example
        self.assertEqual(
            instrument.scpi.parse_variative_header('[:SENSE[1][[:DC]:QU[ICK]]]:[T][H]ENk[:P]'),
            ([(False, [(True, {'SENS', 'SENSE', 'SENSE1'}),
                       (False, [(False, [(True, {'DC'})]),
                                (True, {'QU', 'QUIC', 'QUICK'})])]),
              (True, {'ENK', 'TENK', 'HENK', 'THENK', 'THEN'}),
              (False, [(True, {'P'})])],
             False)
            )
            
    
    def test_add(self):
        tree = instrument.CommandTree()
        tree[':A:V:K'] = 3
        tree[':A:V:K?'] = 4
        tree[':A:Q:K'] = 33
        tree[':B'] = 8
        tree['[:B]:R?'] = 7
        tree['*IDN?'] = 'Mary'
        
        self.assertEqual(tree.tree['A']['V']['K'][None], (3,4))
        self.assertEqual(tree.tree['A']['Q']['K'][None], (33,None))
        self.assertEqual(tree.tree['B'][None], (8,None))
        self.assertEqual(tree.tree['B']['R'][None], (None, 7))
        self.assertEqual(tree.tree['R'][None], (None, 7))
        self.assertEqual(tree.tree['*IDN'][None], (None, 'Mary'))
        
    def test_access(self):
        tree = instrument.CommandTree()
        tree['[:SENSE[1][[:DC]:QU[ICK]]]:[T][H]ENk[:P]'] = 77
        self.assertEqual(tree[':SENSE:ENK'], 77)
        self.assertEqual(tree[':SENSE1:DC:QU:TENK:P'], 77)
        self.assertEqual(tree[':SENS:QUIC:THEN'], 77)
        
    def test_parent(self):
        tree = instrument.CommandTree()
        self.assertEqual(tree.parent(':CONF'), '')
        self.assertEqual(tree.parent(':CONF:DC'), ':CONF')
        self.assertEqual(tree.parent(':AC:BC:CC:DC'), ':AC:BC:CC')
        self.assertEqual(tree.parent('*IDN'), '')


class TestTreeResolution(unittest.TestCase):

    def setUp(self):
        self.receiver = instrument.SCPI_receiver()
        self.receiver.commands = instrument.CommandTree()
        
        def add_gs(name):
            self.receiver.commands[name] = lambda s,*q:name

        add_gs(':FREQUENCY:START')
        add_gs(':FREQUENCY:STOP')
        add_gs(':FREQUENCY:SLEW')
        add_gs(':FREQUENCY:SLEW:AUTO')
        add_gs(':FREQUENCY:BANDWIDTH')
        add_gs(':POWER:START')
        add_gs(':POWER:STOP')
        add_gs(':BAND')
    
    def assertRun(self, command, *results):
        self.assertEqual(tuple(self.receiver.process(command)), results)
        
    def assertFail(self, command):
        with self.assertRaises(instrument.ProtocolError):
            for resp in self.receiver.process(command):
                pass # print(resp)
    
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
    