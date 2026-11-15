"""
Blume Programming Language - Lexer / Tokenizer
Version: 1.0
100% Pure Python Implementation
"""

from enum import Enum, auto
from dataclasses import dataclass
from typing import List, Optional
from blume.ast import SourceLocation

class TokenType(Enum):
    # Literals
    INT_LIT = auto()
    FLOAT_LIT = auto()
    STRING_LIT = auto()
    BOOL_LIT = auto()
    NIL_LIT = auto()
    IDENTIFIER = auto()

    # Keywords
    FN = auto()
    LET = auto()
    VAR = auto()
    STRUCT = auto()
    CLASS = auto()
    INIT = auto()
    DEINIT = auto()
    IF = auto()
    ELSE = auto()
    WHILE = auto()
    FOR = auto()
    IN = auto()
    RETURN = auto()
    DEFER = auto()
    SELF = auto()
    NEW = auto()

    # Ownership Keywords (Blume Hybrid Memory Model)
    OWNED = auto()
    SHARED = auto()
    WEAK = auto()
    UNOWNED = auto()
    AUTOMATIC = auto()

    # Operators
    PLUS = auto()           # +
    MINUS = auto()          # -
    STAR = auto()           # *
    SLASH = auto()          # /
    PERCENT = auto()        # %
    ASSIGN = auto()         # =
    PLUS_ASSIGN = auto()    # +=
    MINUS_ASSIGN = auto()   # -=
    STAR_ASSIGN = auto()    # *=
    SLASH_ASSIGN = auto()   # /=
    EQ = auto()             # ==
    NEQ = auto()            # !=
    LT = auto()             # <
    LTE = auto()            # <=
    GT = auto()             # >
    GTE = auto()            # >=
    AND = auto()            # &&
    OR = auto()             # ||
    NOT = auto()            # !
    ARROW = auto()          # ->
    DOT = auto()            # .
    RANGE = auto()          # ..
    QUESTION = auto()       # ?

    # Delimiters
    LPAREN = auto()         # (
    RPAREN = auto()         # )
    LBRACE = auto()         # {
    RBRACE = auto()         # }
    LBRACKET = auto()       # [
    RBRACKET = auto()       # ]
    COLON = auto()          # :
    COMMA = auto()          # ,
    SEMICOLON = auto()      # ;

    EOF = auto()

KEYWORDS = {
    "fn": TokenType.FN,
    "let": TokenType.LET,
    "var": TokenType.VAR,
    "struct": TokenType.STRUCT,
    "class": TokenType.CLASS,
    "init": TokenType.INIT,
    "deinit": TokenType.DEINIT,
    "if": TokenType.IF,
    "else": TokenType.ELSE,
    "while": TokenType.WHILE,
    "for": TokenType.FOR,
    "in": TokenType.IN,
    "return": TokenType.RETURN,
    "defer": TokenType.DEFER,
    "self": TokenType.SELF,
    "new": TokenType.NEW,
    "true": TokenType.BOOL_LIT,
    "false": TokenType.BOOL_LIT,
    "nil": TokenType.NIL_LIT,

    # Ownership qualifiers
    "owned": TokenType.OWNED,
    "shared": TokenType.SHARED,
    "weak": TokenType.WEAK,
    "unowned": TokenType.UNOWNED,
    "automatic": TokenType.AUTOMATIC,

    # Word-based boolean operators
    "and": TokenType.AND,
    "or": TokenType.OR,
    "not": TokenType.NOT,
}

@dataclass
class Token:
    type: TokenType
    lexeme: str
    value: Optional[object]
    loc: SourceLocation

    def __repr__(self) -> str:
        return f"Token({self.type.name}, {self.lexeme!r}, {self.loc.line}:{self.loc.column})"

class LexerError(Exception):
    def __init__(self, message: str, loc: SourceLocation):
        super().__init__(f"LexerError at {loc}: {message}")
        self.message = message
        self.loc = loc

