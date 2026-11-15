package com.blume.compiler.ir

import com.blume.compiler.ast.*
import com.blume.compiler.analyzer.OwnershipAnalyzer

class ScopeContext(val parent: ScopeContext? = null) {
    val variables = mutableMapOf<String, Triple<String, OwnershipKind, TypeNode?>>()
    val scopedVars = mutableListOf<Pair<String, OwnershipKind>>()
    val defers = mutableListOf<BlockStmt>()

    fun define(name: String, reg: String, ownership: OwnershipKind, type: TypeNode? = null) {
        variables[name] = Triple(reg, ownership, type)
        scopedVars.add(Pair(reg, ownership))
    }

    fun lookup(name: String): Triple<String, OwnershipKind, TypeNode?>? {
        variables[name]?.let { return it }
        return parent?.lookup(name)
    }
}

class BlumeIRGenerator(private val analyzer: OwnershipAnalyzer = OwnershipAnalyzer()) {
    val module = IRModule("blume_main")
    private var currentFn: IRFunction? = null
    private var currentScope: ScopeContext? = null
    private val classMap = mutableMapOf<String, ClassDecl>()

    fun generate(program: ProgramNode): IRModule {
        for (decl in program.declarations) {
            if (decl is ClassDecl) {
                classMap[decl.name] = decl
            }
        }

        // Generate classes
        for (decl in program.declarations) {
            if (decl is ClassDecl) generateClass(decl)
        }

        // Generate functions
        for (decl in program.declarations) {
            if (decl is FuncDecl) generateFunc(decl)
        }

        // Top level main
        val mainFn = IRFunction("__blume_main__", returnType = "Void")
        currentFn = mainFn
        val entryBb = mainFn.newBlock("entry")
        mainFn.currentBlock = entryBb
        currentScope = ScopeContext()

        for (decl in program.declarations) {
            if (decl is StmtNode) {
                generateStmt(decl)
            }
        }

        emitScopeCleanup(currentScope!!)
        mainFn.emit(IRInstruction(IROpcode.RET, operands = listOf(null)))
        module.addFunction(mainFn)

        return module
    }

    private fun generateClass(cls: ClassDecl) {
        // Deinit function
        cls.deinitMethod?.let { deinitBody ->
            val deinitFn = IRFunction("${cls.name}__deinit", params = listOf("%self"), returnType = "Void")
            currentFn = deinitFn
            deinitFn.currentBlock = deinitFn.newBlock("entry")
            currentScope = ScopeContext()
            currentScope!!.define("self", "%self", OwnershipKind.UNOWNED)

            for (stmt in deinitBody.statements) {
                generateStmt(stmt)
            }
            emitScopeCleanup(currentScope!!)
            deinitFn.emit(IRInstruction(IROpcode.RET, operands = listOf(null)))
            module.addFunction(deinitFn)
        }

        // Init function
        cls.initMethod?.let { initDecl ->
            val paramNames = mutableListOf("%self")
            paramNames.addAll(initDecl.params.map { "%${it.name}" })
            val initFn = IRFunction("${cls.name}__init", params = paramNames, returnType = "Void")
            currentFn = initFn
            initFn.currentBlock = initFn.newBlock("entry")
            currentScope = ScopeContext()
            currentScope!!.define("self", "%self", cls.defaultOwnership)
            for (p in initDecl.params) {
                currentScope!!.define(p.name, "%${p.name}", p.ownership, p.typeAnnotation)
            }

            for (stmt in initDecl.body.statements) {
                generateStmt(stmt)
            }
            emitScopeCleanup(currentScope!!)
            initFn.emit(IRInstruction(IROpcode.RET, operands = listOf("%self")))
            module.addFunction(initFn)
        }

        // Class methods
        for (method in cls.methods) {
            val paramNames = mutableListOf("%self")
            paramNames.addAll(method.params.map { "%${it.name}" })
            val methodFn = IRFunction("${cls.name}__${method.name}", params = paramNames, returnType = method.returnType.name)
            currentFn = methodFn
            methodFn.currentBlock = methodFn.newBlock("entry")
            currentScope = ScopeContext()
            currentScope!!.define("self", "%self", cls.defaultOwnership)
            for (p in method.params) {
                currentScope!!.define(p.name, "%${p.name}", p.ownership, p.typeAnnotation)
            }

            for (stmt in method.body.statements) {
                generateStmt(stmt)
            }
            emitScopeCleanup(currentScope!!)
            methodFn.emit(IRInstruction(IROpcode.RET, operands = listOf(null)))
            module.addFunction(methodFn)
        }
    }

