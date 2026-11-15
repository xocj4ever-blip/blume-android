package com.blume.vm

import com.blume.compiler.ast.OwnershipKind
import com.blume.compiler.ir.*
import com.blume.runtime.*

class StackFrame(val fnName: String, val parent: StackFrame? = null) {
    val registers = mutableMapOf<String, Any?>()
    val slots = mutableMapOf<String, Any?>()

    fun getVar(name: String): Any? {
        if (registers.containsKey(name)) return registers[name]
        if (slots.containsKey(name)) return slots[name]
        return null
    }
}

class BlumeVM(
    val module: IRModule,
    val coordinator: HybridMemoryCoordinator = HybridMemoryCoordinator(),
    val onOutput: ((String) -> Unit)? = null
) {
    private val callStack = mutableListOf<StackFrame>()
    val outputBuffer = mutableListOf<String>()

    fun execute(entryFuncName: String = "__blume_main__"): Any? {
        val entryFn = module.functions[entryFuncName]
            ?: throw BlumeRuntimeException("Entry function '$entryFuncName' not found in IR module")

        return executeFunction(entryFn, emptyList())
    }

    private fun executeFunction(fn: IRFunction, args: List<Any?>): Any? {
        val frame = StackFrame(fn.name, callStack.lastOrNull())
        callStack.add(frame)

        // Bind params
        for (i in fn.params.indices) {
            val paramName = fn.params[i]
            frame.registers[paramName] = if (i < args.size) args[i] else null
        }

        if (fn.blocks.isEmpty()) {
            callStack.removeLast()
            return null
        }

        val blockMap = fn.blocks.associateBy { it.label }
        var currBlock = fn.blocks[0]
        var pc = 0

        while (true) {
            if (pc >= currBlock.instructions.size) {
                break
            }

            val inst = currBlock.instructions[pc++]
            val op = inst.opcode
            val res = inst.result
            val ops = inst.operands

            when (op) {
                IROpcode.CONST -> {
                    res?.let { frame.registers[it] = ops.getOrNull(0) }
                }
                IROpcode.ALLOCA -> {
                    res?.let { frame.slots[it] = null }
                }
                IROpcode.LOAD -> {
                    val slotName = ops[0] as String
                    var v = frame.slots[slotName]
                    if (v is BlumeWeakRef) v = v.get()
                    res?.let { frame.registers[it] = v }
                }
                IROpcode.STORE -> {
                    val valReg = ops[0]
                    val slotName = ops[1] as String
                    val v = resolveVal(valReg, frame)
                    frame.slots[slotName] = v
                }
                IROpcode.BLUME_ALLOC -> {
                    val domainStr = ops[0] as String
                    val domain = OwnershipKind.fromString(domainStr)
                    val className = ops[1] as String
                    @Suppress("UNCHECKED_CAST")
                    val fieldNames = (ops.getOrNull(2) as? List<String>) ?: emptyList()

                    val deinitFnName = "${className}__deinit"
                    val deinitCallback: ((BlumeObject) -> Unit)? = if (module.functions.containsKey(deinitFnName)) {
                        val irDeinitFn = module.functions[deinitFnName]!!
                        { obj -> executeFunction(irDeinitFn, listOf(obj)) }
                    } else null

                    val obj = coordinator.allocate(
                        className = className,
                        domain = domain,
                        fields = fieldNames,
                        deinitFn = deinitCallback
                    )
                    res?.let { frame.registers[it] = obj }
                }
                IROpcode.BLUME_OWNERSHIP -> {
                    // Metadata
                }
                IROpcode.BLUME_RETAIN -> {
                    val obj = resolveVal(ops[0], frame)
                    coordinator.retain(obj)
                }
                IROpcode.BLUME_RELEASE -> {
                    val obj = resolveVal(ops[0], frame)
                    coordinator.release(obj)
                }
                IROpcode.BLUME_WEAK -> {
                    val obj = resolveVal(ops[0], frame)
                    val wref = coordinator.createWeakRef(obj)
                    res?.let { frame.registers[it] = wref }
                }
                IROpcode.BLUME_WEAK_LOAD -> {
                    val wref = resolveVal(ops[0], frame)
                    val v = if (wref is BlumeWeakRef) wref.get() else wref
                    res?.let { frame.registers[it] = v }
                }
                IROpcode.BLUME_GC_ROOT -> {
                    val slotName = ops[0] as String
                    coordinator.registerGcRootSlot(slotName) { frame.slots[slotName] }
                }
                IROpcode.BLUME_GC_UNROOT -> {
                    val slotName = ops[0] as String
                    coordinator.unregisterGcRootSlot(slotName)
                }
                IROpcode.BLUME_GC_COLLECT -> {
                    val swept = coordinator.collectGarbage()
                    res?.let { frame.registers[it] = swept.toLong() }
                }
                IROpcode.BLUME_BRIDGE -> {
                    val src = resolveVal(ops[0], frame)
                    val fld = ops[1] as String
                    val tgt = resolveVal(ops[2], frame)
                    coordinator.bridgeReference(src, fld, tgt)
                }
                IROpcode.BLUME_SAFEPOINT -> {
                    if (coordinator.allocCounter >= coordinator.gcThreshold) {
                        coordinator.collectGarbage()
                        coordinator.allocCounter = 0
                    }
                }
                IROpcode.GET_FIELD -> {
                    var obj = resolveVal(ops[0], frame)
                    val fldName = ops[1] as String
                    if (obj is BlumeWeakRef) obj = obj.get()
                    if (obj is BlumeUnownedRef) obj = obj.get()

                    val v = when (obj) {
                        is BlumeObject -> {
                            var f = obj.fields[fldName]
                            if (f is BlumeWeakRef) f = f.get()
                            if (f is BlumeUnownedRef) f = f.get()
                            f
                        }
                        is Map<*, *> -> obj[fldName]
                        else -> null
                    }
                    res?.let { frame.registers[it] = v }
                }
                IROpcode.SET_FIELD -> {
                    var obj = resolveVal(ops[0], frame)
                    val fldName = ops[1] as String
                    val v = resolveVal(ops[2], frame)
                    if (obj is BlumeWeakRef) obj = obj.get()
                    if (obj is BlumeUnownedRef) obj = obj.get()

                    if (obj is BlumeObject) {
                        obj.fields[fldName] = v
                    } else if (obj is MutableMap<*, *>) {
                        @Suppress("UNCHECKED_CAST")
                        (obj as MutableMap<Any?, Any?>)[fldName] = v
                    }
                }
                IROpcode.GET_ELEM -> {
                    val arr = resolveVal(ops[0], frame)
                    val idx = (resolveVal(ops[1], frame) as? Number)?.toInt() ?: 0
                    if (arr is List<*> && idx in 0 until arr.size) {
                        res?.let { frame.registers[it] = arr[idx] }
                    } else {
                        res?.let { frame.registers[it] = null }
                    }
                }
                IROpcode.SET_ELEM -> {
                    val arr = resolveVal(ops[0], frame)
                    val idx = (resolveVal(ops[1], frame) as? Number)?.toInt() ?: 0
                    val v = resolveVal(ops[2], frame)
                    if (arr is MutableList<*> && idx in 0 until arr.size) {
                        @Suppress("UNCHECKED_CAST")
                        (arr as MutableList<Any?>)[idx] = v
                    }
                }
                IROpcode.ARRAY_NEW -> {
                    val elems = ops.map { resolveVal(it, frame) }.toMutableList()
                    res?.let { frame.registers[it] = elems }
                }
                IROpcode.BINOP -> {
                    val binOp = ops[0] as String
                    val left = resolveVal(ops[1], frame)
                    val right = resolveVal(ops[2], frame)
                    val eval = evalBinop(binOp, left, right)
                    res?.let { frame.registers[it] = eval }
                }
                IROpcode.UNOP -> {
                    val unOp = ops[0] as String
                    val opVal = resolveVal(ops[1], frame)
                    val eval = when (unOp) {
                        "-" -> when (opVal) {
                            is Long -> -opVal
                            is Double -> -opVal
                            is Int -> -opVal.toLong()
                            else -> 0L
                        }
                        "!", "not" -> !(opVal as? Boolean ?: false)
                        else -> opVal
                    }
                    res?.let { frame.registers[it] = eval }
                }
                IROpcode.CALL -> {
                    val callee = ops[0] as String
                    val callArgs = ops.drop(1).map { resolveVal(it, frame) }

                    when {
                        callee == "__blume_get_retain_count__" -> {
                            val target = callArgs.firstOrNull()
                            val rc = if (target is BlumeObject && target.domain == OwnershipKind.OWNED) {
                                target.retainCount.toLong()
                            } else -1L
                            res?.let { frame.registers[it] = rc }
                        }
                        callee == "__blume_get_domain__" -> {
                            val target = callArgs.firstOrNull()
                            val dom = if (target is BlumeObject) target.domain.keyword else "value"
                            res?.let { frame.registers[it] = dom }
                        }
                        callee == "__blume_heap_stats__" -> {
                            val statsStr = coordinator.formatStats()
                            emitOutput(statsStr)
                        }
                        callee.startsWith("__method_") -> {
                            val methodName = callee.removePrefix("__method_").removeSuffix("__")
                            val targetObj = callArgs.firstOrNull()
                            val mArgs = callArgs.drop(1)

                            when (targetObj) {
                                is MutableList<*> -> {
                                    when (methodName) {
                                        "len" -> res?.let { frame.registers[it] = targetObj.size.toLong() }
                                        "push" -> {
                                            @Suppress("UNCHECKED_CAST")
                                            (targetObj as MutableList<Any?>).add(mArgs.firstOrNull())
                                        }
                                        "pop" -> {
                                            val last = if (targetObj.isNotEmpty()) {
                                                @Suppress("UNCHECKED_CAST")
                                                (targetObj as MutableList<Any?>).removeLast()
                                            } else null
                                            res?.let { frame.registers[it] = last }
                                        }
                                    }
                                }
                                is BlumeObject -> {
                                    val fullFnName = "${targetObj.className}__$methodName"
                                    if (module.functions.containsKey(fullFnName)) {
                                        val retVal = executeFunction(module.functions[fullFnName]!!, listOf(targetObj) + mArgs)
                                        res?.let { frame.registers[it] = retVal }
                                    }
                                }
                            }
                        }
                        module.functions.containsKey(callee.trimStart('%')) -> {
                            val fnName = callee.trimStart('%')
                            val retVal = executeFunction(module.functions[fnName]!!, callArgs)
                            res?.let { frame.registers[it] = retVal }
                        }
                        else -> {
                            res?.let { if (!frame.registers.containsKey(it)) frame.registers[it] = null }
                        }
                    }
                }
                IROpcode.BR -> {
                    val targetLabel = ops[0] as String
                    currBlock = blockMap[targetLabel] ?: break
                    pc = 0
                }
                IROpcode.BR_COND -> {
                    val cond = resolveVal(ops[0], frame) as? Boolean ?: false
                    val thenLabel = ops[1] as String
                    val elseLabel = ops[2] as String
                    val targetLabel = if (cond) thenLabel else elseLabel
                    currBlock = blockMap[targetLabel] ?: break
                    pc = 0
                }
                IROpcode.RET -> {
                    val retVal = if (ops.isNotEmpty()) resolveVal(ops[0], frame) else null
                    callStack.removeLast()
                    return retVal
                }
                IROpcode.PRINT -> {
                    val vals = ops.map { formatVal(resolveVal(it, frame)) }
                    val text = vals.joinToString(" ")
                    emitOutput(text)
                }
                IROpcode.ASSERT -> {
                    val cond = resolveVal(ops[0], frame) as? Boolean ?: false
                    val msg = if (ops.size > 1) resolveVal(ops[1], frame)?.toString() ?: "Assertion failed" else "Assertion failed"
                    if (!cond) throw BlumeRuntimeException("Assertion Error: $msg")
                }
                else -> {}
            }
        }

        callStack.removeLast()
        return null
    }

    private fun emitOutput(text: String) {
        outputBuffer.add(text)
        onOutput?.invoke(text)
    }

    private fun resolveVal(vOrReg: Any?, frame: StackFrame): Any? {
        if (vOrReg is String && vOrReg.startsWith("%")) {
            if (frame.registers.containsKey(vOrReg)) return frame.registers[vOrReg]
            if (frame.slots.containsKey(vOrReg)) return frame.slots[vOrReg]
        }
        return vOrReg
    }

    private fun evalBinop(op: String, leftRaw: Any?, rightRaw: Any?): Any? {
        var left = leftRaw
        var right = rightRaw
        if (left is BlumeWeakRef) left = left.get()
        if (right is BlumeWeakRef) right = right.get()

        return when (op) {
            "+" -> {
                if (left is String || right is String) {
                    "${formatVal(left)}${formatVal(right)}"
                } else if (left is Double || right is Double) {
                    ((left as? Number)?.toDouble() ?: 0.0) + ((right as? Number)?.toDouble() ?: 0.0)
                } else {
                    ((left as? Number)?.toLong() ?: 0L) + ((right as? Number)?.toLong() ?: 0L)
                }
            }
            "-" -> {
                if (left is Double || right is Double) {
                    ((left as? Number)?.toDouble() ?: 0.0) - ((right as? Number)?.toDouble() ?: 0.0)
                } else {
                    ((left as? Number)?.toLong() ?: 0L) - ((right as? Number)?.toLong() ?: 0L)
                }
            }
            "*" -> {
                if (left is Double || right is Double) {
                    ((left as? Number)?.toDouble() ?: 0.0) * ((right as? Number)?.toDouble() ?: 0.0)
                } else {
                    ((left as? Number)?.toLong() ?: 0L) * ((right as? Number)?.toLong() ?: 0L)
                }
            }
            "/" -> {
                val r = (right as? Number)?.toDouble() ?: 1.0
                if (left is Double || right is Double) {
                    ((left as? Number)?.toDouble() ?: 0.0) / r
                } else {
                    val l = (left as? Number)?.toLong() ?: 0L
                    val rL = (right as? Number)?.toLong() ?: 1L
                    if (rL == 0L) 0L else l / rL
                }
            }
            "%" -> {
                val l = (left as? Number)?.toLong() ?: 0L
                val r = (right as? Number)?.toLong() ?: 1L
                if (r == 0L) 0L else l % r
            }
            "==" -> left == right
            "!=" -> left != right
            "<" -> ((left as? Number)?.toDouble() ?: 0.0) < ((right as? Number)?.toDouble() ?: 0.0)
            "<=" -> ((left as? Number)?.toDouble() ?: 0.0) <= ((right as? Number)?.toDouble() ?: 0.0)
            ">" -> ((left as? Number)?.toDouble() ?: 0.0) > ((right as? Number)?.toDouble() ?: 0.0)
            ">=" -> ((left as? Number)?.toDouble() ?: 0.0) >= ((right as? Number)?.toDouble() ?: 0.0)
            "&&" -> (left as? Boolean ?: false) && (right as? Boolean ?: false)
            "||" -> (left as? Boolean ?: false) || (right as? Boolean ?: false)
            else -> null
        }
    }

    private fun formatVal(v: Any?): String {
        return when (v) {
            null -> "nil"
            is Boolean -> if (v) "true" else "false"
            is BlumeObject -> v.toString()
            is BlumeWeakRef -> v.toString()
            is List<*> -> "[${v.joinToString(", ") { formatVal(it) }}]"
            else -> v.toString()
        }
    }
}
