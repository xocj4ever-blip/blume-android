package com.blume.runtime

import com.blume.compiler.ast.OwnershipKind

class BlumeRuntimeException(message: String) : RuntimeException(message)
class BlumeUnownedReferenceException(message: String) : RuntimeException(message)

data class BlumeObject(
    val objId: Int,
    val className: String,
    val domain: OwnershipKind,
    val fields: MutableMap<String, Any?> = mutableMapOf(),
    var retainCount: Int = 1,
    var isAlive: Boolean = true,
    val weakRefs: MutableList<BlumeWeakRef> = mutableListOf(),
    var deinitFn: ((BlumeObject) -> Unit)? = null
) {
    override fun toString(): String {
        val status = if (isAlive) "alive" else "deallocated"
        return if (domain == OwnershipKind.OWNED) {
            "<$className id=$objId domain=owned rc=$retainCount $status>"
        } else {
            "<$className id=$objId domain=shared gc $status>"
        }
    }
}

class BlumeWeakRef(target: BlumeObject?) {
    private var ref: BlumeObject? = target

    init {
        if (target != null && target.isAlive) {
            target.weakRefs.add(this)
        }
    }

    fun get(): BlumeObject? {
        val t = ref
        return if (t != null && t.isAlive) t else null
    }

    fun targetDeallocated() {
        ref = null
    }

    override fun toString(): String = "<WeakRef -> ${get()}>"
}

class BlumeUnownedRef(val target: BlumeObject) {
    fun get(): BlumeObject {
        if (!target.isAlive) {
            throw BlumeUnownedReferenceException(
                "Panic: Attempted to access unowned reference to deallocated object '${target.className}' (id=${target.objId})!"
            )
        }
        return target
    }

    override fun toString(): String = "<UnownedRef -> $target>"
}

data class HeapStats(
    var totalAllocated: Int = 0,
    var arcAllocated: Int = 0,
    var gcAllocated: Int = 0,
    var arcDeallocated: Int = 0,
    var gcCollected: Int = 0,
    var collectionsRun: Int = 0
) {
    fun arcLive(): Int = arcAllocated - arcDeallocated
    fun gcLive(): Int = gcAllocated - gcCollected
}

data class MemorySnapshot(
    val stats: HeapStats,
    val arcObjects: List<BlumeObject>,
    val gcObjects: List<BlumeObject>,
    val activeBridgesCount: Int
)

class HybridMemoryCoordinator {
    private var nextObjId = 1
    val stats = HeapStats()

    val arcObjects = mutableMapOf<Int, BlumeObject>()
    val gcObjects = mutableMapOf<Int, BlumeObject>()

    val gcRootSlots = mutableMapOf<String, () -> Any?>()
    val gcExplicitRoots = mutableSetOf<Int>()

    // Cross-Domain Bridge
    val bridgeArcToGc = mutableMapOf<Int, MutableSet<Int>>()
    val bridgeGcToArc = mutableMapOf<Int, MutableList<Int>>()

    var allocCounter = 0
    var gcThreshold = 64

    fun allocate(
        className: String,
        domain: OwnershipKind,
        fields: List<String> = emptyList(),
        deinitFn: ((BlumeObject) -> Unit)? = null
    ): BlumeObject {
        val objId = nextObjId++
        val obj = BlumeObject(
            objId = objId,
            className = className,
            domain = domain,
            fields = fields.associateWith { null }.toMutableMap(),
            retainCount = 1,
            isAlive = true,
            deinitFn = deinitFn
        )

        stats.totalAllocated++
        allocCounter++

        if (domain == OwnershipKind.OWNED) {
            stats.arcAllocated++
            arcObjects[objId] = obj
        } else {
            stats.gcAllocated++
            gcObjects[objId] = obj
        }

        return obj
    }

    fun retain(obj: Any?): Int {
        if (obj !is BlumeObject) return 0
        if (obj.domain != OwnershipKind.OWNED) return -1
        if (!obj.isAlive) {
            throw BlumeRuntimeException("Attempted to retain already deallocated object: $obj")
        }
        obj.retainCount++
        return obj.retainCount
    }

    fun release(obj: Any?): Int {
        if (obj !is BlumeObject) return 0
        if (obj.domain != OwnershipKind.OWNED) return -1
        if (!obj.isAlive) return 0

        obj.retainCount--
        if (obj.retainCount <= 0) {
            deallocateArcObject(obj)
            return 0
        }
        return obj.retainCount
    }

    private fun deallocateArcObject(obj: BlumeObject) {
        if (!obj.isAlive) return
        obj.isAlive = false
        stats.arcDeallocated++

        // 1. Deterministic deinit callback
        try {
            obj.deinitFn?.invoke(obj)
        } catch (e: Exception) {
            println("[Blume Runtime] Exception in deinit for $obj: ${e.message}")
        }

        // 2. Invalidate weak references
        for (wref in obj.weakRefs) {
            wref.targetDeallocated()
        }
        obj.weakRefs.clear()

        // 3. Clean up bridged roots held by this ARC container
        bridgeArcToGc.remove(obj.objId)

        // 4. Release any child ARC fields
        for (fld in obj.fields.values) {
            if (fld is BlumeObject && fld.domain == OwnershipKind.OWNED) {
                release(fld)
            }
        }

        // 5. Remove from arcObjects
        arcObjects.remove(obj.objId)
    }

