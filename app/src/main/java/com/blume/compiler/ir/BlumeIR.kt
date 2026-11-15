package com.blume.compiler.ir

enum class IROpcode(val value: String) {
    // Blume Unified Memory Management Operations
    BLUME_ALLOC("blume.alloc"),
    BLUME_OWNERSHIP("blume.ownership"),
    BLUME_RETAIN("blume.retain"),
    BLUME_RELEASE("blume.release"),
    BLUME_WEAK("blume.weak"),
    BLUME_WEAK_LOAD("blume.weak.load"),
    BLUME_GC_ROOT("blume.gc.root"),
    BLUME_GC_UNROOT("blume.gc.unroot"),
    BLUME_GC_TRACE("blume.gc.trace"),
    BLUME_GC_COLLECT("blume.gc.collect"),
    BLUME_BRIDGE("blume.bridge"),
    BLUME_SAFEPOINT("blume.safepoint"),

    // Standard Execution Instructions
    CONST("const"),
    ALLOCA("alloca"),
    LOAD("load"),
    STORE("store"),
    GET_FIELD("get_field"),
    SET_FIELD("set_field"),
    GET_ELEM("get_elem"),
    SET_ELEM("set_elem"),
    ARRAY_NEW("array.new"),
    BINOP("binop"),
    UNOP("unop"),
    CALL("call"),
    BR("br"),
    BR_COND("br_cond"),
    RET("ret"),
    PRINT("print"),
    ASSERT("assert");

    override fun toString(): String = value
}

data class IRInstruction(
    val opcode: IROpcode,
    val result: String? = null,
    val operands: List<Any?> = emptyList(),
    val metadata: Map<String, Any> = emptyMap()
) {
    override fun toString(): String {
        val sb = StringBuilder()
        if (result != null) {
            sb.append("$result = ")
        }
        sb.append(opcode.value)
        if (operands.isNotEmpty()) {
            sb.append(" ")
            sb.append(operands.joinToString(", ") { o ->
                if (o is String) "\"$o\"" else o.toString()
            })
        }
        if (metadata.isNotEmpty()) {
            sb.append("  // [")
            sb.append(metadata.entries.joinToString(", ") { "${it.key}=${it.value}" })
            sb.append("]")
        }
        return sb.toString()
    }
}

data class IRBasicBlock(
    val label: String,
    val instructions: MutableList<IRInstruction> = mutableListOf()
) {
    fun addInstruction(inst: IRInstruction) {
        instructions.add(inst)
    }

    override fun toString(): String {
        val sb = StringBuilder()
        sb.append("$label:\n")
        for (inst in instructions) {
            sb.append("    $inst\n")
        }
        return sb.toString()
    }
}

class IRFunction(
    val name: String,
    val params: List<String> = emptyList(),
    val returnType: String = "Void"
) {
    val blocks = mutableListOf<IRBasicBlock>()
    var currentBlock: IRBasicBlock? = null
    private var nextRegId = 0
    private var nextBlockId = 0

    fun newReg(prefix: String = "%r"): String = "$prefix${nextRegId++}"

    fun newBlock(prefix: String = "bb"): IRBasicBlock {
        val blk = IRBasicBlock("$prefix${nextBlockId++}")
        blocks.add(blk)
        return blk
    }

    fun emit(inst: IRInstruction) {
        currentBlock?.addInstruction(inst)
    }

    override fun toString(): String {
        val sb = StringBuilder()
        sb.append("define @$name(${params.joinToString(", ")}) -> $returnType {\n")
        for (b in blocks) {
            sb.append(b.toString())
        }
        sb.append("}\n")
        return sb.toString()
    }
}

class IRModule(val name: String = "blume_module") {
    val functions = mutableMapOf<String, IRFunction>()

    fun addFunction(fn: IRFunction) {
        functions[fn.name] = fn
    }

    override fun toString(): String {
        val sb = StringBuilder()
        sb.append("; ModuleID = '$name'\n")
        sb.append("; Blume Unified Memory IR (MIR)\n\n")
        for (fn in functions.values) {
            sb.append(fn.toString())
            sb.append("\n")
        }
        return sb.toString()
    }
}
