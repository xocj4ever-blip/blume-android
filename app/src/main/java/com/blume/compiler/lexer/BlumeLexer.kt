package com.blume.compiler.lexer

import com.blume.compiler.ast.SourceLocation

enum class TokenType {
    // Literals
    INT_LIT,
    FLOAT_LIT,
    STRING_LIT,
    BOOL_LIT,
    NIL_LIT,
    IDENTIFIER,

    // Keywords
    FN,
    LET,
    VAR,
    STRUCT,
    CLASS,
    INIT,
    DEINIT,
    IF,
    ELSE,
    WHILE,
    FOR,
    IN,
    RETURN,
    DEFER,
    SELF,
    NEW,

    // Ownership Keywords
    OWNED,
    SHARED,
    WEAK,
    UNOWNED,
    AUTOMATIC,

    // Operators
    PLUS, MINUS, STAR, SLASH, PERCENT,
    ASSIGN, PLUS_ASSIGN, MINUS_ASSIGN, STAR_ASSIGN, SLASH_ASSIGN,
    EQ, NEQ, LT, LTE, GT, GTE,
    AND, OR, NOT,
    ARROW, DOT, RANGE, QUESTION,

    // Delimiters
    LPAREN, RPAREN,
    LBRACE, RBRACE,
    LBRACKET, RBRACKET,
    COLON, COMMA, SEMICOLON,

    EOF
}

data class Token(
    val type: TokenType,
    val lexeme: String,
    val value: Any?,
    val loc: SourceLocation
) {
    override fun toString(): String = "Token($type, '$lexeme', $loc)"
}

class LexerException(message: String, val loc: SourceLocation) : Exception("LexerError at $loc: $message")

class BlumeLexer(private val source: String, private val filename: String = "<input>") {
    private val length = source.length
    private var pos = 0
    private var line = 1
    private var column = 1

    companion object {
        val KEYWORDS = mapOf(
            "fn" to TokenType.FN,
            "let" to TokenType.LET,
            "var" to TokenType.VAR,
            "struct" to TokenType.STRUCT,
            "class" to TokenType.CLASS,
            "init" to TokenType.INIT,
            "deinit" to TokenType.DEINIT,
            "if" to TokenType.IF,
            "else" to TokenType.ELSE,
            "while" to TokenType.WHILE,
            "for" to TokenType.FOR,
            "in" to TokenType.IN,
            "return" to TokenType.RETURN,
            "defer" to TokenType.DEFER,
            "self" to TokenType.SELF,
            "new" to TokenType.NEW,
            "true" to TokenType.BOOL_LIT,
            "false" to TokenType.BOOL_LIT,
            "nil" to TokenType.NIL_LIT,
            "owned" to TokenType.OWNED,
            "shared" to TokenType.SHARED,
            "weak" to TokenType.WEAK,
            "unowned" to TokenType.UNOWNED,
            "automatic" to TokenType.AUTOMATIC,
            "and" to TokenType.AND,
            "or" to TokenType.OR,
            "not" to TokenType.NOT
        )
    }

    private fun currLoc(): SourceLocation = SourceLocation(line, column, filename)

    private fun peek(offset: Int = 0): Char {
        val idx = pos + offset
        return if (idx >= length) '\u0000' else source[idx]
    }

    private fun advance(): Char {
        if (pos >= length) return '\u0000'
        val ch = source[pos++]
        if (ch == '\n') {
            line++
            column = 1
        } else {
            column++
        }
        return ch
    }

    private fun match(expected: Char): Boolean {
        if (peek() == expected) {
            advance()
            return true
        }
        return false
    }