    fun createWeakRef(obj: Any?): BlumeWeakRef {
        return when (obj) {
            is BlumeObject -> BlumeWeakRef(obj)
            is BlumeWeakRef -> obj
            else -> BlumeWeakRef(null)
        }
    }

    fun createUnownedRef(obj: Any?): BlumeUnownedRef {
        if (obj !is BlumeObject) {
            throw BlumeRuntimeException("Cannot create unowned reference to non-object: $obj")
        }
        return BlumeUnownedRef(obj)
    }

    fun registerGcRootSlot(slotName: String, getter: () -> Any?) {
        gcRootSlots[slotName] = getter
    }

    fun unregisterGcRootSlot(slotName: String) {
        gcRootSlots.remove(slotName)
    }

    fun collectGarbage(): Int {
        stats.collectionsRun++

        val visitedIds = mutableSetOf<Int>()
        val queue = mutableListOf<BlumeObject>()

        // 1. Gather all roots
        // Stack roots
        for (getter in gcRootSlots.values.toList()) {
            try {
                val v = getter()
                if (v is BlumeObject && v.domain == OwnershipKind.SHARED && v.isAlive) {
                    if (visitedIds.add(v.objId)) queue.add(v)
                }
            } catch (_: Exception) {}
        }

        // Explicit roots
        for (oid in gcExplicitRoots) {
            val obj = gcObjects[oid]
            if (obj != null && obj.isAlive && visitedIds.add(oid)) {
                queue.add(obj)
            }
        }

        // Cross-domain bridge roots (ARC objects holding GC objects)
        for ((arcId, gcIds) in bridgeArcToGc) {
            val arcObj = arcObjects[arcId]
            if (arcObj != null && arcObj.isAlive) {
                for (gcId in gcIds) {
                    val gcObj = gcObjects[gcId]
                    if (gcObj != null && gcObj.isAlive && visitedIds.add(gcId)) {
                        queue.add(gcObj)
                    }
                }
            }
        }

        // 2. Mark Phase (Reachability Analysis)
        while (queue.isNotEmpty()) {
            val curr = queue.removeAt(0)
            for (fld in curr.fields.values) {
                if (fld is BlumeObject && fld.domain == OwnershipKind.SHARED && fld.isAlive) {
                    if (visitedIds.add(fld.objId)) queue.add(fld)
                } else if (fld is List<*>) {
                    for (item in fld) {
                        if (item is BlumeObject && item.domain == OwnershipKind.SHARED && item.isAlive) {
                            if (visitedIds.add(item.objId)) queue.add(item)
                        }
                    }
                }
            }
        }

        // 3. Sweep Phase
        val unreachable = gcObjects.keys.filter { it !in visitedIds }
        var collected = 0

        for (oid in unreachable) {
            val deadObj = gcObjects[oid] ?: continue
            deadObj.isAlive = false
            collected++
            stats.gcCollected++

            try {
                deadObj.deinitFn?.invoke(deadObj)
            } catch (e: Exception) {
                println("[Blume Runtime] Exception in deinit for GC $deadObj: ${e.message}")
            }

            // Release bridged ARC retain handles held by this GC object
            bridgeGcToArc[oid]?.let { arcIds ->
                for (arcId in arcIds) {
                    arcObjects[arcId]?.let { release(it) }
                }
                bridgeGcToArc.remove(oid)
            }

            for (wref in deadObj.weakRefs) {
                wref.targetDeallocated()
            }
            deadObj.weakRefs.clear()

            gcObjects.remove(oid)
        }

        return collected
    }

    fun bridgeReference(sourceObj: Any?, fieldName: String, targetVal: Any?) {
        if (sourceObj !is BlumeObject || targetVal !is BlumeObject) return

        // Case 1: ARC (owned) references GC (shared)
        if (sourceObj.domain == OwnershipKind.OWNED && targetVal.domain == OwnershipKind.SHARED) {
            bridgeArcToGc.getOrPut(sourceObj.objId) { mutableSetOf() }.add(targetVal.objId)
        }
        // Case 2: GC (shared) references ARC (owned)
        else if (sourceObj.domain == OwnershipKind.SHARED && targetVal.domain == OwnershipKind.OWNED) {
            retain(targetVal)
            bridgeGcToArc.getOrPut(sourceObj.objId) { mutableListOf() }.add(targetVal.objId)
        }
    }

    fun getSnapshot(): MemorySnapshot {
        return MemorySnapshot(
            stats = stats.copy(),
            arcObjects = arcObjects.values.toList(),
            gcObjects = gcObjects.values.toList(),
            activeBridgesCount = bridgeArcToGc.size + bridgeGcToArc.size
        )
    }

    fun formatStats(): String {
        return """
            ====== Blume Hybrid Memory Coordinator Stats ======
            Total Allocations:   ${stats.totalAllocated}
            ARC Allocations:     ${stats.arcAllocated}
            ARC Deallocations:   ${stats.arcDeallocated} (Deterministic)
            ARC Live Objects:    ${stats.arcLive()}
            GC Allocations:      ${stats.gcAllocated}
            GC Collections:      ${stats.collectionsRun}
            GC Objects Swept:    ${stats.gcCollected} (Cycles Collected)
            GC Live Objects:     ${stats.gcLive()}
            Active Cross-Bridges:${bridgeArcToGc.size + bridgeGcToArc.size}
            ====================================================
        """.trimIndent()
    }
}
