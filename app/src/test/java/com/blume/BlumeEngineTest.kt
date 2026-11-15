package com.blume

import com.blume.compiler.ast.OwnershipKind
import com.blume.compiler.lexer.BlumeLexer
import com.blume.compiler.lexer.TokenType
import com.blume.compiler.parser.BlumeParser
import com.blume.compiler.analyzer.OwnershipAnalyzer
import com.blume.compiler.ir.BlumeIRGenerator
import com.blume.compiler.ir.IROpcode
import com.blume.runtime.HybridMemoryCoordinator
import com.blume.vm.BlumeVM
import org.junit.Assert.*
import org.junit.Test

class BlumeEngineTest {

    @Test
    fun testLexerTokens() {
        val source = "owned class Node { weak var parent: Node? }"
        val lexer = BlumeLexer(source)
        val tokens = lexer.tokenize()

        assertEquals(TokenType.OWNED, tokens[0].type)
        assertEquals(TokenType.CLASS, tokens[1].type)
        assertEquals(TokenType.IDENTIFIER, tokens[2].type)
        assertEquals("Node", tokens[2].lexeme)
        assertEquals(TokenType.LBRACE, tokens[3].type)
        assertEquals(TokenType.WEAK, tokens[4].type)
        assertEquals(TokenType.VAR, tokens[5].type)
    }

    @Test
    fun testArcDeterministicDeallocation() {
        val coordinator = HybridMemoryCoordinator()
        var deinitCalled = false

        val obj = coordinator.allocate(
            className = "FileHandle",
            domain = OwnershipKind.OWNED,
            fields = listOf("name"),
            deinitFn = { deinitCalled = true }
        )

        assertEquals(1, obj.retainCount)
        assertEquals(1, coordinator.arcObjects.size)

        coordinator.retain(obj)
        assertEquals(2, obj.retainCount)

        coordinator.release(obj)
        assertEquals(1, obj.retainCount)
        assertFalse(deinitCalled)

        coordinator.release(obj)
        assertEquals(0, obj.retainCount)
        assertTrue(deinitCalled)
        assertEquals(0, coordinator.arcObjects.size)
        assertEquals(1, coordinator.stats.arcDeallocated)
    }

    @Test
    fun testGcCycleCollection() {
        val coordinator = HybridMemoryCoordinator()
        val sweptList = mutableListOf<Int>()

        val node1 = coordinator.allocate("Node", OwnershipKind.SHARED, listOf("next")) { o -> sweptList.add(o.objId) }
        val node2 = coordinator.allocate("Node", OwnershipKind.SHARED, listOf("next")) { o -> sweptList.add(o.objId) }
        val node3 = coordinator.allocate("Node", OwnershipKind.SHARED, listOf("next")) { o -> sweptList.add(o.objId) }

        // Form cyclic graph: 1 -> 2 -> 3 -> 1
        node1.fields["next"] = node2
        node2.fields["next"] = node3
        node3.fields["next"] = node1

        assertEquals(3, coordinator.gcObjects.size)

        // Without stack roots, mark-and-sweep should reclaim all 3 cyclic nodes
        val collected = coordinator.collectGarbage()
        assertEquals(3, collected)
        assertEquals(0, coordinator.gcObjects.size)
        assertEquals(3, sweptList.size)
    }

    @Test
    fun testWeakReferenceAutoNilification() {
        val coordinator = HybridMemoryCoordinator()
        val target = coordinator.allocate("Target", OwnershipKind.OWNED)
        val weakRef = coordinator.createWeakRef(target)

        assertNotNull(weakRef.get())
        assertEquals(target, weakRef.get())

        // Deallocate target
        coordinator.release(target)
        assertNull(weakRef.get())
    }

    @Test
    fun testCrossDomainBridge() {
        val coordinator = HybridMemoryCoordinator()
        val arcObj = coordinator.allocate("ArcContainer", OwnershipKind.OWNED)
        val gcObj = coordinator.allocate("GcNode", OwnershipKind.SHARED)

        // ARC container holds GC node
        coordinator.bridgeReference(arcObj, "child", gcObj)
        assertTrue(coordinator.bridgeArcToGc.containsKey(arcObj.objId))
        assertTrue(coordinator.bridgeArcToGc[arcObj.objId]!!.contains(gcObj.objId))

        // Running GC should NOT sweep gcObj because arcObj bridges it as root
        val swept1 = coordinator.collectGarbage()
        assertEquals(0, swept1)
        assertEquals(1, coordinator.gcObjects.size)

        // Release ARC container -> GC object is now unreferenced and collected
        coordinator.release(arcObj)
        val swept2 = coordinator.collectGarbage()
        assertEquals(1, swept2)
        assertEquals(0, coordinator.gcObjects.size)
    }

    @Test
    fun testEndToEndExecution() {
        val source = """
            fn fib(n: Int) -> Int {
                if n <= 1 {
                    return n
                }
                return fib(n - 1) + fib(n - 2)
            }
            let res: Int = fib(8)
            print("Fibonacci(8) =", res)
        """.trimIndent()

        val lexer = BlumeLexer(source)
        val parser = BlumeParser(lexer.tokenize())
        val ast = parser.parse()

        val analyzer = OwnershipAnalyzer()
        analyzer.analyzeProgram(ast)

        val irGen = BlumeIRGenerator(analyzer)
        val irModule = irGen.generate(ast)

        val output = mutableListOf<String>()
        val vm = BlumeVM(irModule, onOutput = { output.add(it) })
        vm.execute()

        assertTrue(output.any { it.contains("Fibonacci(8) = 21") })
    }
}
