package com.blume.compiler.analyzer

import com.blume.compiler.ast.*

data class BridgeEdge(
    val sourceDomain: OwnershipKind,
    val targetDomain: OwnershipKind,
    val sourceVarOrField: String,
    val targetType: String,
    val loc: SourceLocation
)

data class OwnershipDiagnostic(
    val message: String,
    val loc: SourceLocation,
    val isWarning: Boolean = false
)

class OwnershipAnalyzer {
    val diagnostics = mutableListOf<OwnershipDiagnostic>()
    val bridgeEdges = mutableListOf<BridgeEdge>()
    val resolvedOwnership = mutableMapOf<Int, OwnershipKind>()
    private val classDefinitions = mutableMapOf<String, ClassDecl>()

    fun analyzeProgram(program: ProgramNode) {
        // Collect class definitions
        for (decl in program.declarations) {
            if (decl is ClassDecl) {
                classDefinitions[decl.name] = decl
            }
        }

        // Analyze declarations
        for (decl in program.declarations) {
            when (decl) {
                is FuncDecl -> analyzeFunc(decl)
                is ClassDecl -> analyzeClass(decl)
                is StmtNode -> analyzeStmt(decl)
                else -> {}
            }
        }
    }

    private fun analyzeFunc(func: FuncDecl) {
        val returnedVars = mutableSetOf<String>()
        for (stmt in func.body.statements) {
            if (stmt is ReturnStmt && stmt.value is IdentifierExpr) {
                returnedVars.add((stmt.value as IdentifierExpr).name)
            }
        }
        for (stmt in func.body.statements) {
            analyzeStmt(stmt, returnedVars)
        }
    }

    private fun analyzeClass(cls: ClassDecl) {
        val containerDomain = cls.defaultOwnership
        for (f in cls.fields) {
            var fieldDomain = f.ownership
            if (fieldDomain == OwnershipKind.AUTOMATIC) {
                val targetCls = classDefinitions[f.typeAnnotation.name]
                fieldDomain = targetCls?.defaultOwnership ?: OwnershipKind.OWNED
                f.ownership = fieldDomain
            }

            if (containerDomain != fieldDomain && fieldDomain != OwnershipKind.WEAK && fieldDomain != OwnershipKind.UNOWNED) {
                bridgeEdges.add(
                    BridgeEdge(
                        sourceDomain = containerDomain,
                        targetDomain = fieldDomain,
                        sourceVarOrField = "${cls.name}.${f.name}",
                        targetType = f.typeAnnotation.name,
                        loc = f.loc
                    )
                )
            }
        }

        cls.initMethod?.let { analyzeFunc(it) }
        for (m in cls.methods) {
            analyzeFunc(m)
        }
    }

    private fun analyzeStmt(stmt: StmtNode, returnedVars: Set<String> = emptySet()) {
        when (stmt) {
            is VarDeclStmt -> {
                if (stmt.ownership == OwnershipKind.AUTOMATIC) {
                    // Escape analysis
                    if (returnedVars.contains(stmt.name)) {
                        stmt.ownership = OwnershipKind.SHARED
                    } else {
                        // Check initializer
                        val initCls = (stmt.initializer as? NewExpr)?.typeName?.let { classDefinitions[it] }
                        stmt.ownership = initCls?.defaultOwnership ?: OwnershipKind.OWNED
                    }
                }
                resolvedOwnership[stmt.hashCode()] = stmt.ownership
            }
            is BlockStmt -> {
                for (s in stmt.statements) analyzeStmt(s, returnedVars)
            }
            is IfStmt -> {
                analyzeStmt(stmt.thenBranch, returnedVars)
                stmt.elseBranch?.let { analyzeStmt(it, returnedVars) }
            }
            is WhileStmt -> {
                analyzeStmt(stmt.body, returnedVars)
            }
            is ForStmt -> {
                analyzeStmt(stmt.body, returnedVars)
            }
            else -> {}
        }
    }
}
