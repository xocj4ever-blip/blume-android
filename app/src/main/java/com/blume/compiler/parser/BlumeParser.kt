package com.blume.compiler.parser

import com.blume.compiler.ast.*
import com.blume.compiler.lexer.Token
import com.blume.compiler.lexer.TokenType

class ParserException(message: String, val loc: SourceLocation) : Exception("ParserError at $loc: $message")

class BlumeParser(private val tokens: List<Token>) {
    private var pos = 0

    private fun curr(): Token = if (pos >= tokens.size) tokens.last() else tokens[pos]
    private fun peek(offset: Int = 1): Token {
        val idx = pos + offset
        return if (idx >= tokens.size) tokens.last() else tokens[idx]
    }

    private fun check(vararg types: TokenType): Boolean = curr().type in types
    private fun advance(): Token {
        val tok = curr()
        if (pos < tokens.size - 1) pos++
        return tok
    }

    private fun match(vararg types: TokenType): Boolean {
        if (check(*types)) {
            advance()
            return true
        }
        return false
    }

    private fun consume(type: TokenType, errMsg: String): Token {
        if (check(type)) return advance()
        val c = curr()
        throw ParserException("$errMsg (got ${c.type} '${c.lexeme}')", c.loc)
    }

    fun parse(): ProgramNode {
        val loc = curr().loc
        val decls = mutableListOf<ASTNode>()

        while (!check(TokenType.EOF)) {
            if (match(TokenType.SEMICOLON)) continue
            decls.add(parseTopLevel())
        }
        return ProgramNode(loc, decls)
    }

    private fun parseTopLevel(): ASTNode {
        val c = curr()

        if (c.type in listOf(TokenType.OWNED, TokenType.SHARED, TokenType.AUTOMATIC) && peek().type == TokenType.CLASS) {
            val ownership = OwnershipKind.fromString(advance().lexeme)
            return parseClassDecl(ownership)
        }

        if (c.type == TokenType.CLASS) {
            return parseClassDecl(OwnershipKind.OWNED)
        }

        if (c.type == TokenType.STRUCT) {
            return parseStructDecl()
        }

        if (c.type == TokenType.FN) {
            return parseFuncDecl(isMethod = false)
        }

        return parseStmt()
    }

    private fun parseType(): TypeNode {
        val loc = curr().loc
        var ownership = OwnershipKind.AUTOMATIC

        if (check(TokenType.OWNED, TokenType.SHARED, TokenType.WEAK, TokenType.UNOWNED, TokenType.AUTOMATIC)) {
            ownership = OwnershipKind.fromString(advance().lexeme)
        }

        val nameTok = consume(TokenType.IDENTIFIER, "Expected type name")
        val genericArgs = mutableListOf<TypeNode>()
        if (match(TokenType.LBRACKET)) {
            while (!check(TokenType.RBRACKET, TokenType.EOF)) {
                genericArgs.add(parseType())
                if (!match(TokenType.COMMA)) break
            }
            consume(TokenType.RBRACKET, "Expected ']' after generic type arguments")
        }

        val isOptional = match(TokenType.QUESTION)
        return TypeNode(loc, nameTok.lexeme, ownership, isOptional, genericArgs)
    }

    private fun parseFuncDecl(isMethod: Boolean): FuncDecl {
        val loc = curr().loc
        consume(TokenType.FN, "Expected 'fn'")
        val nameTok = consume(TokenType.IDENTIFIER, "Expected function name")
        consume(TokenType.LPAREN, "Expected '(' after function name")

        val params = mutableListOf<ParamNode>()
        if (!check(TokenType.RPAREN)) {
            while (true) {
                val pLoc = curr().loc
                var pOwnership = OwnershipKind.AUTOMATIC
                if (check(TokenType.OWNED, TokenType.SHARED, TokenType.WEAK, TokenType.UNOWNED)) {
                    pOwnership = OwnershipKind.fromString(advance().lexeme)
                }
                val pName = consume(TokenType.IDENTIFIER, "Expected parameter name").lexeme
                consume(TokenType.COLON, "Expected ':' after parameter name")
                val pType = parseType()
                if (pOwnership == OwnershipKind.AUTOMATIC) {
                    pOwnership = pType.ownership
                }
                params.add(ParamNode(pLoc, pName, pType, pOwnership))
                if (!match(TokenType.COMMA)) break
            }
        }
        consume(TokenType.RPAREN, "Expected ')' after parameters")

        var returnType = TypeNode(loc, "Void")
        if (match(TokenType.ARROW)) {
            returnType = parseType()
        }

        val body = parseBlockStmt()
        return FuncDecl(loc, nameTok.lexeme, params, returnType, body, isMethod)
    }