    fun tokenize(): List<Token> {
        val tokens = mutableListOf<Token>()

        while (pos < length) {
            val ch = peek()

            if (ch.isWhitespace()) {
                advance()
                continue
            }

            val loc = currLoc()

            // Comments
            if (ch == '/' && peek(1) == '/') {
                while (pos < length && peek() != '\n') advance()
                continue
            }
            if (ch == '/' && peek(1) == '*') {
                advance(); advance()
                while (pos < length && !(peek() == '*' && peek(1) == '/')) advance()
                if (pos < length) { advance(); advance() }
                continue
            }

            // Identifiers & Keywords
            if (ch.isLetter() || ch == '_') {
                val start = pos
                while (peek().isLetterOrDigit() || peek() == '_') advance()
                val lexeme = source.substring(start, pos)
                val type = KEYWORDS[lexeme] ?: TokenType.IDENTIFIER
                val value = when (type) {
                    TokenType.BOOL_LIT -> lexeme == "true"
                    TokenType.NIL_LIT -> null
                    else -> lexeme
                }
                tokens.add(Token(type, lexeme, value, loc))
                continue
            }

            // Numbers
            if (ch.isDigit()) {
                val start = pos
                while (peek().isDigit()) advance()
                if (peek() == '.' && peek(1).isDigit()) {
                    advance() // consume '.'
                    while (peek().isDigit()) advance()
                    val lexeme = source.substring(start, pos)
                    tokens.add(Token(TokenType.FLOAT_LIT, lexeme, lexeme.toDouble(), loc))
                } else {
                    val lexeme = source.substring(start, pos)
                    tokens.add(Token(TokenType.INT_LIT, lexeme, lexeme.toLong(), loc))
                }
                continue
            }

            // Strings
            if (ch == '"') {
                advance() // opening quote
                val sb = StringBuilder()
                while (pos < length && peek() != '"') {
                    val sc = advance()
                    if (sc == '\\') {
                        when (val esc = advance()) {
                            'n' -> sb.append('\n')
                            't' -> sb.append('\t')
                            'r' -> sb.append('\r')
                            '\\' -> sb.append('\\')
                            '"' -> sb.append('"')
                            else -> sb.append(esc)
                        }
                    } else {
                        sb.append(sc)
                    }
                }
                if (pos < length && peek() == '"') advance() // closing quote
                val strVal = sb.toString()
                tokens.add(Token(TokenType.STRING_LIT, "\"$strVal\"", strVal, loc))
                continue
            }

            // Operators & Punctuation
            advance()
            when (ch) {
                '+' -> {
                    if (match('=')) tokens.add(Token(TokenType.PLUS_ASSIGN, "+=", null, loc))
                    else tokens.add(Token(TokenType.PLUS, "+", null, loc))
                }
                '-' -> {
                    if (match('>')) tokens.add(Token(TokenType.ARROW, "->", null, loc))
                    else if (match('=')) tokens.add(Token(TokenType.MINUS_ASSIGN, "-=", null, loc))
                    else tokens.add(Token(TokenType.MINUS, "-", null, loc))
                }
                '*' -> {
                    if (match('=')) tokens.add(Token(TokenType.STAR_ASSIGN, "*=", null, loc))
                    else tokens.add(Token(TokenType.STAR, "*", null, loc))
                }
                '/' -> {
                    if (match('=')) tokens.add(Token(TokenType.SLASH_ASSIGN, "/=", null, loc))
                    else tokens.add(Token(TokenType.SLASH, "/", null, loc))
                }
                '%' -> tokens.add(Token(TokenType.PERCENT, "%", null, loc))
                '=' -> {
                    if (match('=')) tokens.add(Token(TokenType.EQ, "==", null, loc))
                    else tokens.add(Token(TokenType.ASSIGN, "=", null, loc))
                }
                '!' -> {
                    if (match('=')) tokens.add(Token(TokenType.NEQ, "!=", null, loc))
                    else tokens.add(Token(TokenType.NOT, "!", null, loc))
                }
                '<' -> {
                    if (match('=')) tokens.add(Token(TokenType.LTE, "<=", null, loc))
                    else tokens.add(Token(TokenType.LT, "<", null, loc))
                }
                '>' -> {
                    if (match('=')) tokens.add(Token(TokenType.GTE, ">=", null, loc))
                    else tokens.add(Token(TokenType.GT, ">", null, loc))
                }
                '&' -> {
                    if (match('&')) tokens.add(Token(TokenType.AND, "&&", null, loc))
                    else throw LexerException("Unexpected character '&', did you mean '&&'?", loc)
                }
                '|' -> {
                    if (match('|')) tokens.add(Token(TokenType.OR, "||", null, loc))
                    else throw LexerException("Unexpected character '|', did you mean '||'?", loc)
                }
                '.' -> {
                    if (match('.')) tokens.add(Token(TokenType.RANGE, "..", null, loc))
                    else tokens.add(Token(TokenType.DOT, ".", null, loc))
                }
                '?' -> tokens.add(Token(TokenType.QUESTION, "?", null, loc))
                '(' -> tokens.add(Token(TokenType.LPAREN, "(", null, loc))
                ')' -> tokens.add(Token(TokenType.RPAREN, ")", null, loc))
                '{' -> tokens.add(Token(TokenType.LBRACE, "{", null, loc))
                '}' -> tokens.add(Token(TokenType.RBRACE, "}", null, loc))
                '[' -> tokens.add(Token(TokenType.LBRACKET, "[", null, loc))
                ']' -> tokens.add(Token(TokenType.RBRACKET, "]", null, loc))
                ':' -> tokens.add(Token(TokenType.COLON, ":", null, loc))
                ',' -> tokens.add(Token(TokenType.COMMA, ",", null, loc))
                ';' -> tokens.add(Token(TokenType.SEMICOLON, ";", null, loc))
                else -> throw LexerException("Unexpected character: '$ch'", loc)
            }
        }

        tokens.add(Token(TokenType.EOF, "", null, currLoc()))
        return tokens
    }
}
