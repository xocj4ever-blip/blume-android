"""
Blume Programming Language - Virtual Machine & MIR Interpreter
Version: 1.0
"One Language. Two Memory Models. One Unified IR."
100% Pure Python Implementation
"""

import sys
from typing import Dict, List, Optional, Any
from blume.ir import IROpcode, IRInstruction, IRBasicBlock, IRFunction, IRModule
from blume.runtime import (
    HybridMemoryCoordinator, BlumeObject, BlumeWeakRef, BlumeUnownedRef,
    BlumeRuntimeError
)
from blume.ast import OwnershipKind

class StackFrame:
    def __init__(self, fn_name: str, parent: Optional["StackFrame"] = None):
        self.fn_name = fn_name
        self.parent = parent
        self.registers: Dict[str, Any] = {}
        self.slots: Dict[str, Any] = {}

    def get_var(self, name: str) -> Any:
        if name in self.registers:
            return self.registers[name]
        if name in self.slots:
            return self.slots[name]
        return None

class BlumeVM:
    def __init__(self, module: IRModule, coordinator: Optional[HybridMemoryCoordinator] = None):
        self.module = module
        self.coordinator = coordinator or HybridMemoryCoordinator()
        self.call_stack: List[StackFrame] = []
        self.output_buffer: List[str] = []
        self.capture_output: bool = False

    def execute(self, entry_func_name: str = "__blume_main__") -> Any:
        if entry_func_name not in self.module.functions:
            raise BlumeRuntimeError(f"Entry function '{entry_func_name}' not found in IR module")

        entry_fn = self.module.functions[entry_func_name]
        return self._execute_function(entry_fn, [])

    def _execute_function(self, fn: IRFunction, args: List[Any]) -> Any:
        frame = StackFrame(fn.name, self.call_stack[-1] if self.call_stack else None)
        self.call_stack.append(frame)

        # Bind params
        for i, param_name in enumerate(fn.params):
            val = args[i] if i < len(args) else None
            frame.registers[param_name] = val

        # Map block labels
        block_map = {b.label: b for b in fn.blocks}
        if not fn.blocks:
            self.call_stack.pop()
            return None

        curr_block = fn.blocks[0]
        pc = 0

        while True:
            if pc >= len(curr_block.instructions):
                # Fallthrough or return
                break

            inst = curr_block.instructions[pc]
            pc += 1

            op = inst.opcode
            res = inst.result
            ops = inst.operands

            if op == IROpcode.CONST:
                val = ops[0]
                frame.registers[res] = val

            elif op == IROpcode.ALLOCA:
                slot_name = res
                frame.slots[slot_name] = None

            elif op == IROpcode.LOAD:
                slot_name = ops[0]
                val = frame.slots.get(slot_name)
                # Unwrap weak ref if target deallocated
                if isinstance(val, BlumeWeakRef):
                    val = val.get()
                frame.registers[res] = val

            elif op == IROpcode.STORE:
                val_reg = ops[0]
                slot_name = ops[1]
                val = self._resolve_val(val_reg, frame)
                frame.slots[slot_name] = val

            elif op == IROpcode.BLUME_ALLOC:
                domain_str = ops[0]
                domain = OwnershipKind.from_str(domain_str)
                class_name = ops[1]
                fields = ops[2] if len(ops) > 2 else []

                # Link deinit callback if deinit function exists in module
                deinit_fn_name = f"{class_name}__deinit"
                deinit_callback = None
                if deinit_fn_name in self.module.functions:
                    ir_deinit_fn = self.module.functions[deinit_fn_name]
                    deinit_callback = (lambda target_fn: lambda obj: self._execute_function(target_fn, [obj]))(ir_deinit_fn)

                obj = self.coordinator.allocate(
                    class_name=class_name,
                    domain=domain,
                    fields=fields,
                    deinit_fn=deinit_callback
                )
                frame.registers[res] = obj

            elif op == IROpcode.BLUME_OWNERSHIP:
                # Metadata instruction
                pass

            elif op == IROpcode.BLUME_RETAIN:
                obj = self._resolve_val(ops[0], frame)
                self.coordinator.retain(obj)

            elif op == IROpcode.BLUME_RELEASE:
                obj = self._resolve_val(ops[0], frame)
                self.coordinator.release(obj)

            elif op == IROpcode.BLUME_WEAK:
                obj = self._resolve_val(ops[0], frame)
                wref = self.coordinator.create_weak_ref(obj)
                frame.registers[res] = wref

            elif op == IROpcode.BLUME_WEAK_LOAD:
                wref = self._resolve_val(ops[0], frame)
                if isinstance(wref, BlumeWeakRef):
                    frame.registers[res] = wref.get()
                else:
                    frame.registers[res] = wref

            elif op == IROpcode.BLUME_GC_ROOT:
                slot_name = ops[0]
                # Register root slot getter
                self.coordinator.register_gc_root_slot(
                    slot_name,
                    lambda s=slot_name: frame.slots.get(s)
                )

            elif op == IROpcode.BLUME_GC_UNROOT:
                slot_name = ops[0]
                self.coordinator.unregister_gc_root_slot(slot_name)

            elif op == IROpcode.BLUME_GC_COLLECT:
                swept = self.coordinator.collect_garbage()
                if res:
                    frame.registers[res] = swept

            elif op == IROpcode.BLUME_BRIDGE:
                source_obj = self._resolve_val(ops[0], frame)
                field_name = ops[1]
                target_val = self._resolve_val(ops[2], frame)
                self.coordinator.bridge_reference(source_obj, field_name, target_val)

            elif op == IROpcode.BLUME_SAFEPOINT:
                # GC coordination checkpoint
                if self.coordinator.alloc_counter >= self.coordinator.gc_threshold:
                    self.coordinator.collect_garbage()
                    self.coordinator.alloc_counter = 0

            elif op == IROpcode.GET_FIELD:
                obj = self._resolve_val(ops[0], frame)
                field_name = ops[1]
                if isinstance(obj, BlumeWeakRef):
                    obj = obj.get()
                if isinstance(obj, BlumeUnownedRef):
                    obj = obj.get()
                if isinstance(obj, BlumeObject):
                    val = obj.fields.get(field_name)
                    if isinstance(val, BlumeWeakRef):
                        val = val.get()
                    elif isinstance(val, BlumeUnownedRef):
                        val = val.get()
                    frame.registers[res] = val
                elif isinstance(obj, dict):
                    val = obj.get(field_name)
                    if isinstance(val, BlumeWeakRef):
                        val = val.get()
                    frame.registers[res] = val
                else:
                    frame.registers[res] = None

            elif op == IROpcode.SET_FIELD:
                obj = self._resolve_val(ops[0], frame)
                field_name = ops[1]
                val = self._resolve_val(ops[2], frame)
                if isinstance(obj, BlumeWeakRef):
                    obj = obj.get()
                if isinstance(obj, BlumeUnownedRef):
                    obj = obj.get()
                if isinstance(obj, BlumeObject):
                    obj.fields[field_name] = val
                elif isinstance(obj, dict):
                    obj[field_name] = val

            elif op == IROpcode.GET_ELEM:
                arr = self._resolve_val(ops[0], frame)
                idx = self._resolve_val(ops[1], frame)
                if isinstance(arr, list) and isinstance(idx, int):
                    if 0 <= idx < len(arr):
                        frame.registers[res] = arr[idx]
                    else:
                        raise BlumeRuntimeError(f"Array index out of bounds: index {idx}, len {len(arr)}")
                else:
                    frame.registers[res] = None

            elif op == IROpcode.SET_ELEM:
                arr = self._resolve_val(ops[0], frame)
                idx = self._resolve_val(ops[1], frame)
                val = self._resolve_val(ops[2], frame)
                if isinstance(arr, list) and isinstance(idx, int):
                    if 0 <= idx < len(arr):
                        arr[idx] = val
                    else:
                        raise BlumeRuntimeError(f"Array index out of bounds: index {idx}, len {len(arr)}")

            elif op == IROpcode.ARRAY_NEW:
                elems = [self._resolve_val(e, frame) for e in ops]
                frame.registers[res] = list(elems)

            elif op == IROpcode.BINOP:
                bin_op = ops[0]
                left = self._resolve_val(ops[1], frame)
                right = self._resolve_val(ops[2], frame)
                val = self._eval_binop(bin_op, left, right)
                frame.registers[res] = val

            elif op == IROpcode.UNOP:
                un_op = ops[0]
                operand = self._resolve_val(ops[1], frame)
                if un_op == "-":
                    frame.registers[res] = -operand
                elif un_op in ("!", "not"):
                    frame.registers[res] = not operand

            elif op == IROpcode.CALL:
                callee = ops[0]
                call_args = [self._resolve_val(a, frame) for a in ops[1:]]

                # Special built-in dispatches
                if callee == "__blume_get_retain_count__":
                    target = call_args[0]
                    rc = target.retain_count if isinstance(target, BlumeObject) and target.domain == OwnershipKind.OWNED else -1
                    if res:
                        frame.registers[res] = rc
                elif callee == "__blume_get_domain__":
                    target = call_args[0]
                    dom = target.domain.value if isinstance(target, BlumeObject) else "value"
                    if res:
                        frame.registers[res] = dom
                elif callee == "__blume_heap_stats__":
                    self.coordinator.print_heap_stats()
                elif callee.startswith("__method_"):
                    # Method call e.g. obj.len(), obj.push(x), obj.pop()
                    method_name = callee[9:-2]
                    target_obj = call_args[0]
                    m_args = call_args[1:]
                    if isinstance(target_obj, list):
                        if method_name == "len":
                            frame.registers[res] = len(target_obj)
                        elif method_name == "push":
                            target_obj.append(m_args[0])
                        elif method_name == "pop":
                            frame.registers[res] = target_obj.pop() if target_obj else None
                    elif isinstance(target_obj, BlumeObject):
                        full_fn_name = f"{target_obj.class_name}__{method_name}"
                        if full_fn_name in self.module.functions:
                            ret_val = self._execute_function(self.module.functions[full_fn_name], [target_obj] + m_args)
                            if res:
                                frame.registers[res] = ret_val
                elif (callee_name := callee.lstrip("%") if isinstance(callee, str) else callee) in self.module.functions:
                    ret_val = self._execute_function(self.module.functions[callee_name], call_args)
                    if res:
                        frame.registers[res] = ret_val
                else:
                    if res and res not in frame.registers:
                        frame.registers[res] = None

            elif op == IROpcode.BR:
                target_label = ops[0]
                curr_block = block_map[target_label]
                pc = 0

            elif op == IROpcode.BR_COND:
                cond_val = self._resolve_val(ops[0], frame)
                then_label = ops[1]
                else_label = ops[2]
                curr_block = block_map[then_label] if cond_val else block_map[else_label]
                pc = 0

            elif op == IROpcode.RET:
                ret_val = self._resolve_val(ops[0], frame) if ops and ops[0] is not None else None
                self.call_stack.pop()
                return ret_val

            elif op == IROpcode.PRINT:
                vals = [self._format_val(self._resolve_val(a, frame)) for a in ops]
                text = " ".join(vals)
                if self.capture_output:
                    self.output_buffer.append(text)
                else:
                    print(text)

            elif op == IROpcode.ASSERT:
                cond = self._resolve_val(ops[0], frame)
                msg = self._resolve_val(ops[1], frame) if len(ops) > 1 else "Assertion failed"
                if not cond:
                    raise BlumeRuntimeError(f"Assertion Error: {msg}")

        self.call_stack.pop()
        return None

    def _resolve_val(self, val_or_reg: Any, frame: StackFrame) -> Any:
        if isinstance(val_or_reg, str):
            if val_or_reg.startswith("%"):
                if val_or_reg in frame.registers:
                    return frame.registers[val_or_reg]
                if val_or_reg in frame.slots:
                    return frame.slots[val_or_reg]
        return val_or_reg

    def _eval_binop(self, op: str, left: Any, right: Any) -> Any:
        if isinstance(left, BlumeWeakRef):
            left = left.get()
        if isinstance(right, BlumeWeakRef):
            right = right.get()
        if op == "+":
            if isinstance(left, str) or isinstance(right, str):
                return f"{self._format_val(left)}{self._format_val(right)}"
            return left + right
        elif op == "-":
            return left - right
        elif op == "*":
            return left * right
        elif op == "/":
            return left / right if isinstance(left, float) or isinstance(right, float) else left // right
        elif op == "%":
            return left % right
        elif op == "==":
            return left == right
        elif op == "!=":
            return left != right
        elif op == "<":
            return left < right
        elif op == "<=":
            return left <= right
        elif op == ">":
            return left > right
        elif op == ">=":
            return left >= right
        elif op in ("&&", "and"):
            return bool(left and right)
        elif op in ("||", "or"):
            return bool(left or right)
        return None

    def _format_val(self, val: Any) -> str:
        if val is None:
            return "nil"
        if isinstance(val, bool):
            return "true" if val else "false"
        if isinstance(val, BlumeObject):
            return repr(val)
        if isinstance(val, BlumeWeakRef):
            return repr(val)
        if isinstance(val, BlumeUnownedRef):
            return repr(val)
        return str(val)