    private fun parseStructDecl(): StructDecl {
        val loc = curr().loc
        consume(TokenType.STRUCT, "Expected 'struct'")
        val nameTok = consume(TokenType.IDENTIFIER, "Expected struct name")
        consume(TokenType.LBRACE, "Expected '{' before struct body")

        val fields = mutableListOf<FieldNode>()
        while (!check(TokenType.RBRACE, TokenType.EOF)) {
            if (match(TokenType.SEMICOLON)) continue
            match(TokenType.VAR, TokenType.LET)
            val fLoc = curr().loc
            val fName = consume(TokenType.IDENTIFIER, "Expected field name").lexeme
            consume(TokenType.COLON, "Expected ':' after field name")
            val fType = parseType()
            var initExpr: ExprNode? = null
            if (match(TokenType.ASSIGN)) {
                initExpr = parseExpr()
            }
            match(TokenType.SEMICOLON)
            fields.add(FieldNode(fLoc, fName, fType, fType.ownership, initExpr))
        }
        consume(TokenType.RBRACE, "Expected '}' after struct body")
        return StructDecl(loc, nameTok.lexeme, fields)
    }

    private fun parseClassDecl(defaultOwnership: OwnershipKind): ClassDecl {
        val loc = curr().loc
        consume(TokenType.CLASS, "Expected 'class'")
        val nameTok = consume(TokenType.IDENTIFIER, "Expected class name")
        consume(TokenType.LBRACE, "Expected '{' before class body")

        val fields = mutableListOf<FieldNode>()
        var initMethod: FuncDecl? = null
        var deinitMethod: BlockStmt? = null
        val methods = mutableListOf<FuncDecl>()

        while (!check(TokenType.RBRACE, TokenType.EOF)) {
            if (match(TokenType.SEMICOLON)) continue

            if (check(TokenType.VAR, TokenType.LET, TokenType.WEAK, TokenType.UNOWNED, TokenType.OWNED, TokenType.SHARED)) {
                var fieldOwnership = OwnershipKind.AUTOMATIC
                if (check(TokenType.WEAK, TokenType.UNOWNED, TokenType.OWNED, TokenType.SHARED)) {
                    fieldOwnership = OwnershipKind.fromString(advance().lexeme)
                }
                val isVar = match(TokenType.VAR)
                if (!isVar) consume(TokenType.LET, "Expected 'var' or 'let' in field declaration")

                val fLoc = curr().loc
                val fName = consume(TokenType.IDENTIFIER, "Expected field name").lexeme
                consume(TokenType.COLON, "Expected ':' after field name")
                val fType = parseType()
                if (fieldOwnership != OwnershipKind.AUTOMATIC) {
                    fType.ownership = fieldOwnership
                } else {
                    fieldOwnership = fType.ownership
                }

                var initExpr: ExprNode? = null
                if (match(TokenType.ASSIGN)) {
                    initExpr = parseExpr()
                }
                match(TokenType.SEMICOLON)
                fields.add(FieldNode(fLoc, fName, fType, fieldOwnership, initExpr))
            } else if (check(TokenType.INIT)) {
                val initLoc = advance().loc
                consume(TokenType.LPAREN, "Expected '(' after 'init'")
                val params = mutableListOf<ParamNode>()
                if (!check(TokenType.RPAREN)) {
                    while (true) {
                        val pLoc = curr().loc
                        val pName = consume(TokenType.IDENTIFIER, "Expected parameter name").lexeme
                        consume(TokenType.COLON, "Expected ':' after parameter name")
                        val pType = parseType()
                        params.add(ParamNode(pLoc, pName, pType, pType.ownership))
                        if (!match(TokenType.COMMA)) break
                    }
                }
                consume(TokenType.RPAREN, "Expected ')' after init parameters")
                val body = parseBlockStmt()
                initMethod = FuncDecl(initLoc, "init", params, TypeNode(initLoc, "Void"), body, isMethod = true)
            } else if (check(TokenType.DEINIT)) {
                advance()
                deinitMethod = parseBlockStmt()
            } else if (check(TokenType.FN)) {
                methods.add(parseFuncDecl(isMethod = true))
            } else {
                throw ParserException("Unexpected token in class body: '${curr().lexeme}'", curr().loc)
            }
        }
        consume(TokenType.RBRACE, "Expected '}' after class body")
        return ClassDecl(loc, nameTok.lexeme, defaultOwnership, fields, initMethod, deinitMethod, methods)
    }

