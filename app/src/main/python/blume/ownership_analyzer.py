"""
Blume Programming Language - Ownership Analyzer & Memory Strategy Selection
Version: 1.0
100% Pure Python Implementation
"""

from typing import Dict, List, Set, Optional, Tuple
from dataclasses import dataclass
from blume.ast import (
    ProgramNode, FuncDecl, ClassDecl, StructDecl, StmtNode, ExprNode,
    VarDeclStmt, AssignStmt, ReturnStmt, CallExpr, MemberAccessExpr,
    NewExpr, IdentifierExpr, BlockStmt, IfStmt, WhileStmt, ForStmt,
    OwnershipKind, SourceLocation
)
from blume.types import ClassType, StructType, WeakType, UnownedType, Type

@dataclass
class BridgeEdge:
    source_domain: OwnershipKind
    target_domain: OwnershipKind
    source_var_or_field: str
    target_type: str
    loc: SourceLocation

@dataclass
class OwnershipDiagnostic:
    message: str
    loc: SourceLocation
    is_warning: bool = False

class OwnershipAnalyzer:
    def __init__(self):
        self.diagnostics: List[OwnershipDiagnostic] = []
        self.bridge_edges: List[BridgeEdge] = []
        # Map from AST node id to resolved ownership
        self.resolved_ownership: Dict[int, OwnershipKind] = {}
        # Track potential cycles between classes
        self.class_references: Dict[str, Set[str]] = {}

    def analyze_program(self, program: ProgramNode):
        # 1. Collect class references to detect potential cycles
        for decl in program.declarations:
            if isinstance(decl, ClassDecl):
                self._collect_class_refs(decl)

        # 2. Check for strong reference cycles among 'owned' classes
        self._check_strong_reference_cycles()

        # 3. Analyze declarations and select memory strategy for 'automatic'
        for decl in program.declarations:
            if isinstance(decl, FuncDecl):
                self._analyze_func(decl)
            elif isinstance(decl, ClassDecl):
                self._analyze_class(decl)
            elif isinstance(decl, StmtNode):
                self._analyze_stmt(decl)

    def _collect_class_refs(self, decl: ClassDecl):
        refs = set()
        for f in decl.fields:
            if f.ownership in (OwnershipKind.OWNED, OwnershipKind.AUTOMATIC):
                # If field refers to another class
                f_type_name = f.type_annotation.name
                refs.add(f_type_name)
        self.class_references[decl.name] = refs

    def _check_strong_reference_cycles(self):
        # Warn if two owned classes hold strong references to each other
        for cls_a, refs_a in self.class_references.items():
            for cls_b in refs_a:
                if cls_b in self.class_references and cls_a in self.class_references[cls_b]:
                    self.diagnostics.append(OwnershipDiagnostic(
                        message=f"Potential strong reference cycle between '{cls_a}' and '{cls_b}'. Consider using 'weak' or 'shared' (GC).",
                        loc=SourceLocation(1, 1),
                        is_warning=True
                    ))

    def _analyze_func(self, func: FuncDecl):
        # Escape analysis within function
        returned_vars = set()
        for stmt in func.body.statements:
            if isinstance(stmt, ReturnStmt) and stmt.value:
                if isinstance(stmt.value, IdentifierExpr):
                    returned_vars.add(stmt.value.name)

        for stmt in func.body.statements:
            self._analyze_stmt(stmt, returned_vars=returned_vars)

    def _analyze_class(self, cls: ClassDecl):
        # Analyze class fields and cross-domain references
        owner_domain = cls.default_ownership
        for f in cls.fields:
            f_domain = f.ownership
            if f_domain == OwnershipKind.AUTOMATIC:
                f_domain = owner_domain

            # Cross-domain check
            if owner_domain == OwnershipKind.OWNED and f_domain == OwnershipKind.SHARED:
                self.bridge_edges.append(BridgeEdge(
                    source_domain=OwnershipKind.OWNED,
                    target_domain=OwnershipKind.SHARED,
                    source_var_or_field=f"{cls.name}.{f.name}",
                    target_type=f.type_annotation.name,
                    loc=f.loc
                ))
            elif owner_domain == OwnershipKind.SHARED and f_domain == OwnershipKind.OWNED:
                self.bridge_edges.append(BridgeEdge(
                    source_domain=OwnershipKind.SHARED,
                    target_domain=OwnershipKind.OWNED,
                    source_var_or_field=f"{cls.name}.{f.name}",
                    target_type=f.type_annotation.name,
                    loc=f.loc
                ))

        if cls.init_method:
            for s in cls.init_method.body.statements:
                self._analyze_stmt(s)
        for m in cls.methods:
            for s in m.body.statements:
                self._analyze_stmt(s)

    def _analyze_stmt(self, stmt: StmtNode, returned_vars: Optional[Set[str]] = None):
        if returned_vars is None:
            returned_vars = set()

        if isinstance(stmt, VarDeclStmt):
            ownership = stmt.ownership
            if ownership == OwnershipKind.AUTOMATIC:
                # Infer strategy via escape analysis and type characteristics
                if stmt.initializer and isinstance(stmt.initializer, NewExpr):
                    # Check if class has deinit
                    # If local and not escaping to shared container -> OWNED (Swift ARC)
                    # If returned -> OWNED (caller takes ownership)
                    # If specifically cyclic or shared -> SHARED (Kotlin GC)
                    chosen_strategy = OwnershipKind.OWNED
                    self.resolved_ownership[id(stmt)] = chosen_strategy
                    stmt.ownership = chosen_strategy
                else:
                    stmt.ownership = OwnershipKind.OWNED
                    self.resolved_ownership[id(stmt)] = OwnershipKind.OWNED

            if stmt.initializer:
                self._analyze_expr(stmt.initializer, target_ownership=stmt.ownership)

        elif isinstance(stmt, AssignStmt):
            self._analyze_expr(stmt.target)
            self._analyze_expr(stmt.value)

        elif isinstance(stmt, BlockStmt):
            for s in stmt.statements:
                self._analyze_stmt(s, returned_vars)

        elif isinstance(stmt, IfStmt):
            self._analyze_stmt(stmt.then_branch, returned_vars)
            if stmt.else_branch:
                self._analyze_stmt(stmt.else_branch, returned_vars)

        elif isinstance(stmt, WhileStmt):
            self._analyze_stmt(stmt.body, returned_vars)

        elif isinstance(stmt, ForStmt):
            self._analyze_stmt(stmt.body, returned_vars)

    def _analyze_expr(self, expr: ExprNode, target_ownership: OwnershipKind = OwnershipKind.AUTOMATIC):
        if isinstance(expr, NewExpr):
            if expr.ownership == OwnershipKind.AUTOMATIC:
                if target_ownership != OwnershipKind.AUTOMATIC:
                    expr.ownership = target_ownership
                else:
                    expr.ownership = OwnershipKind.OWNED
            self.resolved_ownership[id(expr)] = expr.ownership

            for arg in expr.args:
                self._analyze_expr(arg)

        elif isinstance(expr, CallExpr):
            self._analyze_expr(expr.callee)
            for a in expr.args:
                self._analyze_expr(a)

        elif isinstance(expr, MemberAccessExpr):
            self._analyze_expr(expr.obj)
