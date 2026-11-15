package com.blume.studio

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.LiveData
import androidx.lifecycle.MutableLiveData
import androidx.lifecycle.viewModelScope
import com.blume.compiler.analyzer.OwnershipAnalyzer
import com.blume.compiler.ir.BlumeIRGenerator
import com.blume.compiler.lexer.BlumeLexer
import com.blume.compiler.parser.BlumeParser
import com.blume.compiler.ast.ProgramNode
import com.blume.repl.BlumeREPLEngine
import com.blume.runtime.HybridMemoryCoordinator
import com.blume.runtime.MemorySnapshot
import com.blume.vm.BlumeVM
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

data class ExecutionResult(
    val success: Boolean,
    val output: String,
    val executionTimeMs: Long,
    val errorMessage: String? = null
)

class BlumeStudioViewModel(application: Application) : AndroidViewModel(application) {

    val sourceCode = MutableLiveData<String>()
    val consoleOutput = MutableLiveData<String>("")
    val generatedMIR = MutableLiveData<String>("")
    val isRunning = MutableLiveData<Boolean>(false)
    val memorySnapshot = MutableLiveData<MemorySnapshot?>()
    val replOutput = MutableLiveData<String>("")

    private var coordinator = HybridMemoryCoordinator()
    val replEngine = BlumeREPLEngine()

    val exampleList = listOf(
        "01_hello.blume" to "01. Fundamentals & Control Flow",
        "02_arc_deterministic.blume" to "02. Swift-Inspired ARC & Deinit",
        "03_gc_cycle_collection.blume" to "03. Kotlin-Inspired Tracing GC",
        "04_hybrid_bridge.blume" to "04. Cross-Domain Bridge (blume.bridge)",
        "05_weak_references.blume" to "05. Non-Owning Weak References",
        "06_defer_cleanup.blume" to "06. Defer Scope Cleanup (LIFO)",
        "07_escape_analysis.blume" to "07. Automatic Memory Strategy"
    )

    init {
        loadExample("01_hello.blume")
    }

    fun loadExample(filename: String) {
        viewModelScope.launch(Dispatchers.IO) {
            try {
                val inputStream = getApplication<Application>().assets.open("examples/$filename")
                val content = inputStream.bufferedReader().use { it.readText() }
                withContext(Dispatchers.Main) {
                    sourceCode.value = content
                    consoleOutput.value = "Loaded example: $filename\nTap 'Run' to execute."
                }
            } catch (e: Exception) {
                withContext(Dispatchers.Main) {
                    consoleOutput.value = "Error loading example: ${e.message}"
                }
            }
        }
    }

    fun runCode() {
        val code = sourceCode.value ?: return
        isRunning.value = true
        consoleOutput.value = "Executing Blume script...\n"

        viewModelScope.launch(Dispatchers.Default) {
            val startTime = System.currentTimeMillis()
            val logs = StringBuilder()

            try {
                // 1. Lexing
                val lexer = BlumeLexer(code, "script.blume")
                val tokens = lexer.tokenize()

                // 2. Parsing
                val parser = BlumeParser(tokens)
                val ast = parser.parse()

                // 3. Ownership Analysis
                val analyzer = OwnershipAnalyzer()
                analyzer.analyzeProgram(ast)

                // 4. Unified Memory IR Generation
                val irGen = BlumeIRGenerator(analyzer)
                val irModule = irGen.generate(ast)
                val mirText = irModule.toString()

                withContext(Dispatchers.Main) {
                    generatedMIR.value = mirText
                }

                // 5. VM Execution
                coordinator = HybridMemoryCoordinator()
                val vm = BlumeVM(irModule, coordinator = coordinator) { line ->
                    logs.append(line).append("\n")
                }
                vm.execute()

                val duration = System.currentTimeMillis() - startTime
                val snapshot = coordinator.getSnapshot()

                withContext(Dispatchers.Main) {
                    consoleOutput.value = logs.toString() + "\n=== Finished in ${duration}ms ==="
                    memorySnapshot.value = snapshot
                    isRunning.value = false
                }
            } catch (e: Exception) {
                val duration = System.currentTimeMillis() - startTime
                withContext(Dispatchers.Main) {
                    consoleOutput.value = logs.toString() + "\nBlume Error: ${e.message}\n=== Failed after ${duration}ms ==="
                    isRunning.value = false
                }
            }
        }
    }

    fun triggerGC() {
        viewModelScope.launch(Dispatchers.Default) {
            val swept = coordinator.collectGarbage()
            val snapshot = coordinator.getSnapshot()
            withContext(Dispatchers.Main) {
                consoleOutput.value = (consoleOutput.value ?: "") + "\n[GC Manual Trigger] Collected $swept unreachable object(s)."
                memorySnapshot.value = snapshot
            }
        }
    }

    fun executeReplLine(line: String) {
        val currentRepl = replOutput.value ?: ""
        val newPrompt = "$currentRepl\nblume> $line"
        val outBuilder = StringBuilder()

        val result = replEngine.executeLine(line) { out ->
            outBuilder.append("\n").append(out)
        }

        if (result != null) {
            outBuilder.append("\n=> ").append(result)
        }

        replOutput.value = newPrompt + outBuilder.toString()
        memorySnapshot.value = replEngine.coordinator.getSnapshot()
    }

    fun clearConsole() {
        consoleOutput.value = ""
    }
}