    private fun parseStmt(): StmtNode {
        if (check(TokenType.LBRACE)) return parseBlockStmt()

        if (check(TokenType.LET, TokenType.VAR, TokenType.OWNED, TokenType.SHARED, TokenType.WEAK, TokenType.UNOWNED, TokenType.AUTOMATIC)) {
            if (curr().type in listOf(TokenType.OWNED, TokenType.SHARED, TokenType.WEAK, TokenType.UNOWNED, TokenType.AUTOMATIC)) {
                if (peek().type in listOf(TokenType.LET, TokenType.VAR)) return parseVarDecl()
            } else {
                return parseVarDecl()
            }
        }

        if (check(TokenType.IF)) return parseIfStmt()
        if (check(TokenType.WHILE)) return parseWhileStmt()
        if (check(TokenType.FOR)) return parseForStmt()
        if (check(TokenType.RETURN)) return parseReturnStmt()
        if (check(TokenType.DEFER)) return parseDeferStmt()

        val expr = parseExpr()
        if (check(TokenType.ASSIGN, TokenType.PLUS_ASSIGN, TokenType.MINUS_ASSIGN, TokenType.STAR_ASSIGN, TokenType.SLASH_ASSIGN)) {
            val opTok = advance()
            var valExpr = parseExpr()
            if (opTok.type != TokenType.ASSIGN) {
                val binOp = opTok.lexeme.substring(0, 1)
                valExpr = BinaryExpr(opTok.loc, expr, binOp, valExpr)
            }
            match(TokenType.SEMICOLON)
            return AssignStmt(expr.loc, expr, valExpr)
        }

        match(TokenType.SEMICOLON)
        return ExprStmt(expr.loc, expr)
    }

    private fun parseBlockStmt(): BlockStmt {
        val loc = curr().loc
        consume(TokenType.LBRACE, "Expected '{'")
        val stmts = mutableListOf<StmtNode>()
        while (!check(TokenType.RBRACE, TokenType.EOF)) {
            if (match(TokenType.SEMICOLON)) continue
            stmts.add(parseStmt())
        }
        consume(TokenType.RBRACE, "Expected '}'")
        return BlockStmt(loc, stmts)
    }

    private fun parseVarDecl(): VarDeclStmt {
        val loc = curr().loc
        var ownership = OwnershipKind.AUTOMATIC
        if (check(TokenType.OWNED, TokenType.SHARED, TokenType.WEAK, TokenType.UNOWNED, TokenType.AUTOMATIC)) {
            ownership = OwnershipKind.fromString(advance().lexeme)
        }
        val isConst = match(TokenType.LET)
        if (!isConst) consume(TokenType.VAR, "Expected 'let' or 'var'")

        val nameTok = consume(TokenType.IDENTIFIER, "Expected variable name")
        var typeAnn: TypeNode? = null
        if (match(TokenType.COLON)) {
            typeAnn = parseType()
            if (ownership == OwnershipKind.AUTOMATIC) {
                ownership = typeAnn.ownership
            }
        }

        var initExpr: ExprNode? = null
        if (match(TokenType.ASSIGN)) {
            initExpr = parseExpr()
        }
        match(TokenType.SEMICOLON)
        return VarDeclStmt(loc, nameTok.lexeme, typeAnn, initExpr, isConst, ownership)
    }

    private fun parseIfStmt(): IfStmt {
        val loc = curr().loc
        consume(TokenType.IF, "Expected 'if'")
        val cond = parseExpr()
        val thenBranch = parseBlockStmt()
        var elseBranch: BlockStmt? = null
        if (match(TokenType.ELSE)) {
            elseBranch = if (check(TokenType.IF)) {
                val nestedIf = parseIfStmt()
                BlockStmt(nestedIf.loc, mutableListOf(nestedIf))
            } else {
                parseBlockStmt()
            }
        }
        return IfStmt(loc, cond, thenBranch, elseBranch)
    }

