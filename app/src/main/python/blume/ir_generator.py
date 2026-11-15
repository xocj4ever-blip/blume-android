"""
Blume Programming Language - Blume Memory Management IR Generator
Version: 1.0
100% Pure Python Implementation
"""

from typing import Dict, List, Optional, Any, Tuple
from blume.ast import (
    ProgramNode, FuncDecl, ClassDecl, StructDecl, StmtNode, ExprNode,
    VarDeclStmt, AssignStmt, IfStmt, WhileStmt, ForStmt, ReturnStmt, DeferStmt,
    BlockStmt, ExprStmt, LiteralExpr, IdentifierExpr, BinaryExpr, UnaryExpr,
    CallExpr, MemberAccessExpr, IndexExpr, ArrayLiteralExpr, NewExpr,
    RangeExpr, WeakRefExpr, OwnershipKind
)
from blume.types import ClassType, StructType, WeakType, UnownedType, ArrayType, Type
from blume.ir import (
    IROpcode, IRInstruction, IRBasicBlock, IRFunction, IRModule, IRClassInfo
)
from blume.ownership_analyzer import OwnershipAnalyzer

class ScopeContext:
    def __init__(self, parent: Optional["ScopeContext"] = None):
        self.parent = parent
        # Map var_name -> (reg_or_slot, ownership, type)
        self.variables: Dict[str, Tuple[str, OwnershipKind, Optional[Type]]] = {}
        # List of variables to cleanup upon scope exit: (slot_or_reg, ownership)
        self.scoped_vars: List[Tuple[str, OwnershipKind]] = []
        # Deferred statements in this scope
        self.defers: List[BlockStmt] = []

    def define(self, name: str, reg: str, ownership: OwnershipKind, typ: Optional[Type] = None):
        self.variables[name] = (reg, ownership, typ)
        self.scoped_vars.append((reg, ownership))

    def lookup(self, name: str) -> Optional[Tuple[str, OwnershipKind, Optional[Type]]]:
        if name in self.variables:
            return self.variables[name]
        if self.parent:
            return self.parent.lookup(name)
        return None

