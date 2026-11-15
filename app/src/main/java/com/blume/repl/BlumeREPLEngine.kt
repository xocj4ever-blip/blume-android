package com.blume.repl

import com.blume.compiler.ast.*
import com.blume.compiler.lexer.BlumeLexer
import com.blume.compiler.parser.BlumeParser
import com.blume.compiler.ir.BlumeIRGenerator
import com.blume.compiler.ir.IRModule
import com.blume.runtime.HybridMemoryCoordinator
import com.blume.vm.BlumeVM

class BlumeREPLEngine {
    var coordinator = HybridMemoryCoordinator()
    var showIR: Boolean = false
    private val sessionDecls = mutableListOf<ASTNode>()

    fun reset() {
        coordinator = HybridMemoryCoordinator()
        sessionDecls.clear()
    }

    fun executeLine(line: String, onOutput: (String) -> Unit): String? {
        val trimmed = line.trim()
        if (trimmed.isEmpty()) return null

        // REPL Commands
        when (trimmed) {
            ":mem", ":heap" -> {
                val stats = coordinator.formatStats()
                onOutput(stats)
                return null
            }
            ":collect" -> {
                val swept = coordinator.collectGarbage()
                onOutput("Garbage collection executed: $swept unreachable object(s) collected.")
                return null
            }
            ":ir" -> {
                showIR = !showIR
                onOutput("MIR automatic printing is now ${if (showIR) "ON" else "OFF"}.")
                return null
            }
            ":reset" -> {
                reset()
                onOutput("Blume environment and memory coordinator reset.")
                return null
            }
            ":help" -> {
                onOutput("""
                    Blume REPL Commands:
                      :mem / :heap - Display live ARC and GC heap statistics
                      :collect     - Manually trigger Tracing Garbage Collection
                      :ir          - Toggle Blume Memory IR output for evaluations
                      :reset       - Reset runtime heaps and session environment
                      :help        - Show this help menu
                """.trimIndent())
                return null
            }
        }

        try {
            // Tokenize & Parse
            val lexer = BlumeLexer(trimmed, "<repl>")
            val tokens = lexer.tokenize()
            val parser = BlumeParser(tokens)
            val prog = parser.parse()

            // If it's a declaration, add to session
            for (decl in prog.declarations) {
                if (decl is FuncDecl || decl is ClassDecl || decl is StructDecl) {
                    sessionDecls.add(decl)
                }
            }

            // Create combined program for execution
            val combinedDecls = mutableListOf<ASTNode>()
            combinedDecls.addAll(sessionDecls)
            for (decl in prog.declarations) {
                if (decl !is FuncDecl && decl !is ClassDecl && decl !is StructDecl) {
                    combinedDecls.add(decl)
                }
            }
            val execProg = ProgramNode(prog.loc, combinedDecls)

            // Generate IR
            val irGen = BlumeIRGenerator()
            val irModule = irGen.generate(execProg)

            if (showIR) {
                onOutput(irModule.toString())
            }

            // Execute on VM
            val vm = BlumeVM(irModule, coordinator = coordinator, onOutput = onOutput)
            val result = vm.execute()
            return result?.toString()
        } catch (e: Exception) {
            onOutput("Error: ${e.message}")
            return null
        }
    }
}
