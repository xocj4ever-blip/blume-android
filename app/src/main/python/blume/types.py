"""
Blume Programming Language - Type System
Version: 1.0
100% Pure Python Implementation
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from blume.ast import OwnershipKind

class Type:
    name: str = "Type"

    def is_reference_type(self) -> bool:
        return False

    def is_value_type(self) -> bool:
        return True

    def can_assign_to(self, target: "Type") -> bool:
        if self == target:
            return True
        if isinstance(target, OptionalType):
            if isinstance(self, NilType) or self == target.inner:
                return True
            if self.can_assign_to(target.inner):
                return True
        if isinstance(self, NilType) and isinstance(target, (OptionalType, ClassType, WeakType)):
            return True
        if isinstance(target, WeakType):
            target_inner = target.inner
            if isinstance(target_inner, OptionalType):
                target_inner = target_inner.inner
            if isinstance(self, WeakType):
                self_inner = self.inner
                if isinstance(self_inner, OptionalType):
                    self_inner = self_inner.inner
                return self_inner.can_assign_to(target_inner)
            elif isinstance(self, NilType):
                return True
            return self.can_assign_to(target_inner)
        return False

    def __str__(self) -> str:
        return self.name

@dataclass
class PrimitiveType(Type):
    name: str

    def __hash__(self):
        return hash(self.name)

    def __eq__(self, other):
        return isinstance(other, PrimitiveType) and self.name == other.name

TYPE_INT = PrimitiveType("Int")
TYPE_FLOAT = PrimitiveType("Float")
TYPE_BOOL = PrimitiveType("Bool")
TYPE_STRING = PrimitiveType("String")
TYPE_VOID = PrimitiveType("Void")

@dataclass
class NilType(Type):
    name: str = "Nil"

    def __hash__(self):
        return hash(self.name)

    def __eq__(self, other):
        return isinstance(other, NilType)

TYPE_NIL = NilType()

@dataclass
class OptionalType(Type):
    inner: Type

    @property
    def name(self) -> str:
        return f"{self.inner.name}?"

    def is_reference_type(self) -> bool:
        return self.inner.is_reference_type()

    def is_value_type(self) -> bool:
        return self.inner.is_value_type()

    def __hash__(self):
        return hash(("Optional", self.inner))

    def __eq__(self, other):
        return isinstance(other, OptionalType) and self.inner == other.inner

@dataclass
class ArrayType(Type):
    element_type: Type

    @property
    def name(self) -> str:
        return f"Array[{self.element_type.name}]"

    def is_reference_type(self) -> bool:
        return True

    def is_value_type(self) -> bool:
        return False

    def __hash__(self):
        return hash(("Array", self.element_type))

    def __eq__(self, other):
        return isinstance(other, ArrayType) and self.element_type == other.element_type

@dataclass
class StructType(Type):
    name: str
    fields: Dict[str, Type] = field(default_factory=dict)

    def is_reference_type(self) -> bool:
        return False

    def is_value_type(self) -> bool:
        return True

    def __hash__(self):
        return hash(("Struct", self.name))

    def __eq__(self, other):
        return isinstance(other, StructType) and self.name == other.name

@dataclass
class ClassType(Type):
    name: str
    ownership: OwnershipKind = OwnershipKind.OWNED
    fields: Dict[str, Type] = field(default_factory=dict)
    field_ownership: Dict[str, OwnershipKind] = field(default_factory=dict)
    methods: Dict[str, "FunctionType"] = field(default_factory=dict)
    has_deinit: bool = False
    has_explicit_init: bool = False

    def is_reference_type(self) -> bool:
        return True

    def is_value_type(self) -> bool:
        return False

    def __hash__(self):
        return hash(("Class", self.name, self.ownership))

    def __eq__(self, other):
        return isinstance(other, ClassType) and self.name == other.name

    def __str__(self) -> str:
        return f"{self.ownership.value} {self.name}"

@dataclass
class WeakType(Type):
    inner: Type

    @property
    def name(self) -> str:
        return f"weak {self.inner.name}"

    def is_reference_type(self) -> bool:
        return True

    def __hash__(self):
        return hash(("Weak", self.inner))

    def __eq__(self, other):
        return isinstance(other, WeakType) and self.inner == other.inner

@dataclass
class UnownedType(Type):
    inner: Type

    @property
    def name(self) -> str:
        return f"unowned {self.inner.name}"

    def is_reference_type(self) -> bool:
        return True

    def __hash__(self):
        return hash(("Unowned", self.inner))

    def __eq__(self, other):
        return isinstance(other, UnownedType) and self.inner == other.inner

@dataclass
class FunctionType(Type):
    param_types: List[Type] = field(default_factory=list)
    return_type: Type = field(default_factory=lambda: TYPE_VOID)

    @property
    def name(self) -> str:
        params_str = ", ".join(t.name for t in self.param_types)
        return f"({params_str}) -> {self.return_type.name}"

    def __hash__(self):
        return hash(("Function", tuple(self.param_types), self.return_type))

    def __eq__(self, other):
        return (
            isinstance(other, FunctionType) and
            self.param_types == other.param_types and
            self.return_type == other.return_type
        )