class IRGenerator:
    def __init__(self, ownership_analyzer: Optional[OwnershipAnalyzer] = None):
        self.analyzer = ownership_analyzer or OwnershipAnalyzer()
        self.module = IRModule(name="main")
        self.current_fn: Optional[IRFunction] = None
        self.current_scope: Optional[ScopeContext] = None

    def generate(self, program: ProgramNode) -> IRModule:
        # First register class information
        for decl in program.declarations:
            if isinstance(decl, ClassDecl):
                field_names = [f.name for f in decl.fields]
                self.module.classes[decl.name] = IRClassInfo(
                    name=decl.name,
                    domain=decl.default_ownership,
                    fields=field_names,
                    has_deinit=(decl.deinit_method is not None)
                )

        # Generate class methods & deinit functions
        for decl in program.declarations:
            if isinstance(decl, ClassDecl):
                self._generate_class(decl)

        # Generate standalone functions
        for decl in program.declarations:
            if isinstance(decl, FuncDecl):
                self._generate_func(decl)

        # Generate top-level code inside a main/entry function
        top_stmts = [d for d in program.declarations if isinstance(d, StmtNode)]
        main_fn = IRFunction(name="__blume_main__", return_type="Void")
        self.current_fn = main_fn
        entry_bb = main_fn.new_block("entry")
        main_fn.current_block = entry_bb

        self.current_scope = ScopeContext()
        for stmt in top_stmts:
            self._generate_stmt(stmt)

        # Emit scope cleanup for top level
        self._emit_scope_cleanup(self.current_scope)
        main_fn.emit(IROpcode.RET, [None])

        self.module.add_function(main_fn)
        self.module.top_level_func = main_fn

        return self.module

    def _generate_class(self, cls: ClassDecl):
        # Generate deinit function if present
        if cls.deinit_method:
            deinit_fn = IRFunction(name=f"{cls.name}__deinit", params=["%self"], return_type="Void")
            self.current_fn = deinit_fn
            bb = deinit_fn.new_block("entry")
            deinit_fn.current_block = bb
            self.current_scope = ScopeContext()
            self.current_scope.define("self", "%self", OwnershipKind.UNOWNED)

            for stmt in cls.deinit_method.statements:
                self._generate_stmt(stmt)

            deinit_fn.emit(IROpcode.RET, [None])
            self.module.add_function(deinit_fn)

        # Generate init function
        if cls.init_method:
            init_fn_name = f"{cls.name}__init"
            param_names = ["%self"] + [f"%arg_{p.name}" for p in cls.init_method.params]
            init_fn = IRFunction(name=init_fn_name, params=param_names, return_type="Void")
            self.current_fn = init_fn
            bb = init_fn.new_block("entry")
            init_fn.current_block = bb
            self.current_scope = ScopeContext()
            self.current_scope.define("self", "%self", OwnershipKind.UNOWNED)

            for i, p in enumerate(cls.init_method.params):
                self.current_scope.define(p.name, param_names[i + 1], p.ownership)

            for stmt in cls.init_method.body.statements:
                self._generate_stmt(stmt)

            self._emit_scope_cleanup(self.current_scope)
            init_fn.emit(IROpcode.RET, [None])
            self.module.add_function(init_fn)

        # Generate methods
        for method in cls.methods:
            method_fn_name = f"{cls.name}__{method.name}"
            param_names = ["%self"] + [f"%arg_{p.name}" for p in method.params]
            method_fn = IRFunction(name=method_fn_name, params=param_names, return_type=method.return_type.name)
            self.current_fn = method_fn
            bb = method_fn.new_block("entry")
            method_fn.current_block = bb
            self.current_scope = ScopeContext()
            self.current_scope.define("self", "%self", OwnershipKind.UNOWNED)

            for i, p in enumerate(method.params):
                self.current_scope.define(p.name, param_names[i + 1], p.ownership)

            for stmt in method.body.statements:
                self._generate_stmt(stmt)

            self._emit_scope_cleanup(self.current_scope)
            if not method_fn.current_block.instructions or method_fn.current_block.instructions[-1].opcode != IROpcode.RET:
                method_fn.emit(IROpcode.RET, [None])

            self.module.add_function(method_fn)

    def _generate_func(self, func: FuncDecl):
        param_regs = [f"%arg_{p.name}" for p in func.params]
        ir_fn = IRFunction(name=func.name, params=param_regs, return_type=func.return_type.name)
        self.current_fn = ir_fn
        bb = ir_fn.new_block("entry")
        ir_fn.current_block = bb

        self.current_scope = ScopeContext()
        for i, p in enumerate(func.params):
            slot = ir_fn.new_reg(f"%slot_{p.name}")
            ir_fn.emit(IROpcode.ALLOCA, [p.name], result=slot)
            ir_fn.emit(IROpcode.STORE, [param_regs[i], slot])
            self.current_scope.define(p.name, slot, p.ownership)
            if p.ownership == OwnershipKind.SHARED:
                ir_fn.emit(IROpcode.BLUME_GC_ROOT, [slot])

        for stmt in func.body.statements:
            self._generate_stmt(stmt)

        self._emit_scope_cleanup(self.current_scope)
        if not ir_fn.current_block.instructions or ir_fn.current_block.instructions[-1].opcode != IROpcode.RET:
            ir_fn.emit(IROpcode.RET, [None])

        self.module.add_function(ir_fn)

    def _emit_scope_cleanup(self, scope: ScopeContext):
        # 1. Execute defer blocks in LIFO order
        for defer_block in reversed(scope.defers):
            for s in defer_block.statements:
                self._generate_stmt(s)

        # 2. Release ARC variables & unroot GC variables
        for slot, ownership in reversed(scope.scoped_vars):
            if ownership == OwnershipKind.OWNED:
                # Load current value from slot and release
                val_reg = self.current_fn.new_reg("%rel_val")
                self.current_fn.emit(IROpcode.LOAD, [slot], result=val_reg)
                self.current_fn.emit(IROpcode.BLUME_RELEASE, [val_reg])
            elif ownership == OwnershipKind.SHARED:
                self.current_fn.emit(IROpcode.BLUME_GC_UNROOT, [slot])

    def _generate_stmt(self, stmt: StmtNode):
        fn = self.current_fn

        if isinstance(stmt, BlockStmt):
            prev_scope = self.current_scope
            self.current_scope = ScopeContext(parent=prev_scope)
            for s in stmt.statements:
                self._generate_stmt(s)
            self._emit_scope_cleanup(self.current_scope)
            self.current_scope = prev_scope

        elif isinstance(stmt, VarDeclStmt):
            slot = fn.new_reg(f"%slot_{stmt.name}")
            fn.emit(IROpcode.ALLOCA, [stmt.name], result=slot)

            init_val = None
            if stmt.initializer:
                init_val = self._generate_expr(stmt.initializer)
            else:
                init_val = fn.new_reg("%nil_const")
                fn.emit(IROpcode.CONST, [None], result=init_val)

            fn.emit(IROpcode.STORE, [init_val, slot])

            ownership = stmt.ownership
            if ownership == OwnershipKind.AUTOMATIC:
                ownership = self.analyzer.resolved_ownership.get(id(stmt), OwnershipKind.OWNED)

            is_new_alloc = isinstance(stmt.initializer, NewExpr) or (
                isinstance(stmt.initializer, CallExpr) and
                isinstance(stmt.initializer.callee, IdentifierExpr) and
                stmt.initializer.callee.name in self.module.classes
            )

            if ownership == OwnershipKind.OWNED and stmt.initializer and not is_new_alloc:
                # ARC aliasing: retain existing object reference
                fn.emit(IROpcode.BLUME_RETAIN, [init_val])

            self.current_scope.define(stmt.name, slot, ownership)

            if ownership == OwnershipKind.SHARED:
                fn.emit(IROpcode.BLUME_GC_ROOT, [slot])

        elif isinstance(stmt, AssignStmt):
            val_reg = self._generate_expr(stmt.value)

            if isinstance(stmt.target, IdentifierExpr):
                info = self.current_scope.lookup(stmt.target.name)
                if info:
                    slot, ownership, _ = info
                    # If reassigning an ARC owned slot, release old value first!
                    if ownership == OwnershipKind.OWNED:
                        old_val = fn.new_reg("%old_val")
                        fn.emit(IROpcode.LOAD, [slot], result=old_val)
                        fn.emit(IROpcode.BLUME_RELEASE, [old_val])
                        fn.emit(IROpcode.BLUME_RETAIN, [val_reg])

                    fn.emit(IROpcode.STORE, [val_reg, slot])

            elif isinstance(stmt.target, MemberAccessExpr):
                obj_reg = self._generate_expr(stmt.target.obj)
                fn.emit(IROpcode.SET_FIELD, [obj_reg, stmt.target.member, val_reg])

                # Check for cross-domain bridge
                # Emit blume.bridge to coordinate cross-domain references
                fn.emit(IROpcode.BLUME_BRIDGE, [obj_reg, stmt.target.member, val_reg], metadata={"bridge": "cross_domain"})

            elif isinstance(stmt.target, IndexExpr):
                arr_reg = self._generate_expr(stmt.target.target)
                idx_reg = self._generate_expr(stmt.target.index)
                fn.emit(IROpcode.SET_ELEM, [arr_reg, idx_reg, val_reg])

        elif isinstance(stmt, IfStmt):
            cond_reg = self._generate_expr(stmt.condition)
            then_bb = fn.new_block("then")
            else_bb = fn.new_block("else")
            merge_bb = fn.new_block("merge")

            target_else = else_bb if stmt.else_branch else merge_bb
            fn.emit(IROpcode.BR_COND, [cond_reg, then_bb.label, target_else.label])

            # Then block
            fn.current_block = then_bb
            self._generate_stmt(stmt.then_branch)
            fn.emit(IROpcode.BR, [merge_bb.label])

            # Else block
            if stmt.else_branch:
                fn.current_block = else_bb
                self._generate_stmt(stmt.else_branch)
                fn.emit(IROpcode.BR, [merge_bb.label])

            fn.current_block = merge_bb

        elif isinstance(stmt, WhileStmt):
            header_bb = fn.new_block("while_header")
            body_bb = fn.new_block("while_body")
            exit_bb = fn.new_block("while_exit")

            fn.emit(IROpcode.BR, [header_bb.label])

            fn.current_block = header_bb
            # Emit safepoint at loop back-edge
            fn.emit(IROpcode.BLUME_SAFEPOINT, [])
            cond_reg = self._generate_expr(stmt.condition)
            fn.emit(IROpcode.BR_COND, [cond_reg, body_bb.label, exit_bb.label])

            fn.current_block = body_bb
            self._generate_stmt(stmt.body)
            fn.emit(IROpcode.BR, [header_bb.label])

            fn.current_block = exit_bb

        elif isinstance(stmt, ForStmt):
            # For loop over range or array
            iter_reg = self._generate_expr(stmt.iterable)
            # Desugar for-in range loop
            # header, body, incr, exit
            header_bb = fn.new_block("for_header")
            body_bb = fn.new_block("for_body")
            exit_bb = fn.new_block("for_exit")

            # Check if range (handled via loop index)
            slot = fn.new_reg(f"%slot_{stmt.var_name}")
            fn.emit(IROpcode.ALLOCA, [stmt.var_name], result=slot)

            # If iterable is array or range, we iterate
            idx_slot = fn.new_reg("%for_idx")
            fn.emit(IROpcode.ALLOCA, ["_idx"], result=idx_slot)
            c0 = fn.new_reg("%c0")
            fn.emit(IROpcode.CONST, [0], result=c0)
            fn.emit(IROpcode.STORE, [c0, idx_slot])

            fn.emit(IROpcode.BR, [header_bb.label])

            fn.current_block = header_bb
            fn.emit(IROpcode.BLUME_SAFEPOINT, [])
            curr_idx = fn.new_reg("%idx_val")
            fn.emit(IROpcode.LOAD, [idx_slot], result=curr_idx)

            # Determine length or range end
            cond_reg = fn.new_reg("%cond")
            fn.emit(IROpcode.BINOP, ["<", curr_idx, iter_reg], result=cond_reg)
            fn.emit(IROpcode.BR_COND, [cond_reg, body_bb.label, exit_bb.label])

            fn.current_block = body_bb
            fn.emit(IROpcode.STORE, [curr_idx, slot])

            prev_scope = self.current_scope
            self.current_scope = ScopeContext(parent=prev_scope)
            self.current_scope.define(stmt.var_name, slot, OwnershipKind.AUTOMATIC)
            for s in stmt.body.statements:
                self._generate_stmt(s)
            self._emit_scope_cleanup(self.current_scope)
            self.current_scope = prev_scope

            # Increment index
            c1 = fn.new_reg("%c1")
            fn.emit(IROpcode.CONST, [1], result=c1)
            next_idx = fn.new_reg("%next_idx")
            fn.emit(IROpcode.BINOP, ["+", curr_idx, c1], result=next_idx)
            fn.emit(IROpcode.STORE, [next_idx, idx_slot])
            fn.emit(IROpcode.BR, [header_bb.label])

            fn.current_block = exit_bb

        elif isinstance(stmt, ReturnStmt):
            ret_val = None
            if stmt.value:
                ret_val = self._generate_expr(stmt.value)

            # Clean up scopes before returning
            curr = self.current_scope
            while curr is not None:
                self._emit_scope_cleanup(curr)
                curr = curr.parent

            fn.emit(IROpcode.RET, [ret_val])

        elif isinstance(stmt, DeferStmt):
            if self.current_scope:
                self.current_scope.defers.append(stmt.body)

        elif isinstance(stmt, ExprStmt):
            self._generate_expr(stmt.expr)

    def _generate_expr(self, expr: ExprNode) -> str:
        fn = self.current_fn

        if isinstance(expr, LiteralExpr):
            reg = fn.new_reg("%c")
            fn.emit(IROpcode.CONST, [expr.value], result=reg, metadata={"type": expr.type_name})
            return reg

        elif isinstance(expr, IdentifierExpr):
            info = self.current_scope.lookup(expr.name)
            if info:
                slot_or_reg, ownership, _ = info
                if slot_or_reg.startswith("%slot_") or slot_or_reg.startswith("%r"):
                    # Load value from slot
                    res_reg = fn.new_reg("%val")
                    fn.emit(IROpcode.LOAD, [slot_or_reg], result=res_reg)
                    return res_reg
                return slot_or_reg
            # If global or parameter
            return f"%{expr.name}"

        elif isinstance(expr, BinaryExpr):
            left_reg = self._generate_expr(expr.left)
            right_reg = self._generate_expr(expr.right)
            res_reg = fn.new_reg("%bin")
            fn.emit(IROpcode.BINOP, [expr.op, left_reg, right_reg], result=res_reg)
            return res_reg

        elif isinstance(expr, UnaryExpr):
            op_reg = self._generate_expr(expr.operand)
            res_reg = fn.new_reg("%un")
            fn.emit(IROpcode.UNOP, [expr.op, op_reg], result=res_reg)
            return res_reg

        elif isinstance(expr, CallExpr):
            # Special built-in checks
            if isinstance(expr.callee, IdentifierExpr):
                name = expr.callee.name
                if name in ("print", "println"):
                    arg_regs = [self._generate_expr(a) for a in expr.args]
                    fn.emit(IROpcode.PRINT, arg_regs)
                    res = fn.new_reg("%void")
                    fn.emit(IROpcode.CONST, [None], result=res)
                    return res
                elif name == "blume_gc_collect":
                    res = fn.new_reg("%gc_count")
                    fn.emit(IROpcode.BLUME_GC_COLLECT, [], result=res)
                    return res
                elif name == "blume_retain_count":
                    arg_reg = self._generate_expr(expr.args[0])
                    res = fn.new_reg("%rc")
                    fn.emit(IROpcode.CALL, ["__blume_get_retain_count__", arg_reg], result=res)
                    return res
                elif name == "blume_memory_domain":
                    arg_reg = self._generate_expr(expr.args[0])
                    res = fn.new_reg("%dom")
                    fn.emit(IROpcode.CALL, ["__blume_get_domain__", arg_reg], result=res)
                    return res
                elif name == "blume_heap_stats":
                    fn.emit(IROpcode.CALL, ["__blume_heap_stats__"])
                    res = fn.new_reg("%void")
                    fn.emit(IROpcode.CONST, [None], result=res)
                    return res
                elif name == "assert":
                    arg_regs = [self._generate_expr(a) for a in expr.args]
                    fn.emit(IROpcode.ASSERT, arg_regs)
                    res = fn.new_reg("%void")
                    fn.emit(IROpcode.CONST, [None], result=res)
                    return res

            # Check if calling a constructor directly: e.g. ClassName(args...)
            if isinstance(expr.callee, IdentifierExpr) and expr.callee.name in self.module.classes:
                cls_info = self.module.classes[expr.callee.name]
                domain = cls_info.domain
                return self._emit_allocation(expr.callee.name, expr.args, domain)

            # Direct function call by identifier name
            if isinstance(expr.callee, IdentifierExpr):
                callee_name = expr.callee.name
                arg_regs = [self._generate_expr(a) for a in expr.args]
                res_reg = fn.new_reg("%call")
                fn.emit(IROpcode.CALL, [callee_name] + arg_regs, result=res_reg)
                return res_reg

            # Member method call: obj.method(args...)
            if isinstance(expr.callee, MemberAccessExpr):
                obj_reg = self._generate_expr(expr.callee.obj)
                arg_regs = [obj_reg] + [self._generate_expr(a) for a in expr.args]
                res_reg = fn.new_reg("%ret")
                fn.emit(IROpcode.CALL, [f"__method_{expr.callee.member}__"] + arg_regs, result=res_reg)
                return res_reg

            callee_reg = self._generate_expr(expr.callee)
            arg_regs = [self._generate_expr(a) for a in expr.args]
            res_reg = fn.new_reg("%call")
            fn.emit(IROpcode.CALL, [callee_reg] + arg_regs, result=res_reg)
            return res_reg

        elif isinstance(expr, MemberAccessExpr):
            obj_reg = self._generate_expr(expr.obj)
            res_reg = fn.new_reg("%fld")
            fn.emit(IROpcode.GET_FIELD, [obj_reg, expr.member], result=res_reg)
            return res_reg

        elif isinstance(expr, IndexExpr):
            target_reg = self._generate_expr(expr.target)
            idx_reg = self._generate_expr(expr.index)
            res_reg = fn.new_reg("%elem")
            fn.emit(IROpcode.GET_ELEM, [target_reg, idx_reg], result=res_reg)
            return res_reg

        elif isinstance(expr, ArrayLiteralExpr):
            elem_regs = [self._generate_expr(e) for e in expr.elements]
            res_reg = fn.new_reg("%arr")
            fn.emit(IROpcode.ARRAY_NEW, elem_regs, result=res_reg)
            return res_reg

        elif isinstance(expr, NewExpr):
            domain = expr.ownership
            if domain == OwnershipKind.AUTOMATIC:
                cls_info = self.module.classes.get(expr.type_name)
                domain = cls_info.domain if cls_info else OwnershipKind.OWNED
            return self._emit_allocation(expr.type_name, expr.args, domain)

        elif isinstance(expr, RangeExpr):
            # Evaluate end of range for iteration
            return self._generate_expr(expr.end)

        elif isinstance(expr, WeakRefExpr):
            inner_reg = self._generate_expr(expr.expr)
            res_reg = fn.new_reg("%wref")
            fn.emit(IROpcode.BLUME_WEAK, [inner_reg], result=res_reg)
            return res_reg

        res = fn.new_reg("%nil")
        fn.emit(IROpcode.CONST, [None], result=res)
        return res

    def _emit_allocation(self, class_name: str, args: List[ExprNode], domain: OwnershipKind) -> str:
        fn = self.current_fn
        cls_info = self.module.classes.get(class_name)
        fields = cls_info.fields if cls_info else []

        obj_reg = fn.new_reg("%obj")
        fn.emit(IROpcode.BLUME_ALLOC, [domain.value, class_name, fields], result=obj_reg)
        fn.emit(IROpcode.BLUME_OWNERSHIP, [obj_reg, domain.value])

        # If constructor exists, call init
        arg_regs = [self._generate_expr(a) for a in args]
        init_fn_name = f"{class_name}__init"
        if init_fn_name in self.module.functions:
            fn.emit(IROpcode.CALL, [init_fn_name, obj_reg] + arg_regs)
        else:
            # Assign positional args directly to fields
            for i, arg_reg in enumerate(arg_regs):
                if i < len(fields):
                    fn.emit(IROpcode.SET_FIELD, [obj_reg, fields[i], arg_reg])

        return obj_reg