class Lexer:
    def __init__(self, source: str, filename: str = "<input>"):
        self.source = source
        self.filename = filename
        self.length = len(source)
        self.pos = 0
        self.line = 1
        self.column = 1

    def _curr_loc(self) -> SourceLocation:
        return SourceLocation(self.line, self.column, self.filename)

    def _peek(self, offset: int = 0) -> str:
        idx = self.pos + offset
        if idx >= self.length:
            return '\0'
        return self.source[idx]

    def _advance(self) -> str:
        if self.pos >= self.length:
            return '\0'
        ch = self.source[self.pos]
        self.pos += 1
        if ch == '\n':
            self.line += 1
            self.column = 1
        else:
            self.column += 1
        return ch

    def _match(self, expected: str) -> bool:
        if self._peek() == expected:
            self._advance()
            return True
        return False

    def tokenize(self) -> List[Token]:
        tokens: List[Token] = []

        while self.pos < self.length:
            ch = self._peek()

            # Whitespace
            if ch.isspace():
                self._advance()
                continue

            loc = self._curr_loc()

            # Comments
            if ch == '/' and self._peek(1) == '/':
                # Single-line comment
                while self.pos < self.length and self._peek() != '\n':
                    self._advance()
                continue
            elif ch == '/' and self._peek(1) == '*':
                # Multi-line comment
                self._advance() # /
                self._advance() # *
                depth = 1
                while self.pos < self.length and depth > 0:
                    if self._peek() == '/' and self._peek(1) == '*':
                        depth += 1
                        self._advance()
                        self._advance()
                    elif self._peek() == '*' and self._peek(1) == '/':
                        depth -= 1
                        self._advance()
                        self._advance()
                    else:
                        self._advance()
                if depth > 0:
                    raise LexerError("Unterminated multi-line comment", loc)
                continue

            # Numbers
            if ch.isdigit():
                tokens.append(self._number())
                continue

            # Strings
            if ch == '"':
                tokens.append(self._string())
                continue

            # Identifiers and keywords
            if ch.isalpha() or ch == '_':
                tokens.append(self._identifier())
                continue

            # Multi-character or single-character operators
            self._advance()
            if ch == '+':
                if self._match('='):
                    tokens.append(Token(TokenType.PLUS_ASSIGN, "+=", None, loc))
                else:
                    tokens.append(Token(TokenType.PLUS, "+", None, loc))
            elif ch == '-':
                if self._match('>'):
                    tokens.append(Token(TokenType.ARROW, "->", None, loc))
                elif self._match('='):
                    tokens.append(Token(TokenType.MINUS_ASSIGN, "-=", None, loc))
                else:
                    tokens.append(Token(TokenType.MINUS, "-", None, loc))
            elif ch == '*':
                if self._match('='):
                    tokens.append(Token(TokenType.STAR_ASSIGN, "*=", None, loc))
                else:
                    tokens.append(Token(TokenType.STAR, "*", None, loc))
            elif ch == '/':
                if self._match('='):
                    tokens.append(Token(TokenType.SLASH_ASSIGN, "/=", None, loc))
                else:
                    tokens.append(Token(TokenType.SLASH, "/", None, loc))
            elif ch == '%':
                tokens.append(Token(TokenType.PERCENT, "%", None, loc))
            elif ch == '=':
                if self._match('='):
                    tokens.append(Token(TokenType.EQ, "==", None, loc))
                else:
                    tokens.append(Token(TokenType.ASSIGN, "=", None, loc))
            elif ch == '!':
                if self._match('='):
                    tokens.append(Token(TokenType.NEQ, "!=", None, loc))
                else:
                    tokens.append(Token(TokenType.NOT, "!", None, loc))
            elif ch == '<':
                if self._match('='):
                    tokens.append(Token(TokenType.LTE, "<=", None, loc))
                else:
                    tokens.append(Token(TokenType.LT, "<", None, loc))
            elif ch == '>':
                if self._match('='):
                    tokens.append(Token(TokenType.GTE, ">=", None, loc))
                else:
                    tokens.append(Token(TokenType.GT, ">", None, loc))
            elif ch == '&':
                if self._match('&'):
                    tokens.append(Token(TokenType.AND, "&&", None, loc))
                else:
                    raise LexerError(f"Unexpected character '&', did you mean '&&'?", loc)
            elif ch == '|':
                if self._match('|'):
                    tokens.append(Token(TokenType.OR, "||", None, loc))
                else:
                    raise LexerError(f"Unexpected character '|', did you mean '||'?", loc)
            elif ch == '.':
                if self._match('.'):
                    tokens.append(Token(TokenType.RANGE, "..", None, loc))
                else:
                    tokens.append(Token(TokenType.DOT, ".", None, loc))
            elif ch == '?':
                tokens.append(Token(TokenType.QUESTION, "?", None, loc))
            elif ch == '(':
                tokens.append(Token(TokenType.LPAREN, "(", None, loc))
            elif ch == ')':
                tokens.append(Token(TokenType.RPAREN, ")", None, loc))
            elif ch == '{':
                tokens.append(Token(TokenType.LBRACE, "{", None, loc))
            elif ch == '}':
                tokens.append(Token(TokenType.RBRACE, "}", None, loc))
            elif ch == '[':
                tokens.append(Token(TokenType.LBRACKET, "[", None, loc))
            elif ch == ']':
                tokens.append(Token(TokenType.RBRACKET, "]", None, loc))
            elif ch == ':':
                tokens.append(Token(TokenType.COLON, ":", None, loc))
            elif ch == ',':
                tokens.append(Token(TokenType.COMMA, ",", None, loc))
            elif ch == ';':
                tokens.append(Token(TokenType.SEMICOLON, ";", None, loc))
            else:
                raise LexerError(f"Unexpected character: {ch!r}", loc)

        tokens.append(Token(TokenType.EOF, "", None, self._curr_loc()))
        return tokens

    def _number(self) -> Token:
        start_pos = self.pos
        loc = self._curr_loc()

        # Check for hex or binary
        if self._peek() == '0' and (self._peek(1) in ('x', 'X')):
            self._advance()
            self._advance()
            while self._peek().isalnum():
                self._advance()
            lexeme = self.source[start_pos:self.pos]
            val = int(lexeme, 16)
            return Token(TokenType.INT_LIT, lexeme, val, loc)

        if self._peek() == '0' and (self._peek(1) in ('b', 'B')):
            self._advance()
            self._advance()
            while self._peek() in ('0', '1'):
                self._advance()
            lexeme = self.source[start_pos:self.pos]
            val = int(lexeme, 2)
            return Token(TokenType.INT_LIT, lexeme, val, loc)

        is_float = False
        while self._peek().isdigit():
            self._advance()

        if self._peek() == '.' and self._peek(1).isdigit():
            is_float = True
            self._advance() # consume '.'
            while self._peek().isdigit():
                self._advance()

        lexeme = self.source[start_pos:self.pos]
        if is_float:
            return Token(TokenType.FLOAT_LIT, lexeme, float(lexeme), loc)
        else:
            return Token(TokenType.INT_LIT, lexeme, int(lexeme), loc)

    def _string(self) -> Token:
        loc = self._curr_loc()
        self._advance() # consume '"'
        chars = []
        while self.pos < self.length and self._peek() != '"':
            ch = self._advance()
            if ch == '\\':
                if self.pos >= self.length:
                    raise LexerError("Unterminated string escape", loc)
                esc = self._advance()
                if esc == 'n':
                    chars.append('\n')
                elif esc == 't':
                    chars.append('\t')
                elif esc == 'r':
                    chars.append('\r')
                elif esc == '\\':
                    chars.append('\\')
                elif esc == '"':
                    chars.append('"')
                elif esc == '0':
                    chars.append('\0')
                else:
                    chars.append(esc)
            else:
                chars.append(ch)

        if self.pos >= self.length:
            raise LexerError("Unterminated string literal", loc)

        self._advance() # consume closing '"'
        val = "".join(chars)
        return Token(TokenType.STRING_LIT, f'"{val}"', val, loc)

    def _identifier(self) -> Token:
        start_pos = self.pos
        loc = self._curr_loc()
        while self._peek().isalnum() or self._peek() == '_':
            self._advance()

        lexeme = self.source[start_pos:self.pos]
        if lexeme in KEYWORDS:
            tok_type = KEYWORDS[lexeme]
            val = None
            if tok_type == TokenType.BOOL_LIT:
                val = (lexeme == "true")
            elif tok_type == TokenType.NIL_LIT:
                val = None
            return Token(tok_type, lexeme, val, loc)
        return Token(TokenType.IDENTIFIER, lexeme, lexeme, loc)