    private fun generateFunc(func: FuncDecl) {
        val paramNames = func.params.map { "%${it.name}" }
        val fn = IRFunction(func.name, params = paramNames, returnType = func.returnType.name)
        currentFn = fn
        fn.currentBlock = fn.newBlock("entry")
        currentScope = ScopeContext()
        for (p in func.params) {
            currentScope!!.define(p.name, "%${p.name}", p.ownership, p.typeAnnotation)
        }

        for (stmt in func.body.statements) {
            generateStmt(stmt)
        }
        emitScopeCleanup(currentScope!!)
        fn.emit(IRInstruction(IROpcode.RET, operands = listOf(null)))
        module.addFunction(fn)
    }

    private fun generateStmt(stmt: StmtNode) {
        val fn = currentFn ?: return

        when (stmt) {
            is BlockStmt -> {
                val prevScope = currentScope
                val blockScope = ScopeContext(prevScope)
                currentScope = blockScope
                for (s in stmt.statements) {
                    generateStmt(s)
                }
                emitScopeCleanup(blockScope)
                currentScope = prevScope
            }
            is VarDeclStmt -> {
                val slotName = "%slot_${stmt.name}"
                fn.emit(IRInstruction(IROpcode.ALLOCA, result = slotName))
                val initReg = stmt.initializer?.let { generateExpr(it) } ?: "%null"
                fn.emit(IRInstruction(IROpcode.STORE, operands = listOf(initReg, slotName)))

                val resolvedDomain = stmt.ownership
                if (resolvedDomain == OwnershipKind.OWNED) {
                    fn.emit(IRInstruction(IROpcode.BLUME_RETAIN, operands = listOf(initReg)))
                } else if (resolvedDomain == OwnershipKind.SHARED) {
                    fn.emit(IRInstruction(IROpcode.BLUME_GC_ROOT, operands = listOf(slotName)))
                }

                currentScope!!.define(stmt.name, slotName, resolvedDomain, stmt.typeAnnotation)
            }
            is AssignStmt -> {
                val valReg = generateExpr(stmt.value)
                when (val target = stmt.target) {
                    is IdentifierExpr -> {
                        val varInfo = currentScope?.lookup(target.name)
                        if (varInfo != null) {
                            val slotName = varInfo.first
                            val domain = varInfo.second
                            if (domain == OwnershipKind.OWNED) {
                                val oldReg = fn.newReg()
                                fn.emit(IRInstruction(IROpcode.LOAD, result = oldReg, operands = listOf(slotName)))
                                fn.emit(IRInstruction(IROpcode.BLUME_RELEASE, operands = listOf(oldReg)))
                                fn.emit(IRInstruction(IROpcode.BLUME_RETAIN, operands = listOf(valReg)))
                            }
                            fn.emit(IRInstruction(IROpcode.STORE, operands = listOf(valReg, slotName)))
                        }
                    }
                    is MemberAccessExpr -> {
                        val objReg = generateExpr(target.obj)
                        fn.emit(IRInstruction(IROpcode.BLUME_BRIDGE, operands = listOf(objReg, target.member, valReg)))
                        fn.emit(IRInstruction(IROpcode.SET_FIELD, operands = listOf(objReg, target.member, valReg)))
                    }
                    is IndexExpr -> {
                        val arrReg = generateExpr(target.target)
                        val idxReg = generateExpr(target.index)
                        fn.emit(IRInstruction(IROpcode.SET_ELEM, operands = listOf(arrReg, idxReg, valReg)))
                    }
                    else -> {}
                }
            }
            is IfStmt -> {
                val condReg = generateExpr(stmt.condition)
                val thenBb = fn.newBlock("if.then")
                val elseBb = if (stmt.elseBranch != null) fn.newBlock("if.else") else null
                val mergeBb = fn.newBlock("if.merge")

                val targetElse = elseBb?.label ?: mergeBb.label
                fn.emit(IRInstruction(IROpcode.BR_COND, operands = listOf(condReg, thenBb.label, targetElse)))

                fn.currentBlock = thenBb
                generateStmt(stmt.thenBranch)
                fn.emit(IRInstruction(IROpcode.BR, operands = listOf(mergeBb.label)))

                if (elseBb != null && stmt.elseBranch != null) {
                    fn.currentBlock = elseBb
                    generateStmt(stmt.elseBranch)
                    fn.emit(IRInstruction(IROpcode.BR, operands = listOf(mergeBb.label)))
                }

                fn.currentBlock = mergeBb
            }
            is WhileStmt -> {
                val condBb = fn.newBlock("while.cond")
                val bodyBb = fn.newBlock("while.body")
                val exitBb = fn.newBlock("while.exit")

                fn.emit(IRInstruction(IROpcode.BR, operands = listOf(condBb.label)))

                fn.currentBlock = condBb
                val condReg = generateExpr(stmt.condition)
                fn.emit(IRInstruction(IROpcode.BR_COND, operands = listOf(condReg, bodyBb.label, exitBb.label)))

                fn.currentBlock = bodyBb
                generateStmt(stmt.body)
                fn.emit(IRInstruction(IROpcode.BLUME_SAFEPOINT))
                fn.emit(IRInstruction(IROpcode.BR, operands = listOf(condBb.label)))

                fn.currentBlock = exitBb
            }
            is ForStmt -> {
                if (stmt.iterable is RangeExpr) {
                    val startReg = generateExpr(stmt.iterable.start)
                    val endReg = generateExpr(stmt.iterable.end)
                    val loopVarSlot = "%slot_${stmt.varName}"
                    fn.emit(IRInstruction(IROpcode.ALLOCA, result = loopVarSlot))
                    fn.emit(IRInstruction(IROpcode.STORE, operands = listOf(startReg, loopVarSlot)))

                    val condBb = fn.newBlock("for.cond")
                    val bodyBb = fn.newBlock("for.body")
                    val incBb = fn.newBlock("for.inc")
                    val exitBb = fn.newBlock("for.exit")

                    fn.emit(IRInstruction(IROpcode.BR, operands = listOf(condBb.label)))

                    fn.currentBlock = condBb
                    val currVal = fn.newReg()
                    fn.emit(IRInstruction(IROpcode.LOAD, result = currVal, operands = listOf(loopVarSlot)))
                    val cmpReg = fn.newReg()
                    fn.emit(IRInstruction(IROpcode.BINOP, result = cmpReg, operands = listOf("<", currVal, endReg)))
                    fn.emit(IRInstruction(IROpcode.BR_COND, operands = listOf(cmpReg, bodyBb.label, exitBb.label)))

                    fn.currentBlock = bodyBb
                    val forScope = ScopeContext(currentScope)
                    forScope.define(stmt.varName, loopVarSlot, OwnershipKind.AUTOMATIC)
                    val prevScope = currentScope
                    currentScope = forScope
                    for (s in stmt.body.statements) generateStmt(s)
                    emitScopeCleanup(forScope)
                    currentScope = prevScope

                    fn.emit(IRInstruction(IROpcode.BR, operands = listOf(incBb.label)))

                    fn.currentBlock = incBb
                    val nextVal = fn.newReg()
                    val constOne = fn.newReg()
                    fn.emit(IRInstruction(IROpcode.CONST, result = constOne, operands = listOf(1L)))
                    fn.emit(IRInstruction(IROpcode.BINOP, result = nextVal, operands = listOf("+", currVal, constOne)))
                    fn.emit(IRInstruction(IROpcode.STORE, operands = listOf(nextVal, loopVarSlot)))
                    fn.emit(IRInstruction(IROpcode.BR, operands = listOf(condBb.label)))

                    fn.currentBlock = exitBb
                }
            }
            is ReturnStmt -> {
                val retReg = stmt.value?.let { generateExpr(it) }
                // Scope cleanup before return
                var s = currentScope
                while (s != null) {
                    emitScopeCleanup(s)
                    s = s.parent
                }
                fn.emit(IRInstruction(IROpcode.RET, operands = listOf(retReg)))
            }
            is DeferStmt -> {
                currentScope?.defers?.add(stmt.body)
            }
            is ExprStmt -> {
                generateExpr(stmt.expr)
            }
        }
    }

