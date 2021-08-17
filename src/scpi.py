import pyparsing as pp
from pyparsing import pyparsing_common as ppc

pp.ParserElement.enablePackrat()
pp.ParserElement.setDefaultWhitespaceChars(pp.srange('[\x00-\x09\x0b-\x20]'))

program_mnemonic = pp.Word(pp.alphas, pp.alphas+'_')

program_mnemonic = pp.Word(pp.alphas, pp.alphas+'_')

character_program_data = program_mnemonic.copy()

mantissa = pp.Combine(pp.Optional(pp.Char('+-'))
                                  + ((pp.Char('.') + pp.Word(pp.nums))
                                     | (pp.Word(pp.nums) + pp.Optional(pp.Char('.')
                                                                 + pp.Optional(pp.Word(pp.nums), default='0'))))
                                  ).setResultsName("mantissa").setParseAction(lambda t:float(t[0]) if '.' in t[0] else int(t[0]))
exponent = pp.Optional(pp.Char('eE')
                       + pp.Combine(pp.Optional(pp.Char('+-'))
                                    + pp.Word(pp.nums)).setResultsName('exponent')
                                                       .setParseAction(lambda t:int(t[0]))
                      )
decimal_numeric_program_data = (mantissa + exponent)\
                                .setResultsName("value")\
                                .setParseAction(lambda t: t.mantissa * (10**t.exponent if t.exponent!='' else 1))
                               

suffix_program_data = pp.Combine(pp.Optional(pp.Char('/'))
                                 + pp.delimitedList(
                                     pp.Word(pp.alphas)+ pp.Optional(pp.Optional(pp.Char('-')) + pp.Char(pp.nums)),
                                     delim=pp.Char('./'), combine=True))("suffix")
hex_numeric = pp.Word('hH', '0123456789aAbBcCdDeEfF').setParseAction(lambda s,i,t:int(t[0][1:], base=16))
oct_numeric = pp.Word('qQ', '01234567').setParseAction(lambda s,i,t:int(t[0][1:], base=8))
bin_numeric = pp.Word('bB', '01').setParseAction(lambda s,i,t:int(t[0][1:], base=2))
nondecimal_numeric_program_data = pp.Combine(pp.Suppress('#') + (hex_numeric | oct_numeric | bin_numeric))
string_program_data = pp.QuotedString("'", escQuote="''", unquoteResults=True, convertWhitespaceEscapes=False)

class FiniteBlock(pp.Token):
    """
    Matches IEEE finite block string.
    Example::
        FiniteBlock().parse_string('111')  # -> [b'1']
        FiniteBlock().parse_string('216stranger things;')  # -> [b'stranger things;']
        FiniteBlock().parse_string('215stranger things;')  # -> [b'stranger things']
    """

    def __init__(self):
        super().__init__()
        self.name = 'FiniteBlock'
        self.mayReturnEmpty = False
        self.mayIndexError = False

    def _generateDefaultName(self):
        return 'FiniteBlock()'

    def parseImpl(self, instring, loc, doActions=True):
        if instring[loc] != '#':
            raise pp.ParseException(instring, loc, "Not a block", self)
        loc += 1
        if instring[loc] not in '123456789':
            raise pp.ParseException(instring, loc, f"Invalid block length length {instring[loc]}", self)
        ll = int(instring[loc])
        loc += 1
        if loc + ll >= len(instring):
            raise pp.ParseException(instring, loc, f"Message too short for block length length {ll}", self)
        l = int(instring[loc:loc+ll])
        loc += ll
        if loc + l >= len(instring):
            raise pp.ParseException(instring, loc, f"Message too short for block length {l}", self)
        return loc + l, instring[loc:loc+l].encode('latin1')

infinite_arbitrary_block_program_data = pp.Combine(pp.Literal('#0') + pp.SkipTo(pp.StringEnd()))

#expression_program_data = pp.nestedExpr('(', ')',
#                                        pp.Combine(character_program_data("symbol")
#                                                  ^ pp.Group(decimal_numeric_program_data + pp.Optional(suffix_program_data))("number")
#                                                  ^ nondecimal_numeric_program_data("number")
#                                                  ^ string_program_data("string")
#                                                  ^ FiniteBlock()("block")
#                                                  ^ expression_program_data("expression"),
#                                                    adjacent=False))

program_data = pp.Group(pp.Combine(
                 character_program_data("symbol")
                 ^ pp.Group(decimal_numeric_program_data + pp.Optional(suffix_program_data))("number")
                 ^ nondecimal_numeric_program_data("number")
                 ^ string_program_data("string")
                 ^ FiniteBlock()("block")
                 ^ infinite_arbitrary_block_program_data("block")
#                 ^ expression_program_data("expression")
                                  , adjacent=False))

compound_program_header = pp.Combine(pp.Optional(pp.Char(':'))\
                                     + pp.delimitedList(program_mnemonic, delim=':', combine=True))
common_program_header = pp.Combine(pp.Char('*') + program_mnemonic)

program_header = (common_program_header | compound_program_header)\
                      .setResultsName('command') \
                 + pp.Optional(pp.Char('?'), default=False) \
                      .leaveWhitespace().setParseAction(lambda:True).setResultsName('query')


compound_program_header = pp.Combine(pp.Optional(pp.Char(':'))\
                                     + pp.delimitedList(program_mnemonic, delim=':', combine=True))
common_program_header = pp.Combine(pp.Char('*') + program_mnemonic)

program_header = (common_program_header | compound_program_header)\
                      .setResultsName('header') \
                 + pp.Optional(pp.Char('?'), default=False) \
                      .leaveWhitespace().setParseAction(lambda t:t[0] == '?').setResultsName('query')

program_message_unit = pp.Group(program_header + 
                                pp.Optional(pp.Word(pp.ParserElement.DEFAULT_WHITE_CHARS)
                                              .leaveWhitespace()
                                               .suppress() + 
                                            pp.delimitedList(program_data, delim=',', combine=False)('args'))
                               )
program_message = pp.Optional(pp.delimitedList(program_message_unit | pp.SkipTo(pp.StringEnd())('error'), delim=';')('commands'))

def parse(string):
    results =  program_message.parseString(string, parseAll=True)
    results.pprint()
    return results
