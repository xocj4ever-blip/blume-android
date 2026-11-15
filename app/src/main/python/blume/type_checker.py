"""
Blume Programming Language - Type Checker & Semantic Analyzer
Version: 1.0
100% Pure Python Implementation
"""

from typing import Dict, List, Optional, Set, Any
from blume.ast import (
    ProgramNode, FuncDecl, StructDecl, ClassDecl, StmtNode, ExprNode,
    TypeNode, VarDeclStmt, AssignStmt, IfStmt, WhileStmt, ForStmt,
    ReturnStmt, DeferStmt, BlockStmt, ExprStmt, LiteralExpr, IdentifierExpr,
    BinaryExpr, UnaryExpr, CallExpr, MemberAccessExpr, IndexExpr,
    ArrayLiteralExpr, NewExpr, RangeExpr, WeakRefExpr, OwnershipKind,
    SourceLocation
)
from blume.types import (
    Type, PrimitiveType, TYPE_INT, TYPE_FLOAT, TYPE_BOOL, TYPE_STRING,
    TYPE_VOID, TYPE_NIL, OptionalType, ArrayType, StructType, ClassType,
    WeakType, UnownedType, FunctionType
)

class TypeError(Exception):
    def __init__(self, message: str, loc: SourceLocation):
        super().__init__(f"TypeError at {loc}: {message}")
        self.message = message
        self.loc = loc

class SymbolScope:
    def __init__(self, parent: Optional["SymbolScope"] = None):
        self.parent = parent
        self.symbols: Dict[str, Type] = {}
        self.ownerships: Dict[str, OwnershipKind] = {}
        self.is_mutables: Dict[str, bool] = {}

    def define(self, name: str, typ: Type, ownership: OwnershipKind = OwnershipKind.AUTOMATIC, is_mutable: bool = False):
        self.symbols[name] = typ
        self.ownerships[name] = ownership
        self.is_mutables[name] = is_mutable

    def lookup(self, name: str) -> Optional[Type]:
        if name in self.symbols:
            return self.symbols[name]
        if self.parent:
            return self.parent.lookup(name)
        return None

    def lookup_ownership(self, name: str) -> OwnershipKind:
        if name in self.ownerships:
            return self.ownerships[name]
        if self.parent:
            return self.parent.lookup_ownership(name)
        return OwnershipKind.AUTOMATIC

    def lookup_is_mutable(self, name: str) -> bool:
        if name in self.is_mutables:
            return self.is_mutables[name]
        if self.parent:
            return self.parent.lookup_is_mutable(name)
        return True