    private fun generateExpr(expr: ExprNode): String {
        val fn = currentFn ?: return "%null"

        return when (expr) {
            is LiteralExpr -> {
                val reg = fn.newReg()
                fn.emit(IRInstruction(IROpcode.CONST, result = reg, operands = listOf(expr.value)))
                reg
            }
            is IdentifierExpr -> {
                if (expr.name == "self") {
                    return "%self"
                }
                val varInfo = currentScope?.lookup(expr.name)
                if (varInfo != null) {
                    val slotOrReg = varInfo.first
                    if (slotOrReg.startsWith("%slot_")) {
                        val reg = fn.newReg()
                        fn.emit(IRInstruction(IROpcode.LOAD, result = reg, operands = listOf(slotOrReg)))
                        reg
                    } else {
                        slotOrReg
                    }
                } else {
                    "%null"
                }
            }
            is BinaryExpr -> {
                val leftReg = generateExpr(expr.left)
                val rightReg = generateExpr(expr.right)
                val reg = fn.newReg()
                fn.emit(IRInstruction(IROpcode.BINOP, result = reg, operands = listOf(expr.op, leftReg, rightReg)))
                reg
            }
            is UnaryExpr -> {
                val operandReg = generateExpr(expr.operand)
                val reg = fn.newReg()
                fn.emit(IRInstruction(IROpcode.UNOP, result = reg, operands = listOf(expr.op, operandReg)))
                reg
            }
            is CallExpr -> {
                val calleeName = when (val c = expr.callee) {
                    is IdentifierExpr -> c.name
                    is MemberAccessExpr -> {
                        val objReg = generateExpr(c.obj)
                        "__method_${c.member}__"
                    }
                    else -> "unknown_fn"
                }

                // Built-in functions
                if (calleeName == "print") {
                    val argRegs = expr.args.map { generateExpr(it) }
                    fn.emit(IRInstruction(IROpcode.PRINT, operands = argRegs))
                    return "%void"
                } else if (calleeName == "blume_retain_count") {
                    val argReg = generateExpr(expr.args[0])
                    val reg = fn.newReg()
                    fn.emit(IRInstruction(IROpcode.CALL, result = reg, operands = listOf("__blume_get_retain_count__", argReg)))
                    return reg
                } else if (calleeName == "blume_memory_domain") {
                    val argReg = generateExpr(expr.args[0])
                    val reg = fn.newReg()
                    fn.emit(IRInstruction(IROpcode.CALL, result = reg, operands = listOf("__blume_get_domain__", argReg)))
                    return reg
                } else if (calleeName == "blume_gc_collect") {
                    val reg = fn.newReg()
                    fn.emit(IRInstruction(IROpcode.BLUME_GC_COLLECT, result = reg))
                    return reg
                } else if (calleeName == "blume_stats") {
                    fn.emit(IRInstruction(IROpcode.CALL, operands = listOf("__blume_heap_stats__")))
                    return "%void"
                }

                // Check if constructor call
                if (classMap.containsKey(calleeName)) {
                    val cls = classMap[calleeName]!!
                    val domain = cls.defaultOwnership
                    val objReg = fn.newReg()
                    val fieldNames = cls.fields.map { it.name }
                    fn.emit(IRInstruction(IROpcode.BLUME_ALLOC, result = objReg, operands = listOf(domain.keyword, cls.name, fieldNames)))

                    val argRegs = mutableListOf(objReg)
                    argRegs.addAll(expr.args.map { generateExpr(it) })
                    if (cls.initMethod != null) {
                        fn.emit(IRInstruction(IROpcode.CALL, operands = listOf("${cls.name}__init") + argRegs))
                    }
                    return objReg
                }

                val argRegs = expr.args.map { generateExpr(it) }
                val reg = fn.newReg()
                fn.emit(IRInstruction(IROpcode.CALL, result = reg, operands = listOf(calleeName) + argRegs))
                reg
            }
            is MemberAccessExpr -> {
                val objReg = generateExpr(expr.obj)
                val reg = fn.newReg()
                fn.emit(IRInstruction(IROpcode.GET_FIELD, result = reg, operands = listOf(objReg, expr.member)))
                reg
            }
            is IndexExpr -> {
                val targetReg = generateExpr(expr.target)
                val idxReg = generateExpr(expr.index)
                val reg = fn.newReg()
                fn.emit(IRInstruction(IROpcode.GET_ELEM, result = reg, operands = listOf(targetReg, idxReg)))
                reg
            }
            is ArrayLiteralExpr -> {
                val elemRegs = expr.elements.map { generateExpr(it) }
                val reg = fn.newReg()
                fn.emit(IRInstruction(IROpcode.ARRAY_NEW, result = reg, operands = elemRegs))
                reg
            }
            is NewExpr -> {
                val domain = if (expr.ownership != OwnershipKind.AUTOMATIC) expr.ownership else {
                    classMap[expr.typeName]?.defaultOwnership ?: OwnershipKind.OWNED
                }
                val cls = classMap[expr.typeName]
                val fieldNames = cls?.fields?.map { it.name } ?: emptyList()
                val objReg = fn.newReg()
                fn.emit(IRInstruction(IROpcode.BLUME_ALLOC, result = objReg, operands = listOf(domain.keyword, expr.typeName, fieldNames)))

                val argRegs = mutableListOf(objReg)
                argRegs.addAll(expr.args.map { generateExpr(it) })
                if (cls?.initMethod != null) {
                    fn.emit(IRInstruction(IROpcode.CALL, operands = listOf("${expr.typeName}__init") + argRegs))
                }
                objReg
            }
            is WeakRefExpr -> {
                val innerReg = generateExpr(expr.expr)
                val reg = fn.newReg()
                fn.emit(IRInstruction(IROpcode.BLUME_WEAK, result = reg, operands = listOf(innerReg)))
                reg
            }
            is RangeExpr -> {
                generateExpr(expr.start)
            }
        }
    }

    private fun emitScopeCleanup(scope: ScopeContext) {
        val fn = currentFn ?: return

        // Execute defers in LIFO order
        for (i in scope.defers.indices.reversed()) {
            val deferBlock = scope.defers[i]
            for (s in deferBlock.statements) {
                generateStmt(s)
            }
        }

        // Release ARC and unroot GC variables in LIFO order
        for (i in scope.scopedVars.indices.reversed()) {
            val (slotOrReg, domain) = scope.scopedVars[i]
            if (domain == OwnershipKind.OWNED) {
                if (slotOrReg.startsWith("%slot_")) {
                    val objReg = fn.newReg()
                    fn.emit(IRInstruction(IROpcode.LOAD, result = objReg, operands = listOf(slotOrReg)))
                    fn.emit(IRInstruction(IROpcode.BLUME_RELEASE, operands = listOf(objReg)))
                } else {
                    fn.emit(IRInstruction(IROpcode.BLUME_RELEASE, operands = listOf(slotOrReg)))
                }
            } else if (domain == OwnershipKind.SHARED) {
                fn.emit(IRInstruction(IROpcode.BLUME_GC_UNROOT, operands = listOf(slotOrReg)))
            }
        }
    }
}
