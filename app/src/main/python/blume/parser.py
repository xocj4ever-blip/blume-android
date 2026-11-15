"""
Blume Programming Language - Parser
Version: 1.0
100% Pure Python Implementation
"""

from typing import List, Optional, Union
from blume.ast import (
    ASTNode, SourceLocation, ProgramNode, StmtNode, ExprNode, TypeNode,
    VarDeclStmt, AssignStmt, IfStmt, WhileStmt, ForStmt, ReturnStmt, DeferStmt,
    BlockStmt, ExprStmt, FuncDecl, StructDecl, ClassDecl, ParamNode, FieldNode,
    LiteralExpr, IdentifierExpr, BinaryExpr, UnaryExpr, CallExpr,
    MemberAccessExpr, IndexExpr, ArrayLiteralExpr, NewExpr, RangeExpr,
    WeakRefExpr, OwnershipKind
)
from blume.lexer import Token, TokenType, Lexer

class ParserError(Exception):
    def __init__(self, message: str, loc: SourceLocation):
        super().__init__(f"ParserError at {loc}: {message}")
        self.message = message
        self.loc = loc

class Parser:
    def __init__(self, tokens: List[Token]):
        self.tokens = tokens
        self.pos = 0

    def _curr(self) -> Token:
        if self.pos >= len(self.tokens):
            return self.tokens[-1]
        return self.tokens[self.pos]

    def _peek(self, offset: int = 1) -> Token:
        idx = self.pos + offset
        if idx >= len(self.tokens):
            return self.tokens[-1]
        return self.tokens[idx]

    def _check(self, *types: TokenType) -> bool:
        return self._curr().type in types

    def _advance(self) -> Token:
        tok = self._curr()
        if self.pos < len(self.tokens) - 1:
            self.pos += 1
        return tok

    def _match(self, *types: TokenType) -> bool:
        if self._check(*types):
            self._advance()
            return True
        return False

    def _consume(self, tok_type: TokenType, err_msg: str) -> Token:
        if self._check(tok_type):
            return self._advance()
        curr = self._curr()
        raise ParserError(f"{err_msg} (got {curr.type.name} {curr.lexeme!r})", curr.loc)

    # ---------------- Parsing Entry Point ----------------

    def parse(self) -> ProgramNode:
        loc = self._curr().loc
        decls: List[Union[FuncDecl, StructDecl, ClassDecl, StmtNode]] = []

        while not self._check(TokenType.EOF):
            # Skip stray semicolons
            if self._match(TokenType.SEMICOLON):
                continue
            decls.append(self._parse_top_level())

        return ProgramNode(loc=loc, declarations=decls)

    def _parse_top_level(self) -> Union[FuncDecl, StructDecl, ClassDecl, StmtNode]:
        curr = self._curr()

        # Check for class declaration with ownership modifier (e.g. `shared class Node` or `class Node`)
        if curr.type in (TokenType.OWNED, TokenType.SHARED, TokenType.AUTOMATIC) and self._peek().type == TokenType.CLASS:
            ownership_tok = self._advance()
            ownership = OwnershipKind.from_str(ownership_tok.lexeme)
            return self._parse_class_decl(ownership)

        if curr.type == TokenType.CLASS:
            return self._parse_class_decl(OwnershipKind.OWNED)

        if curr.type == TokenType.STRUCT:
            return self._parse_struct_decl()

        if curr.type == TokenType.FN:
            return self._parse_func_decl()

        # Otherwise, parse top-level statement (support scripting / main code)
        return self._parse_stmt()

    # ---------------- Type Parsing ----------------

    def _parse_type(self) -> TypeNode:
        loc = self._curr().loc
        ownership = OwnershipKind.AUTOMATIC

        if self._check(TokenType.OWNED, TokenType.SHARED, TokenType.WEAK, TokenType.UNOWNED, TokenType.AUTOMATIC):
            ownership = OwnershipKind.from_str(self._advance().lexeme)

        name_tok = self._consume(TokenType.IDENTIFIER, "Expected type name")
        type_name = name_tok.lexeme

        generic_args: List[TypeNode] = []
        if self._match(TokenType.LBRACKET):
            while not self._check(TokenType.RBRACKET, TokenType.EOF):
                generic_args.append(self._parse_type())
                if not self._match(TokenType.COMMA):
                    break
            self._consume(TokenType.RBRACKET, "Expected ']' after generic type arguments")

        is_optional = self._match(TokenType.QUESTION)

        return TypeNode(
            loc=loc,
            name=type_name,
            ownership=ownership,
            is_optional=is_optional,
            generic_args=generic_args
        )

    # ---------------- Declarations ----------------

    def _parse_func_decl(self, is_method: bool = False) -> FuncDecl:
        loc = self._curr().loc
        self._consume(TokenType.FN, "Expected 'fn'")
        name_tok = self._consume(TokenType.IDENTIFIER, "Expected function name")
        name = name_tok.lexeme

        self._consume(TokenType.LPAREN, "Expected '(' after function name")
        params: List[ParamNode] = []
        if not self._check(TokenType.RPAREN):
            while True:
                p_loc = self._curr().loc
                p_ownership = OwnershipKind.AUTOMATIC
                if self._check(TokenType.OWNED, TokenType.SHARED, TokenType.WEAK, TokenType.UNOWNED):
                    p_ownership = OwnershipKind.from_str(self._advance().lexeme)

                p_name_tok = self._consume(TokenType.IDENTIFIER, "Expected parameter name")
                self._consume(TokenType.COLON, "Expected ':' after parameter name")
                p_type = self._parse_type()
                if p_ownership == OwnershipKind.AUTOMATIC:
                    p_ownership = p_type.ownership

                params.append(ParamNode(
                    loc=p_loc,
                    name=p_name_tok.lexeme,
                    type_annotation=p_type,
                    ownership=p_ownership
                ))

                if not self._match(TokenType.COMMA):
                    break

        self._consume(TokenType.RPAREN, "Expected ')' after parameters")

        return_type = TypeNode(loc=loc, name="Void")
        if self._match(TokenType.ARROW):
            return_type = self._parse_type()

        body = self._parse_block_stmt()
        return FuncDecl(
            loc=loc,
            name=name,
            params=params,
            return_type=return_type,
            body=body,
            is_method=is_method
        )

    def _parse_struct_decl(self) -> StructDecl:
        loc = self._curr().loc
        self._consume(TokenType.STRUCT, "Expected 'struct'")
        name_tok = self._consume(TokenType.IDENTIFIER, "Expected struct name")
        self._consume(TokenType.LBRACE, "Expected '{' before struct body")

        fields: List[FieldNode] = []
        while not self._check(TokenType.RBRACE, TokenType.EOF):
            if self._match(TokenType.SEMICOLON):
                continue
            is_var = self._match(TokenType.VAR)
            is_let = self._match(TokenType.LET)
            f_loc = self._curr().loc
            f_name_tok = self._consume(TokenType.IDENTIFIER, "Expected field name")
            self._consume(TokenType.COLON, "Expected ':' after field name")
            f_type = self._parse_type()
            init_expr = None
            if self._match(TokenType.ASSIGN):
                init_expr = self._parse_expr()
            self._match(TokenType.SEMICOLON)
            fields.append(FieldNode(loc=f_loc, name=f_name_tok.lexeme, type_annotation=f_type, initializer=init_expr))

        self._consume(TokenType.RBRACE, "Expected '}' after struct body")
        return StructDecl(loc=loc, name=name_tok.lexeme, fields=fields)

    def _parse_class_decl(self, default_ownership: OwnershipKind) -> ClassDecl:
        loc = self._curr().loc
        self._consume(TokenType.CLASS, "Expected 'class'")
        name_tok = self._consume(TokenType.IDENTIFIER, "Expected class name")
        self._consume(TokenType.LBRACE, "Expected '{' before class body")

        fields: List[FieldNode] = []
        init_method: Optional[FuncDecl] = None
        deinit_method: Optional[BlockStmt] = None
        methods: List[FuncDecl] = []

        while not self._check(TokenType.RBRACE, TokenType.EOF):
            if self._match(TokenType.SEMICOLON):
                continue

            # Field declaration: `var name: Type` or `let name: Type` or `weak var parent: Node?`
            if self._check(TokenType.VAR, TokenType.LET, TokenType.WEAK, TokenType.UNOWNED, TokenType.OWNED, TokenType.SHARED):
                field_ownership = OwnershipKind.AUTOMATIC
                if self._check(TokenType.WEAK, TokenType.UNOWNED, TokenType.OWNED, TokenType.SHARED):
                    field_ownership = OwnershipKind.from_str(self._advance().lexeme)

                is_var = self._match(TokenType.VAR)
                if not is_var:
                    self._consume(TokenType.LET, "Expected 'var' or 'let' in field declaration")

                f_loc = self._curr().loc
                f_name_tok = self._consume(TokenType.IDENTIFIER, "Expected field name")
                self._consume(TokenType.COLON, "Expected ':' after field name")
                f_type = self._parse_type()
                if field_ownership != OwnershipKind.AUTOMATIC:
                    f_type.ownership = field_ownership
                else:
                    field_ownership = f_type.ownership

                init_expr = None
                if self._match(TokenType.ASSIGN):
                    init_expr = self._parse_expr()
                self._match(TokenType.SEMICOLON)
                fields.append(FieldNode(
                    loc=f_loc,
                    name=f_name_tok.lexeme,
                    type_annotation=f_type,
                    ownership=field_ownership,
                    initializer=init_expr
                ))
            elif self._check(TokenType.INIT):
                # Constructor: `init(params...) { ... }`
                init_loc = self._advance().loc
                self._consume(TokenType.LPAREN, "Expected '(' after 'init'")
                params: List[ParamNode] = []
                if not self._check(TokenType.RPAREN):
                    while True:
                        p_loc = self._curr().loc
                        p_name = self._consume(TokenType.IDENTIFIER, "Expected parameter name").lexeme
                        self._consume(TokenType.COLON, "Expected ':' after parameter name")
                        p_type = self._parse_type()
                        params.append(ParamNode(loc=p_loc, name=p_name, type_annotation=p_type, ownership=p_type.ownership))
                        if not self._match(TokenType.COMMA):
                            break
                self._consume(TokenType.RPAREN, "Expected ')' after init parameters")
                body = self._parse_block_stmt()
                init_method = FuncDecl(
                    loc=init_loc,
                    name="init",
                    params=params,
                    return_type=TypeNode(loc=init_loc, name="Void"),
                    body=body,
                    is_method=True
                )
            elif self._check(TokenType.DEINIT):
                # Destructor: `deinit { ... }`
                deinit_loc = self._advance().loc
                deinit_body = self._parse_block_stmt()
                deinit_method = deinit_body
            elif self._check(TokenType.FN):
                # Method
                method = self._parse_func_decl(is_method=True)
                methods.append(method)
            else:
                curr = self._curr()
                raise ParserError(f"Unexpected token in class body: {curr.lexeme!r}", curr.loc)

        self._consume(TokenType.RBRACE, "Expected '}' after class body")
        return ClassDecl(
            loc=loc,
            name=name_tok.lexeme,
            default_ownership=default_ownership,
            fields=fields,
            init_method=init_method,
            deinit_method=deinit_method,
            methods=methods
        )

    # ---------------- Statements ----------------

    def _parse_stmt(self) -> StmtNode:
        if self._check(TokenType.LBRACE):
            return self._parse_block_stmt()
        if self._check(TokenType.LET, TokenType.VAR, TokenType.OWNED, TokenType.SHARED, TokenType.WEAK, TokenType.UNOWNED, TokenType.AUTOMATIC):
            # Check if this is a variable declaration with ownership prefix e.g. `owned let x = ...`
            if self._curr().type in (TokenType.OWNED, TokenType.SHARED, TokenType.WEAK, TokenType.UNOWNED, TokenType.AUTOMATIC):
                if self._peek().type in (TokenType.LET, TokenType.VAR):
                    return self._parse_var_decl()
            elif self._curr().type in (TokenType.LET, TokenType.VAR):
                return self._parse_var_decl()

        if self._check(TokenType.IF):
            return self._parse_if_stmt()
        if self._check(TokenType.WHILE):
            return self._parse_while_stmt()
        if self._check(TokenType.FOR):
            return self._parse_for_stmt()
        if self._check(TokenType.RETURN):
            return self._parse_return_stmt()
        if self._check(TokenType.DEFER):
            return self._parse_defer_stmt()

        # Expression statement or assignment
        expr = self._parse_expr()

        # Check for assignment
        if self._check(TokenType.ASSIGN, TokenType.PLUS_ASSIGN, TokenType.MINUS_ASSIGN, TokenType.STAR_ASSIGN, TokenType.SLASH_ASSIGN):
            op_tok = self._advance()
            val_expr = self._parse_expr()
            if op_tok.type != TokenType.ASSIGN:
                # desugar +=, -=, etc.
                bin_op = op_tok.lexeme[0]
                val_expr = BinaryExpr(loc=op_tok.loc, left=expr, op=bin_op, right=val_expr)
            self._match(TokenType.SEMICOLON)
            return AssignStmt(loc=expr.loc, target=expr, value=val_expr)

        self._match(TokenType.SEMICOLON)
        return ExprStmt(loc=expr.loc, expr=expr)

    def _parse_block_stmt(self) -> BlockStmt:
        loc = self._curr().loc
        self._consume(TokenType.LBRACE, "Expected '{'")
        stmts: List[StmtNode] = []
        while not self._check(TokenType.RBRACE, TokenType.EOF):
            if self._match(TokenType.SEMICOLON):
                continue
            stmts.append(self._parse_stmt())
        self._consume(TokenType.RBRACE, "Expected '}'")
        return BlockStmt(loc=loc, statements=stmts)

    def _parse_var_decl(self) -> VarDeclStmt:
        loc = self._curr().loc
        ownership = OwnershipKind.AUTOMATIC
        if self._check(TokenType.OWNED, TokenType.SHARED, TokenType.WEAK, TokenType.UNOWNED, TokenType.AUTOMATIC):
            ownership = OwnershipKind.from_str(self._advance().lexeme)

        is_mut = False
        if self._match(TokenType.VAR):
            is_mut = True
        else:
            self._consume(TokenType.LET, "Expected 'let' or 'var'")

        name_tok = self._consume(TokenType.IDENTIFIER, "Expected variable name")
        name = name_tok.lexeme

        type_annotation = None
        if self._match(TokenType.COLON):
            type_annotation = self._parse_type()
            if ownership == OwnershipKind.AUTOMATIC:
                ownership = type_annotation.ownership

        initializer = None
        if self._match(TokenType.ASSIGN):
            initializer = self._parse_expr()

        self._match(TokenType.SEMICOLON)
        return VarDeclStmt(
            loc=loc,
            name=name,
            is_mutable=is_mut,
            ownership=ownership,
            type_annotation=type_annotation,
            initializer=initializer
        )

    def _parse_if_stmt(self) -> IfStmt:
        loc = self._curr().loc
        self._consume(TokenType.IF, "Expected 'if'")
        cond = self._parse_expr()
        then_block = self._parse_block_stmt()
        else_block = None

        if self._match(TokenType.ELSE):
            if self._check(TokenType.IF):
                # else if -> wrap in block
                else_if_stmt = self._parse_if_stmt()
                else_block = BlockStmt(loc=else_if_stmt.loc, statements=[else_if_stmt])
            else:
                else_block = self._parse_block_stmt()

        return IfStmt(loc=loc, condition=cond, then_branch=then_block, else_branch=else_block)

    def _parse_while_stmt(self) -> WhileStmt:
        loc = self._curr().loc
        self._consume(TokenType.WHILE, "Expected 'while'")
        cond = self._parse_expr()
        body = self._parse_block_stmt()
        return WhileStmt(loc=loc, condition=cond, body=body)

    def _parse_for_stmt(self) -> ForStmt:
        loc = self._curr().loc
        self._consume(TokenType.FOR, "Expected 'for'")
        var_name = self._consume(TokenType.IDENTIFIER, "Expected loop variable name").lexeme
        self._consume(TokenType.IN, "Expected 'in' after loop variable")
        iterable = self._parse_expr()
        body = self._parse_block_stmt()
        return ForStmt(loc=loc, var_name=var_name, iterable=iterable, body=body)

    def _parse_return_stmt(self) -> ReturnStmt:
        loc = self._curr().loc
        self._consume(TokenType.RETURN, "Expected 'return'")
        val = None
        if not self._check(TokenType.SEMICOLON, TokenType.RBRACE, TokenType.EOF):
            val = self._parse_expr()
        self._match(TokenType.SEMICOLON)
        return ReturnStmt(loc=loc, value=val)

    def _parse_defer_stmt(self) -> DeferStmt:
        loc = self._curr().loc
        self._consume(TokenType.DEFER, "Expected 'defer'")
        if self._check(TokenType.LBRACE):
            body = self._parse_block_stmt()
        else:
            stmt = self._parse_stmt()
            body = BlockStmt(loc=loc, statements=[stmt])
        return DeferStmt(loc=loc, body=body)

    # ---------------- Expressions (Pratt / Precedence Climbing) ----------------

    def _parse_expr(self) -> ExprNode:
        return self._parse_or()

    def _parse_or(self) -> ExprNode:
        left = self._parse_and()
        while self._match(TokenType.OR):
            op = "||"
            right = self._parse_and()
            left = BinaryExpr(loc=left.loc, left=left, op=op, right=right)
        return left

    def _parse_and(self) -> ExprNode:
        left = self._parse_equality()
        while self._match(TokenType.AND):
            op = "&&"
            right = self._parse_equality()
            left = BinaryExpr(loc=left.loc, left=left, op=op, right=right)
        return left

    def _parse_equality(self) -> ExprNode:
        left = self._parse_relational()
        while self._check(TokenType.EQ, TokenType.NEQ):
            op = self._advance().lexeme
            right = self._parse_relational()
            left = BinaryExpr(loc=left.loc, left=left, op=op, right=right)
        return left

    def _parse_relational(self) -> ExprNode:
        left = self._parse_range()
        while self._check(TokenType.LT, TokenType.LTE, TokenType.GT, TokenType.GTE):
            op = self._advance().lexeme
            right = self._parse_range()
            left = BinaryExpr(loc=left.loc, left=left, op=op, right=right)
        return left

    def _parse_range(self) -> ExprNode:
        left = self._parse_additive()
        if self._match(TokenType.RANGE):
            right = self._parse_additive()
            return RangeExpr(loc=left.loc, start=left, end=right)
        return left

    def _parse_additive(self) -> ExprNode:
        left = self._parse_multiplicative()
        while self._check(TokenType.PLUS, TokenType.MINUS):
            op = self._advance().lexeme
            right = self._parse_multiplicative()
            left = BinaryExpr(loc=left.loc, left=left, op=op, right=right)
        return left

    def _parse_multiplicative(self) -> ExprNode:
        left = self._parse_unary()
        while self._check(TokenType.STAR, TokenType.SLASH, TokenType.PERCENT):
            op = self._advance().lexeme
            right = self._parse_unary()
            left = BinaryExpr(loc=left.loc, left=left, op=op, right=right)
        return left

    def _parse_unary(self) -> ExprNode:
        curr = self._curr()
        if curr.type in (TokenType.NOT, TokenType.MINUS):
            self._advance()
            operand = self._parse_unary()
            return UnaryExpr(loc=curr.loc, op=curr.lexeme, operand=operand)
        return self._parse_postfix()

    def _parse_postfix(self) -> ExprNode:
        expr = self._parse_primary()

        while True:
            if self._match(TokenType.LPAREN):
                # Call expression: expr(arg1, arg2)
                args: List[ExprNode] = []
                if not self._check(TokenType.RPAREN):
                    while True:
                        args.append(self._parse_expr())
                        if not self._match(TokenType.COMMA):
                            break
                self._consume(TokenType.RPAREN, "Expected ')' after call arguments")
                expr = CallExpr(loc=expr.loc, callee=expr, args=args)
            elif self._match(TokenType.DOT):
                # Member access: expr.member
                mem_tok = self._consume(TokenType.IDENTIFIER, "Expected member name after '.'")
                expr = MemberAccessExpr(loc=expr.loc, obj=expr, member=mem_tok.lexeme)
            elif self._match(TokenType.LBRACKET):
                # Array index: expr[index]
                idx_expr = self._parse_expr()
                self._consume(TokenType.RBRACKET, "Expected ']' after index")
                expr = IndexExpr(loc=expr.loc, target=expr, index=idx_expr)
            else:
                break

        return expr

    def _parse_primary(self) -> ExprNode:
        curr = self._curr()

        # Explicit object instantiation with ownership prefix:
        # e.g. `owned File("log.txt")` or `shared Node(1)`
        if curr.type in (TokenType.OWNED, TokenType.SHARED, TokenType.AUTOMATIC) and self._peek().type == TokenType.IDENTIFIER:
            # Check if followed by identifier and '('
            if self._peek(2).type == TokenType.LPAREN:
                ownership = OwnershipKind.from_str(self._advance().lexeme)
                type_name = self._advance().lexeme
                self._consume(TokenType.LPAREN, "Expected '('")
                args: List[ExprNode] = []
                if not self._check(TokenType.RPAREN):
                    while True:
                        args.append(self._parse_expr())
                        if not self._match(TokenType.COMMA):
                            break
                self._consume(TokenType.RPAREN, "Expected ')'")
                return NewExpr(loc=curr.loc, type_name=type_name, args=args, ownership=ownership)

        # Keyword `weak`: `weak(expr)`
        if curr.type == TokenType.WEAK and self._peek().type == TokenType.LPAREN:
            self._advance()
            self._consume(TokenType.LPAREN, "Expected '(' after 'weak'")
            inner = self._parse_expr()
            self._consume(TokenType.RPAREN, "Expected ')'")
            return WeakRefExpr(loc=curr.loc, expr=inner)

        # Keyword `new`: `new Type(args...)` or `new owned Type(args...)`
        if self._match(TokenType.NEW):
            ownership = OwnershipKind.AUTOMATIC
            if self._check(TokenType.OWNED, TokenType.SHARED, TokenType.AUTOMATIC):
                ownership = OwnershipKind.from_str(self._advance().lexeme)
            type_name = self._consume(TokenType.IDENTIFIER, "Expected type name after 'new'").lexeme
            self._consume(TokenType.LPAREN, "Expected '(' after type name")
            args = []
            if not self._check(TokenType.RPAREN):
                while True:
                    args.append(self._parse_expr())
                    if not self._match(TokenType.COMMA):
                        break
            self._consume(TokenType.RPAREN, "Expected ')'")
            return NewExpr(loc=curr.loc, type_name=type_name, args=args, ownership=ownership)

        # Literals
        if curr.type == TokenType.INT_LIT:
            self._advance()
            return LiteralExpr(loc=curr.loc, value=curr.value, type_name="Int")
        if curr.type == TokenType.FLOAT_LIT:
            self._advance()
            return LiteralExpr(loc=curr.loc, value=curr.value, type_name="Float")
        if curr.type == TokenType.STRING_LIT:
            self._advance()
            return LiteralExpr(loc=curr.loc, value=curr.value, type_name="String")
        if curr.type == TokenType.BOOL_LIT:
            self._advance()
            return LiteralExpr(loc=curr.loc, value=curr.value, type_name="Bool")
        if curr.type == TokenType.NIL_LIT:
            self._advance()
            return LiteralExpr(loc=curr.loc, value=None, type_name="Nil")

        # Identifier / Self
        if curr.type in (TokenType.IDENTIFIER, TokenType.SELF):
            self._advance()
            return IdentifierExpr(loc=curr.loc, name=curr.lexeme)

        # Array literal: `[elem1, elem2, ...]`
        if self._match(TokenType.LBRACKET):
            elements: List[ExprNode] = []
            if not self._check(TokenType.RBRACKET):
                while True:
                    elements.append(self._parse_expr())
                    if not self._match(TokenType.COMMA):
                        break
            self._consume(TokenType.RBRACKET, "Expected ']' after array elements")
            return ArrayLiteralExpr(loc=curr.loc, elements=elements)

        # Parenthesized expression: `(expr)`
        if self._match(TokenType.LPAREN):
            inner = self._parse_expr()
            self._consume(TokenType.RPAREN, "Expected ')'")
            return inner

        raise ParserError(f"Unexpected token in expression: {curr.type.name} {curr.lexeme!r}", curr.loc)