class TypeChecker:
    def __init__(self):
        self.global_types: Dict[str, Type] = {
            "Int": TYPE_INT,
            "Float": TYPE_FLOAT,
            "Bool": TYPE_BOOL,
            "String": TYPE_STRING,
            "Void": TYPE_VOID,
        }
        self.global_scope = SymbolScope()
        self.current_scope = self.global_scope
        self.current_return_type: Optional[Type] = None
        self.current_class: Optional[ClassType] = None

        self._init_builtins()

    def _init_builtins(self):
        # Built-in functions
        self.global_scope.define("print", FunctionType([TYPE_STRING], TYPE_VOID))
        self.global_scope.define("println", FunctionType([TYPE_STRING], TYPE_VOID))
        self.global_scope.define("blume_retain_count", FunctionType([TYPE_VOID], TYPE_INT))
        self.global_scope.define("blume_memory_domain", FunctionType([TYPE_VOID], TYPE_STRING))
        self.global_scope.define("blume_gc_collect", FunctionType([], TYPE_INT))
        self.global_scope.define("blume_heap_stats", FunctionType([], TYPE_VOID))
        self.global_scope.define("assert", FunctionType([TYPE_BOOL, TYPE_STRING], TYPE_VOID))

    def resolve_type_node(self, node: Optional[TypeNode]) -> Type:
        if node is None:
            return TYPE_VOID

        base_name = node.name
        if base_name in self.global_types:
            t = self.global_types[base_name]
        elif base_name == "Array" and node.generic_args:
            elem_t = self.resolve_type_node(node.generic_args[0])
            t = ArrayType(element_type=elem_t)
        else:
            raise TypeError(f"Unknown type '{base_name}'", node.loc)

        if node.is_optional:
            t = OptionalType(inner=t)

        if node.ownership == OwnershipKind.WEAK:
            t = WeakType(inner=t)
        elif node.ownership == OwnershipKind.UNOWNED:
            t = UnownedType(inner=t)

        return t

    def check_program(self, program: ProgramNode):
        # Pass 1: Declare struct and class types
        for decl in program.declarations:
            if isinstance(decl, StructDecl):
                struct_type = StructType(name=decl.name)
                self.global_types[decl.name] = struct_type
            elif isinstance(decl, ClassDecl):
                class_type = ClassType(name=decl.name, ownership=decl.default_ownership)
                self.global_types[decl.name] = class_type

        # Pass 2: Populate struct and class fields and methods
        for decl in program.declarations:
            if isinstance(decl, StructDecl):
                struct_t = self.global_types[decl.name]
                assert isinstance(struct_t, StructType)
                for f in decl.fields:
                    f_type = self.resolve_type_node(f.type_annotation)
                    struct_t.fields[f.name] = f_type
            elif isinstance(decl, ClassDecl):
                class_t = self.global_types[decl.name]
                assert isinstance(class_t, ClassType)
                class_t.has_deinit = (decl.deinit_method is not None)
                for f in decl.fields:
                    f_type = self.resolve_type_node(f.type_annotation)
                    class_t.fields[f.name] = f_type
                    class_t.field_ownership[f.name] = f.ownership

                # Init method
                class_t.has_explicit_init = (decl.init_method is not None)
                if decl.init_method:
                    p_types = [self.resolve_type_node(p.type_annotation) for p in decl.init_method.params]
                    init_fn_t = FunctionType(param_types=p_types, return_type=class_t)
                    class_t.methods["init"] = init_fn_t
                else:
                    # Default constructor taking fields or empty
                    p_types = list(class_t.fields.values())
                    class_t.methods["init"] = FunctionType(param_types=p_types, return_type=class_t)

                for m in decl.methods:
                    p_types = [self.resolve_type_node(p.type_annotation) for p in m.params]
                    ret_t = self.resolve_type_node(m.return_type)
                    class_t.methods[m.name] = FunctionType(param_types=p_types, return_type=ret_t)

        # Pass 3: Register global functions
        for decl in program.declarations:
            if isinstance(decl, FuncDecl):
                p_types = [self.resolve_type_node(p.type_annotation) for p in decl.params]
                ret_t = self.resolve_type_node(decl.return_type)
                fn_t = FunctionType(param_types=p_types, return_type=ret_t)
                self.global_scope.define(decl.name, fn_t)

        # Pass 4: Type-check bodies of functions, classes, and top-level statements
        for decl in program.declarations:
            if isinstance(decl, FuncDecl):
                self._check_func_decl(decl)
            elif isinstance(decl, ClassDecl):
                self._check_class_decl(decl)
            elif isinstance(decl, StmtNode):
                self._check_stmt(decl)

    def _check_func_decl(self, decl: FuncDecl):
        fn_type = self.global_scope.lookup(decl.name)
        assert isinstance(fn_type, FunctionType)

        prev_scope = self.current_scope
        prev_ret = self.current_return_type
        self.current_scope = SymbolScope(parent=self.global_scope)
        self.current_return_type = fn_type.return_type

        # Bind params
        for i, param in enumerate(decl.params):
            p_type = fn_type.param_types[i]
            self.current_scope.define(param.name, p_type, ownership=param.ownership, is_mutable=False)

        for stmt in decl.body.statements:
            self._check_stmt(stmt)

        self.current_scope = prev_scope
        self.current_return_type = prev_ret

    def _check_class_decl(self, decl: ClassDecl):
        class_t = self.global_types[decl.name]
        assert isinstance(class_t, ClassType)
        prev_class = self.current_class
        self.current_class = class_t

        # Check constructor
        if decl.init_method:
            prev_scope = self.current_scope
            prev_ret = self.current_return_type
            self.current_scope = SymbolScope(parent=self.global_scope)
            self.current_scope.define("self", class_t, is_mutable=True)
            self.current_return_type = TYPE_VOID

            for p in decl.init_method.params:
                p_type = self.resolve_type_node(p.type_annotation)
                self.current_scope.define(p.name, p_type, is_mutable=False)

            for stmt in decl.init_method.body.statements:
                self._check_stmt(stmt)

            self.current_scope = prev_scope
            self.current_return_type = prev_ret

        # Check deinit
        if decl.deinit_method:
            prev_scope = self.current_scope
            self.current_scope = SymbolScope(parent=self.global_scope)
            self.current_scope.define("self", class_t, is_mutable=False)
            for stmt in decl.deinit_method.statements:
                self._check_stmt(stmt)
            self.current_scope = prev_scope

        # Check methods
        for m in decl.methods:
            m_type = class_t.methods[m.name]
            prev_scope = self.current_scope
            prev_ret = self.current_return_type
            self.current_scope = SymbolScope(parent=self.global_scope)
            self.current_scope.define("self", class_t, is_mutable=True)
            self.current_return_type = m_type.return_type

            for i, p in enumerate(m.params):
                p_type = m_type.param_types[i]
                self.current_scope.define(p.name, p_type, is_mutable=False)

            for stmt in m.body.statements:
                self._check_stmt(stmt)

            self.current_scope = prev_scope
            self.current_return_type = prev_ret

        self.current_class = prev_class

    def _check_stmt(self, stmt: StmtNode):
        if isinstance(stmt, BlockStmt):
            prev_scope = self.current_scope
            self.current_scope = SymbolScope(parent=prev_scope)
            for s in stmt.statements:
                self._check_stmt(s)
            self.current_scope = prev_scope

        elif isinstance(stmt, VarDeclStmt):
            init_type = None
            if stmt.initializer:
                init_type = self._check_expr(stmt.initializer)

            annotated_type = None
            if stmt.type_annotation:
                annotated_type = self.resolve_type_node(stmt.type_annotation)

            if annotated_type and init_type:
                if not init_type.can_assign_to(annotated_type):
                    raise TypeError(
                        f"Cannot assign value of type '{init_type}' to variable '{stmt.name}' of type '{annotated_type}'",
                        stmt.loc
                    )
                var_type = annotated_type
            elif annotated_type:
                var_type = annotated_type
            elif init_type:
                var_type = init_type
            else:
                raise TypeError(f"Variable '{stmt.name}' must have a type annotation or an initializer", stmt.loc)

            ownership = stmt.ownership
            if ownership == OwnershipKind.AUTOMATIC:
                if isinstance(var_type, ClassType):
                    ownership = var_type.ownership
                elif isinstance(var_type, WeakType):
                    ownership = OwnershipKind.WEAK
                elif isinstance(var_type, UnownedType):
                    ownership = OwnershipKind.UNOWNED

            self.current_scope.define(stmt.name, var_type, ownership=ownership, is_mutable=stmt.is_mutable)

        elif isinstance(stmt, AssignStmt):
            target_type = self._check_expr(stmt.target)
            val_type = self._check_expr(stmt.value)

            # Check mutability if target is an identifier
            if isinstance(stmt.target, IdentifierExpr):
                if not self.current_scope.lookup_is_mutable(stmt.target.name):
                    raise TypeError(f"Cannot reassign immutable variable '{stmt.target.name}'", stmt.loc)

            if not val_type.can_assign_to(target_type):
                raise TypeError(
                    f"Cannot assign value of type '{val_type}' to target of type '{target_type}'",
                    stmt.loc
                )

        elif isinstance(stmt, IfStmt):
            cond_t = self._check_expr(stmt.condition)
            if cond_t != TYPE_BOOL:
                raise TypeError(f"If condition must be Bool, got '{cond_t}'", stmt.loc)
            self._check_stmt(stmt.then_branch)
            if stmt.else_branch:
                self._check_stmt(stmt.else_branch)

        elif isinstance(stmt, WhileStmt):
            cond_t = self._check_expr(stmt.condition)
            if cond_t != TYPE_BOOL:
                raise TypeError(f"While condition must be Bool, got '{cond_t}'", stmt.loc)
            self._check_stmt(stmt.body)

        elif isinstance(stmt, ForStmt):
            iter_t = self._check_expr(stmt.iterable)
            prev_scope = self.current_scope
            self.current_scope = SymbolScope(parent=prev_scope)

            elem_t: Type = TYPE_INT
            if isinstance(iter_t, ArrayType):
                elem_t = iter_t.element_type
            elif iter_t == TYPE_INT:
                # range iteration
                elem_t = TYPE_INT
            else:
                raise TypeError(f"For loop expects Array or Range, got '{iter_t}'", stmt.loc)

            self.current_scope.define(stmt.var_name, elem_t, is_mutable=False)
            for s in stmt.body.statements:
                self._check_stmt(s)
            self.current_scope = prev_scope

        elif isinstance(stmt, ReturnStmt):
            val_t = TYPE_VOID
            if stmt.value:
                val_t = self._check_expr(stmt.value)
            if self.current_return_type is not None:
                if not val_t.can_assign_to(self.current_return_type):
                    raise TypeError(
                        f"Function expects return type '{self.current_return_type}', got '{val_t}'",
                        stmt.loc
                    )

        elif isinstance(stmt, DeferStmt):
            self._check_stmt(stmt.body)

        elif isinstance(stmt, ExprStmt):
            self._check_expr(stmt.expr)

    def _check_expr(self, expr: ExprNode) -> Type:
        t = self._infer_expr(expr)
        expr.inferred_type = t
        return t

    def _infer_expr(self, expr: ExprNode) -> Type:
        if isinstance(expr, LiteralExpr):
            if expr.type_name == "Int":
                return TYPE_INT
            elif expr.type_name == "Float":
                return TYPE_FLOAT
            elif expr.type_name == "String":
                return TYPE_STRING
            elif expr.type_name == "Bool":
                return TYPE_BOOL
            elif expr.type_name == "Nil":
                return TYPE_NIL
            return TYPE_VOID

        elif isinstance(expr, IdentifierExpr):
            if expr.name == "self" and self.current_class:
                return self.current_class
            typ = self.current_scope.lookup(expr.name)
            if typ is None:
                # Check if it's a class/struct constructor reference
                if expr.name in self.global_types:
                    t = self.global_types[expr.name]
                    return t
                raise TypeError(f"Undefined identifier '{expr.name}'", expr.loc)
            return typ

        elif isinstance(expr, BinaryExpr):
            lt = self._check_expr(expr.left)
            rt = self._check_expr(expr.right)

            if expr.op in ("+", "-", "*", "/", "%"):
                if lt == TYPE_INT and rt == TYPE_INT:
                    return TYPE_INT
                if lt in (TYPE_INT, TYPE_FLOAT) and rt in (TYPE_INT, TYPE_FLOAT):
                    return TYPE_FLOAT
                if expr.op == "+" and (lt == TYPE_STRING or rt == TYPE_STRING):
                    return TYPE_STRING
                raise TypeError(f"Operator '{expr.op}' not supported for types '{lt}' and '{rt}'", expr.loc)

            elif expr.op in ("==", "!="):
                return TYPE_BOOL

            elif expr.op in ("<", "<=", ">", ">="):
                if (lt in (TYPE_INT, TYPE_FLOAT) and rt in (TYPE_INT, TYPE_FLOAT)) or (lt == TYPE_STRING and rt == TYPE_STRING):
                    return TYPE_BOOL
                raise TypeError(f"Relational operator '{expr.op}' not supported for '{lt}' and '{rt}'", expr.loc)

            elif expr.op in ("&&", "||"):
                if lt == TYPE_BOOL and rt == TYPE_BOOL:
                    return TYPE_BOOL
                raise TypeError(f"Logical operator '{expr.op}' expects Bool operands, got '{lt}' and '{rt}'", expr.loc)

            raise TypeError(f"Unknown binary operator '{expr.op}'", expr.loc)

        elif isinstance(expr, UnaryExpr):
            op_t = self._check_expr(expr.operand)
            if expr.op == "-":
                if op_t in (TYPE_INT, TYPE_FLOAT):
                    return op_t
                raise TypeError(f"Unary '-' expects numeric type, got '{op_t}'", expr.loc)
            elif expr.op in ("!", "not"):
                if op_t == TYPE_BOOL:
                    return TYPE_BOOL
                raise TypeError(f"Unary '!' expects Bool, got '{op_t}'", expr.loc)
            raise TypeError(f"Unknown unary operator '{expr.op}'", expr.loc)

        elif isinstance(expr, CallExpr):
            # Check if calling a constructor directly: e.g. Node(1)
            if isinstance(expr.callee, IdentifierExpr) and expr.callee.name in self.global_types:
                t = self.global_types[expr.callee.name]
                if isinstance(t, ClassType):
                    # Check init args
                    init_fn = t.methods.get("init")
                    if init_fn:
                        if len(expr.args) == 0 and not t.has_explicit_init:
                            pass
                        elif len(expr.args) != len(init_fn.param_types):
                            raise TypeError(f"Class '{t.name}' constructor expects {len(init_fn.param_types)} args, got {len(expr.args)}", expr.loc)
                        else:
                            for a, pt in zip(expr.args, init_fn.param_types):
                                at = self._check_expr(a)
                                if not at.can_assign_to(pt):
                                    raise TypeError(f"Constructor arg type '{at}' does not match '{pt}'", expr.loc)
                    return t
                elif isinstance(t, StructType):
                    return t

            callee_t = self._check_expr(expr.callee)

            # Built-in print/println polymorphic support
            if isinstance(expr.callee, IdentifierExpr) and expr.callee.name in ("print", "println", "blume_retain_count", "blume_memory_domain"):
                for a in expr.args:
                    self._check_expr(a)
                if expr.callee.name in ("print", "println"):
                    return TYPE_VOID
                elif expr.callee.name == "blume_retain_count":
                    return TYPE_INT
                elif expr.callee.name == "blume_memory_domain":
                    return TYPE_STRING

            if isinstance(callee_t, FunctionType):
                if len(expr.args) != len(callee_t.param_types):
                    raise TypeError(f"Expected {len(callee_t.param_types)} arguments, got {len(expr.args)}", expr.loc)
                for a, pt in zip(expr.args, callee_t.param_types):
                    at = self._check_expr(a)
                    if not at.can_assign_to(pt):
                        raise TypeError(f"Argument type '{at}' does not match parameter type '{pt}'", expr.loc)
                return callee_t.return_type

            raise TypeError(f"Cannot call non-function type '{callee_t}'", expr.loc)

        elif isinstance(expr, MemberAccessExpr):
            obj_t = self._check_expr(expr.obj)
            # Unwrap weak or optional if needed
            base_t = obj_t
            if isinstance(base_t, (WeakType, UnownedType, OptionalType)):
                base_t = getattr(base_t, "inner", base_t)

            if isinstance(base_t, ClassType):
                if expr.member in base_t.fields:
                    return base_t.fields[expr.member]
                if expr.member in base_t.methods:
                    return base_t.methods[expr.member]
                raise TypeError(f"Class '{base_t.name}' has no member '{expr.member}'", expr.loc)

            elif isinstance(base_t, StructType):
                if expr.member in base_t.fields:
                    return base_t.fields[expr.member]
                raise TypeError(f"Struct '{base_t.name}' has no field '{expr.member}'", expr.loc)

            elif isinstance(base_t, ArrayType):
                if expr.member == "len":
                    return FunctionType([], TYPE_INT)
                if expr.member == "push":
                    return FunctionType([base_t.element_type], TYPE_VOID)
                if expr.member == "pop":
                    return FunctionType([], base_t.element_type)

            raise TypeError(f"Cannot access member '{expr.member}' on type '{obj_t}'", expr.loc)

        elif isinstance(expr, IndexExpr):
            target_t = self._check_expr(expr.target)
            idx_t = self._check_expr(expr.index)
            if idx_t != TYPE_INT:
                raise TypeError(f"Index must be Int, got '{idx_t}'", expr.loc)
            if isinstance(target_t, ArrayType):
                return target_t.element_type
            raise TypeError(f"Cannot index non-array type '{target_t}'", expr.loc)

        elif isinstance(expr, ArrayLiteralExpr):
            if not expr.elements:
                return ArrayType(element_type=TYPE_INT)
            elem_types = [self._check_expr(e) for e in expr.elements]
            first_t = elem_types[0]
            for et in elem_types[1:]:
                if et != first_t:
                    raise TypeError(f"Array literal elements must have same type, got '{first_t}' and '{et}'", expr.loc)
            return ArrayType(element_type=first_t)

        elif isinstance(expr, NewExpr):
            if expr.type_name not in self.global_types:
                raise TypeError(f"Unknown type '{expr.type_name}' in new expression", expr.loc)
            base_t = self.global_types[expr.type_name]
            if isinstance(base_t, ClassType):
                # Instantiate class with explicit or default ownership
                ownership = expr.ownership if expr.ownership != OwnershipKind.AUTOMATIC else base_t.ownership
                # Check constructor args
                init_fn = base_t.methods.get("init")
                if init_fn:
                    if len(expr.args) == 0 and not base_t.has_explicit_init:
                        pass
                    elif len(expr.args) != len(init_fn.param_types):
                        raise TypeError(f"Class '{base_t.name}' constructor expects {len(init_fn.param_types)} arguments, got {len(expr.args)}", expr.loc)
                    else:
                        for a, pt in zip(expr.args, init_fn.param_types):
                            at = self._check_expr(a)
                            if not at.can_assign_to(pt):
                                raise TypeError(f"Constructor argument type '{at}' does not match '{pt}'", expr.loc)
                return ClassType(
                    name=base_t.name,
                    ownership=ownership,
                    fields=base_t.fields,
                    field_ownership=base_t.field_ownership,
                    methods=base_t.methods,
                    has_deinit=base_t.has_deinit
                )
            elif isinstance(base_t, StructType):
                return base_t
            raise TypeError(f"Cannot instantiate type '{expr.type_name}'", expr.loc)

        elif isinstance(expr, RangeExpr):
            st = self._check_expr(expr.start)
            et = self._check_expr(expr.end)
            if st != TYPE_INT or et != TYPE_INT:
                raise TypeError(f"Range boundaries must be Int, got '{st}' and '{et}'", expr.loc)
            return TYPE_INT

        elif isinstance(expr, WeakRefExpr):
            inner_t = self._check_expr(expr.expr)
            if not inner_t.is_reference_type():
                raise TypeError(f"Cannot create weak reference to value type '{inner_t}'", expr.loc)
            return WeakType(inner=inner_t)

        return TYPE_VOID
