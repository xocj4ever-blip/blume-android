"""
Blume Programming Language - Abstract Syntax Tree (AST) definitions
Version: 1.0
100% Pure Python Implementation
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Any, Union

class OwnershipKind(Enum):
    AUTOMATIC = "automatic"  # Compiler-selected memory strategy
    OWNED = "owned"          # Swift-inspired ARC-managed ownership
    SHARED = "shared"        # Kotlin-inspired GC-managed shared allocation
    WEAK = "weak"            # Non-owning weak reference (ARC)
    UNOWNED = "unowned"      # Non-owning reference with lifetime assertion (ARC)

    @classmethod
    def from_str(cls, s: str) -> "OwnershipKind":
        try:
            return cls(s.lower())
        except ValueError:
            return cls.AUTOMATIC

@dataclass
class SourceLocation:
    line: int
    column: int
    file: str = "<input>"

    def __str__(self) -> str:
        return f"{self.file}:{self.line}:{self.column}"

@dataclass
class ASTNode:
    loc: SourceLocation = field(default_factory=lambda: SourceLocation(1, 1))

# ----------------- Type Nodes -----------------

@dataclass
class TypeNode(ASTNode):
    name: str = "Void"
    ownership: OwnershipKind = OwnershipKind.AUTOMATIC
    is_optional: bool = False
    generic_args: List["TypeNode"] = field(default_factory=list)

    def __str__(self) -> str:
        res = self.name
        if self.generic_args:
            res += f"[{', '.join(str(g) for g in self.generic_args)}]"
        if self.is_optional:
            res += "?"
        if self.ownership != OwnershipKind.AUTOMATIC:
            res = f"{self.ownership.value} {res}"
        return res

# ----------------- Expressions -----------------

@dataclass
class ExprNode(ASTNode):
    inferred_type: Optional[Any] = None

@dataclass
class LiteralExpr(ExprNode):
    value: Any = None
    type_name: str = "Int"  # "Int", "Float", "String", "Bool", "Nil"

@dataclass
class IdentifierExpr(ExprNode):
    name: str = ""

@dataclass
class BinaryExpr(ExprNode):
    left: ExprNode = field(default_factory=ExprNode)
    op: str = "+"
    right: ExprNode = field(default_factory=ExprNode)

@dataclass
class UnaryExpr(ExprNode):
    op: str = "-"
    operand: ExprNode = field(default_factory=ExprNode)

@dataclass
class CallExpr(ExprNode):
    callee: ExprNode = field(default_factory=ExprNode)
    args: List[ExprNode] = field(default_factory=list)

@dataclass
class MemberAccessExpr(ExprNode):
    obj: ExprNode = field(default_factory=ExprNode)
    member: str = ""

@dataclass
class IndexExpr(ExprNode):
    target: ExprNode = field(default_factory=ExprNode)
    index: ExprNode = field(default_factory=ExprNode)

@dataclass
class ArrayLiteralExpr(ExprNode):
    elements: List[ExprNode] = field(default_factory=list)

@dataclass
class NewExpr(ExprNode):
    type_name: str = ""
    args: List[ExprNode] = field(default_factory=list)
    ownership: OwnershipKind = OwnershipKind.AUTOMATIC

@dataclass
class RangeExpr(ExprNode):
    start: ExprNode = field(default_factory=ExprNode)
    end: ExprNode = field(default_factory=ExprNode)

@dataclass
class WeakRefExpr(ExprNode):
    expr: ExprNode = field(default_factory=ExprNode)

# ----------------- Statements -----------------

@dataclass
class StmtNode(ASTNode):
    pass

@dataclass
class BlockStmt(StmtNode):
    statements: List[StmtNode] = field(default_factory=list)

@dataclass
class ExprStmt(StmtNode):
    expr: ExprNode = field(default_factory=ExprNode)

@dataclass
class VarDeclStmt(StmtNode):
    name: str = ""
    is_mutable: bool = False
    ownership: OwnershipKind = OwnershipKind.AUTOMATIC
    type_annotation: Optional[TypeNode] = None
    initializer: Optional[ExprNode] = None

@dataclass
class AssignStmt(StmtNode):
    target: ExprNode = field(default_factory=ExprNode)
    value: ExprNode = field(default_factory=ExprNode)

@dataclass
class IfStmt(StmtNode):
    condition: ExprNode = field(default_factory=ExprNode)
    then_branch: BlockStmt = field(default_factory=BlockStmt)
    else_branch: Optional[BlockStmt] = None

@dataclass
class WhileStmt(StmtNode):
    condition: ExprNode = field(default_factory=ExprNode)
    body: BlockStmt = field(default_factory=BlockStmt)

@dataclass
class ForStmt(StmtNode):
    var_name: str = ""
    iterable: ExprNode = field(default_factory=ExprNode)
    body: BlockStmt = field(default_factory=BlockStmt)

@dataclass
class ReturnStmt(StmtNode):
    value: Optional[ExprNode] = None

@dataclass
class DeferStmt(StmtNode):
    body: BlockStmt = field(default_factory=BlockStmt)

# ----------------- Declarations -----------------

@dataclass
class ParamNode(ASTNode):
    name: str = ""
    type_annotation: TypeNode = field(default_factory=TypeNode)
    ownership: OwnershipKind = OwnershipKind.AUTOMATIC

@dataclass
class FieldNode(ASTNode):
    name: str = ""
    type_annotation: TypeNode = field(default_factory=TypeNode)
    ownership: OwnershipKind = OwnershipKind.AUTOMATIC
    initializer: Optional[ExprNode] = None

@dataclass
class FuncDecl(ASTNode):
    name: str = ""
    params: List[ParamNode] = field(default_factory=list)
    return_type: TypeNode = field(default_factory=TypeNode)
    body: BlockStmt = field(default_factory=BlockStmt)
    is_method: bool = False

@dataclass
class StructDecl(ASTNode):
    name: str = ""
    fields: List[FieldNode] = field(default_factory=list)

@dataclass
class ClassDecl(ASTNode):
    name: str = ""
    default_ownership: OwnershipKind = OwnershipKind.OWNED
    fields: List[FieldNode] = field(default_factory=list)
    init_method: Optional[FuncDecl] = None
    deinit_method: Optional[BlockStmt] = None
    methods: List[FuncDecl] = field(default_factory=list)

@dataclass
class ProgramNode(ASTNode):
    declarations: List[Union[FuncDecl, StructDecl, ClassDecl, StmtNode]] = field(default_factory=list)
