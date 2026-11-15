"""
Blume Programming Language - Blume Memory Management Intermediate Representation (MIR)
Version: 1.0
"One Language. Two Memory Models. One Unified IR."
100% Pure Python Implementation
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Dict, Optional, Any
from blume.ast import OwnershipKind

class IROpcode(Enum):
    # --- Blume Unified Memory Management Operations (from Specification) ---
    BLUME_ALLOC = "blume.alloc"          # Allocate memory (domain: owned|shared, type, size)
    BLUME_OWNERSHIP = "blume.ownership"  # Establish / annotate ownership
    BLUME_RETAIN = "blume.retain"        # Increment ARC ownership count
    BLUME_RELEASE = "blume.release"      # Decrement ARC ownership count (trigger deinit if 0)
    BLUME_WEAK = "blume.weak"            # Create weak reference handle
    BLUME_WEAK_LOAD = "blume.weak.load"  # Dereference weak reference (returns nil if target dead)
    BLUME_GC_ROOT = "blume.gc.root"      # Register a GC root on the GC stack
    BLUME_GC_UNROOT = "blume.gc.unroot"  # Unregister a GC root
    BLUME_GC_TRACE = "blume.gc.trace"    # Trace reachable objects
    BLUME_GC_COLLECT = "blume.gc.collect"# Trigger / coordinate GC collection
    BLUME_BRIDGE = "blume.bridge"        # Manage cross-domain ARC <-> GC reference
    BLUME_SAFEPOINT = "blume.safepoint"  # GC coordination point

    # --- Standard Execution Instructions ---
    CONST = "const"                      # Load literal constant
    ALLOCA = "alloca"                    # Allocate stack slot
    LOAD = "load"                        # Load value from stack/variable
    STORE = "store"                      # Store value into stack/variable
    GET_FIELD = "get_field"              # Read object field
    SET_FIELD = "set_field"              # Write object field
    GET_ELEM = "get_elem"                # Array index read
    SET_ELEM = "set_elem"                # Array index write
    ARRAY_NEW = "array.new"              # Create array
    BINOP = "binop"                      # Binary operation
    UNOP = "unop"                        # Unary operation
    CALL = "call"                        # Function / method call
    BR = "br"                            # Unconditional branch
    BR_COND = "br_cond"                  # Conditional branch
    RET = "ret"                          # Return from function
    PRINT = "print"                      # Console output
    ASSERT = "assert"                    # Runtime assertion

@dataclass
class IRInstruction:
    opcode: IROpcode
    result: Optional[str] = None
    operands: List[Any] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        parts = []
        if self.result:
            parts.append(f"{self.result} = ")
        parts.append(self.opcode.value)
        if self.operands:
            parts.append(" " + ", ".join(repr(o) if isinstance(o, str) else str(o) for o in self.operands))
        if self.metadata:
            meta_str = ", ".join(f"{k}={v}" for k, v in self.metadata.items())
            parts.append(f"  // [{meta_str}]")
        return "".join(parts)

@dataclass
class IRBasicBlock:
    label: str
    instructions: List[IRInstruction] = field(default_factory=list)

    def add_instruction(self, inst: IRInstruction):
        self.instructions.append(inst)

    def __str__(self) -> str:
        lines = [f"{self.label}:"]
        for inst in self.instructions:
            lines.append(f"    {inst}")
        return "\n".join(lines)

@dataclass
class IRFunction:
    name: str
    params: List[str] = field(default_factory=list)
    return_type: str = "Void"
    blocks: List[IRBasicBlock] = field(default_factory=list)
    current_block: Optional[IRBasicBlock] = None
    next_reg_id: int = 0
    next_block_id: int = 0

    def new_reg(self, prefix: str = "%r") -> str:
        reg = f"{prefix}{self.next_reg_id}"
        self.next_reg_id += 1
        return reg

    def new_block(self, prefix: str = "bb") -> IRBasicBlock:
        name = f"{prefix}{self.next_block_id}"
        self.next_block_id += 1
        blk = IRBasicBlock(label=name)
        self.blocks.append(blk)
        return blk

    def emit(self, opcode: IROpcode, operands: Optional[List[Any]] = None, result: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> IRInstruction:
        inst = IRInstruction(
            opcode=opcode,
            result=result,
            operands=operands or [],
            metadata=metadata or {}
        )
        if self.current_block:
            self.current_block.add_instruction(inst)
        return inst

    def __str__(self) -> str:
        param_str = ", ".join(self.params)
        lines = [f"fn @{self.name}({param_str}) -> {self.return_type} {{"]
        for blk in self.blocks:
            lines.append(str(blk))
        lines.append("}")
        return "\n".join(lines)

@dataclass
class IRClassInfo:
    name: str
    domain: OwnershipKind
    fields: List[str]
    has_deinit: bool = False

@dataclass
class IRModule:
    name: str
    classes: Dict[str, IRClassInfo] = field(default_factory=dict)
    functions: Dict[str, IRFunction] = field(default_factory=dict)
    top_level_func: Optional[IRFunction] = None

    def add_function(self, fn: IRFunction):
        self.functions[fn.name] = fn

    def __str__(self) -> str:
        lines = [
            f"; ===================================================================",
            f"; Blume Unified Memory Intermediate Representation (MIR)",
            f"; Module: {self.name}",
            f"; Architecture: Hybrid ARC + GC (One Language. Two Memory Models.)",
            f"; ===================================================================",
            ""
        ]

        if self.classes:
            lines.append("; --- Declared Types ---")
            for c_name, c_info in self.classes.items():
                lines.append(f"; class {c_name} [domain: {c_info.domain.value}, fields: {', '.join(c_info.fields)}, deinit: {c_info.has_deinit}]")
            lines.append("")

        for fn in self.functions.values():
            lines.append(str(fn))
            lines.append("")

        return "\n".join(lines)