    private fun parseWhileStmt(): WhileStmt {
        val loc = curr().loc
        consume(TokenType.WHILE, "Expected 'while'")
        val cond = parseExpr()
        val body = parseBlockStmt()
        return WhileStmt(loc, cond, body)
    }

    private fun parseForStmt(): ForStmt {
        val loc = curr().loc
        consume(TokenType.FOR, "Expected 'for'")
        val varName = consume(TokenType.IDENTIFIER, "Expected loop variable name").lexeme
        consume(TokenType.IN, "Expected 'in' after loop variable")
        val iterable = parseExpr()
        val body = parseBlockStmt()
        return ForStmt(loc, varName, iterable, body)
    }

    private fun parseReturnStmt(): ReturnStmt {
        val loc = curr().loc
        consume(TokenType.RETURN, "Expected 'return'")
        var value: ExprNode? = null
        if (!check(TokenType.SEMICOLON, TokenType.RBRACE, TokenType.EOF)) {
            value = parseExpr()
        }
        match(TokenType.SEMICOLON)
        return ReturnStmt(loc, value)
    }

    private fun parseDeferStmt(): DeferStmt {
        val loc = curr().loc
        consume(TokenType.DEFER, "Expected 'defer'")
        val body = if (check(TokenType.LBRACE)) {
            parseBlockStmt()
        } else {
            val stmt = parseStmt()
            BlockStmt(loc, mutableListOf(stmt))
        }
        return DeferStmt(loc, body)
    }

    // Expression Precedence Climbing
    private fun parseExpr(): ExprNode = parseOr()

    private fun parseOr(): ExprNode {
        var left = parseAnd()
        while (match(TokenType.OR)) {
            val right = parseAnd()
            left = BinaryExpr(left.loc, left, "||", right)
        }
        return left
    }

    private fun parseAnd(): ExprNode {
        var left = parseEquality()
        while (match(TokenType.AND)) {
            val right = parseEquality()
            left = BinaryExpr(left.loc, left, "&&", right)
        }
        return left
    }

    private fun parseEquality(): ExprNode {
        var left = parseRelational()
        while (check(TokenType.EQ, TokenType.NEQ)) {
            val op = advance().lexeme
            val right = parseRelational()
            left = BinaryExpr(left.loc, left, op, right)
        }
        return left
    }

    private fun parseRelational(): ExprNode {
        var left = parseRange()
        while (check(TokenType.LT, TokenType.LTE, TokenType.GT, TokenType.GTE)) {
            val op = advance().lexeme
            val right = parseRange()
            left = BinaryExpr(left.loc, left, op, right)
        }
        return left
    }

    private fun parseRange(): ExprNode {
        val left = parseAdditive()
        if (match(TokenType.RANGE)) {
            val right = parseAdditive()
            return RangeExpr(left.loc, left, right)
        }
        return left
    }

    private fun parseAdditive(): ExprNode {
        var left = parseMultiplicative()
        while (check(TokenType.PLUS, TokenType.MINUS)) {
            val op = advance().lexeme
            val right = parseMultiplicative()
            left = BinaryExpr(left.loc, left, op, right)
        }
        return left
    }

    private fun parseMultiplicative(): ExprNode {
        var left = parseUnary()
        while (check(TokenType.STAR, TokenType.SLASH, TokenType.PERCENT)) {
            val op = advance().lexeme
            val right = parseUnary()
            left = BinaryExpr(left.loc, left, op, right)
        }
        return left
    }

    private fun parseUnary(): ExprNode {
        val c = curr()
        if (c.type in listOf(TokenType.NOT, TokenType.MINUS)) {
            advance()
            val operand = parseUnary()
            return UnaryExpr(c.loc, c.lexeme, operand)
        }
        return parsePostfix()
    }

