"""
Blume Programming Language - LLVM IR Lowering & Code Generator
Version: 1.0
"One Language. Two Memory Models. One Unified IR."
100% Pure Python Implementation
"""

from typing import List, Dict, Optional, Any
from blume.ir import IROpcode, IRInstruction, IRBasicBlock, IRFunction, IRModule

class LLVMEmitter:
    def __init__(self, module: IRModule):
        self.module = module
        self.str_constants: Dict[str, str] = {}
        self.str_counter = 0

    def emit(self) -> str:
        lines: List[str] = [
            "; ModuleID = 'blume_module'",
            f"; Source Language: Blume 1.0 (Hybrid ARC + GC)",
            f"; Module: {self.module.name}",
            'source_filename = "blume_source.blume"',
            'target datalayout = "e-m:e-p270:32:32-p271:32:32-p272:64:64-i64:64-f80:128-n8:16:32:64-S128"',
            'target triple = "x86_64-unknown-linux-gnu"',
            "",
            "; --- Blume Unified Memory Headers ---",
            "%struct.BlumeObject = type { i32, i32, i32, i8* } ; { id, domain, retain_count, payload }",
            "",
            "; --- Runtime Function Declarations ---",
            "declare i8* @malloc(i64)",
            "declare void @free(i8*)",
            "declare i32 @printf(i8*, ...)",
            "declare void @blume_arc_retain(i8*)",
            "declare void @blume_arc_release(i8*)",
            "declare void @blume_gc_register_root(i8**)",
            "declare void @blume_gc_unregister_root(i8**)",
            "declare i32 @blume_gc_collect()",
            "declare void @blume_bridge_reference(i8*, i8*, i8*)",
            "declare void @blume_safepoint()",
            "",
            "; --- Global String Constants ---",
            '@.str.int_fmt = private unnamed_addr constant [4 x i8] c"%d\\0A\\00", align 1',
            '@.str.str_fmt = private unnamed_addr constant [4 x i8] c"%s\\0A\\00", align 1',
            '@.str.nil_str = private unnamed_addr constant [4 x i8] c"nil\\00", align 1',
            ""
        ]

        # Declare class struct types
        for c_name, c_info in self.module.classes.items():
            field_types = ", ".join(["i8*"] * len(c_info.fields))
            if not field_types:
                field_types = "i8"
            lines.append(f"%struct.{c_name} = type {{ %struct.BlumeObject, {field_types} }}")
        lines.append("")

        # Emit functions
        for fn in self.module.functions.values():
            lines.append(self._emit_function(fn))
            lines.append("")

        # Emit native C entry point `main`
        lines.extend([
            "; --- Native Main Entry Point ---",
            "define i32 @main(i32 %argc, i8** %argv) {",
            "entry:",
            "    call void @__blume_main__()",
            "    ret i32 0",
            "}",
            ""
        ])

        return "\n".join(lines)

    def _emit_function(self, fn: IRFunction) -> str:
        param_defs = []
        for p in fn.params:
            param_defs.append(f"i8* {p}")
        params_str = ", ".join(param_defs)

        ret_type = "void" if fn.return_type in ("Void", "void") else "i8*"
        if fn.name == "__blume_main__":
            ret_type = "void"

        lines = [f"define {ret_type} @{fn.name}({params_str}) {{"]

        for blk in fn.blocks:
            lines.append(f"{blk.label}:")
            for inst in blk.instructions:
                lines.append(self._emit_instruction(inst))

        lines.append("}")
        return "\n".join(lines)

    def _emit_instruction(self, inst: IRInstruction) -> str:
        op = inst.opcode
        res = inst.result
        ops = inst.operands

        if op == IROpcode.CONST:
            val = ops[0]
            if val is None:
                return f"    {res} = bitcast i8* null to i8*"
            elif isinstance(val, bool):
                b_val = 1 if val else 0
                return f"    {res} = zext i1 {b_val} to i64"
            elif isinstance(val, int):
                return f"    {res} = add i64 0, {val}"
            elif isinstance(val, str):
                # String constant
                return f"    {res} = bitcast [4 x i8]* @.str.str_fmt to i8*"
            return f"    {res} = bitcast i8* null to i8*"

        elif op == IROpcode.ALLOCA:
            return f"    {res} = alloca i8*, align 8"

        elif op == IROpcode.LOAD:
            slot = ops[0]
            return f"    {res} = load i8*, i8** {slot}, align 8"

        elif op == IROpcode.STORE:
            val_reg = ops[0]
            slot = ops[1]
            return f"    store i8* {val_reg}, i8** {slot}, align 8"

        elif op == IROpcode.BLUME_ALLOC:
            class_name = ops[1]
            return f"    {res} = call i8* @malloc(i64 64) ; allocate {class_name}"

        elif op == IROpcode.BLUME_RETAIN:
            obj = ops[0]
            return f"    call void @blume_arc_retain(i8* {obj})"

        elif op == IROpcode.BLUME_RELEASE:
            obj = ops[0]
            return f"    call void @blume_arc_release(i8* {obj})"

        elif op == IROpcode.BLUME_GC_ROOT:
            slot = ops[0]
            return f"    call void @blume_gc_register_root(i8** {slot})"

        elif op == IROpcode.BLUME_GC_UNROOT:
            slot = ops[0]
            return f"    call void @blume_gc_unregister_root(i8** {slot})"

        elif op == IROpcode.BLUME_GC_COLLECT:
            return f"    {res} = call i32 @blume_gc_collect()"

        elif op == IROpcode.BLUME_BRIDGE:
            return f"    call void @blume_bridge_reference(i8* {ops[0]}, i8* null, i8* {ops[2]})"

        elif op == IROpcode.BLUME_SAFEPOINT:
            return f"    call void @blume_safepoint()"

        elif op == IROpcode.BR:
            target = ops[0]
            return f"    br label %{target}"

        elif op == IROpcode.BR_COND:
            cond = ops[0]
            then_l = ops[1]
            else_l = ops[2]
            return f"    br i1 {cond}, label %{then_l}, label %{else_l}"

        elif op == IROpcode.RET:
            val = ops[0] if ops and ops[0] is not None else None
            if val is None:
                return "    ret void"
            return f"    ret i8* {val}"

        elif op == IROpcode.PRINT:
            first_arg = ops[0] if ops else "null"
            return f"    call i32 (i8*, ...) @printf(i8* bitcast ([4 x i8]* @.str.str_fmt to i8*), i8* {first_arg})"

        elif op == IROpcode.CALL:
            callee = ops[0]
            args_str = ", ".join([f"i8* {a}" for a in ops[1:]])
            if res:
                return f"    {res} = call i8* @{callee}({args_str})"
            return f"    call void @{callee}({args_str})"

        elif op == IROpcode.BINOP:
            b_op = ops[0]
            l_val = ops[1]
            r_val = ops[2]
            op_map = {
                "+": "add i64",
                "-": "sub i64",
                "*": "mul i64",
                "/": "sdiv i64",
                "%": "srem i64",
                "==": "icmp eq i64",
                "!=": "icmp ne i64",
                "<": "icmp slt i64",
                "<=": "icmp sle i64",
                ">": "icmp sgt i64",
                ">=": "icmp sge i64",
                "&&": "and i1",
                "||": "or i1"
            }
            llvm_op = op_map.get(b_op, "add i64")
            return f"    {res} = {llvm_op} {l_val}, {r_val}"