    private fun parsePostfix(): ExprNode {
        var expr = parsePrimary()

        while (true) {
            if (match(TokenType.LPAREN)) {
                val args = mutableListOf<ExprNode>()
                if (!check(TokenType.RPAREN)) {
                    while (true) {
                        args.add(parseExpr())
                        if (!match(TokenType.COMMA)) break
                    }
                }
                consume(TokenType.RPAREN, "Expected ')' after call arguments")
                expr = CallExpr(expr.loc, expr, args)
            } else if (match(TokenType.DOT)) {
                val memTok = consume(TokenType.IDENTIFIER, "Expected member name after '.'")
                expr = MemberAccessExpr(expr.loc, expr, memTok.lexeme)
            } else if (match(TokenType.LBRACKET)) {
                val idxExpr = parseExpr()
                consume(TokenType.RBRACKET, "Expected ']' after index")
                expr = IndexExpr(expr.loc, expr, idxExpr)
            } else {
                break
            }
        }
        return expr
    }

    private fun parsePrimary(): ExprNode {
        val c = curr()

        // Explicit new instantiation e.g. `owned File("log.txt")` or `shared Node(1)`
        if (c.type in listOf(TokenType.OWNED, TokenType.SHARED, TokenType.AUTOMATIC) && peek().type == TokenType.IDENTIFIER && peek(2).type == TokenType.LPAREN) {
            val ownership = OwnershipKind.fromString(advance().lexeme)
            val typeName = advance().lexeme
            consume(TokenType.LPAREN, "Expected '('")
            val args = mutableListOf<ExprNode>()
            if (!check(TokenType.RPAREN)) {
                while (true) {
                    args.add(parseExpr())
                    if (!match(TokenType.COMMA)) break
                }
            }
            consume(TokenType.RPAREN, "Expected ')'")
            return NewExpr(c.loc, typeName, args, ownership)
        }

        // weak(expr)
        if (c.type == TokenType.WEAK && peek().type == TokenType.LPAREN) {
            advance()
            consume(TokenType.LPAREN, "Expected '(' after 'weak'")
            val inner = parseExpr()
            consume(TokenType.RPAREN, "Expected ')'")
            return WeakRefExpr(c.loc, inner)
        }

        // new Type(args...)
        if (match(TokenType.NEW)) {
            var ownership = OwnershipKind.AUTOMATIC
            if (check(TokenType.OWNED, TokenType.SHARED, TokenType.AUTOMATIC)) {
                ownership = OwnershipKind.fromString(advance().lexeme)
            }
            val typeName = consume(TokenType.IDENTIFIER, "Expected type name after 'new'").lexeme
            consume(TokenType.LPAREN, "Expected '(' after type name")
            val args = mutableListOf<ExprNode>()
            if (!check(TokenType.RPAREN)) {
                while (true) {
                    args.add(parseExpr())
                    if (!match(TokenType.COMMA)) break
                }
            }
            consume(TokenType.RPAREN, "Expected ')'")
            return NewExpr(c.loc, typeName, args, ownership)
        }

        // Literals
        if (c.type == TokenType.INT_LIT) {
            advance()
            return LiteralExpr(c.loc, c.value, "Int")
        }
        if (c.type == TokenType.FLOAT_LIT) {
            advance()
            return LiteralExpr(c.loc, c.value, "Float")
        }
        if (c.type == TokenType.STRING_LIT) {
            advance()
            return LiteralExpr(c.loc, c.value, "String")
        }
        if (c.type == TokenType.BOOL_LIT) {
            advance()
            return LiteralExpr(c.loc, c.value, "Bool")
        }
        if (c.type == TokenType.NIL_LIT) {
            advance()
            return LiteralExpr(c.loc, null, "Nil")
        }

        // Identifiers & self
        if (c.type in listOf(TokenType.IDENTIFIER, TokenType.SELF)) {
            advance()
            return IdentifierExpr(c.loc, c.lexeme)
        }

        // Array literal [elem1, elem2]
        if (match(TokenType.LBRACKET)) {
            val elems = mutableListOf<ExprNode>()
            if (!check(TokenType.RBRACKET)) {
                while (true) {
                    elems.add(parseExpr())
                    if (!match(TokenType.COMMA)) break
                }
            }
            consume(TokenType.RBRACKET, "Expected ']' after array elements")
            return ArrayLiteralExpr(c.loc, elems)
        }

        // Grouping (expr)
        if (match(TokenType.LPAREN)) {
            val expr = parseExpr()
            consume(TokenType.RPAREN, "Expected ')' after expression")
            return expr
        }

        throw ParserException("Unexpected token: '${c.lexeme}' (${c.type})", c.loc)
    }
}
