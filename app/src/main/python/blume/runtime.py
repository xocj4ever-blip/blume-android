"""
Blume Programming Language - Hybrid Memory Runtime (ARC + GC + Bridge Coordinator)
Version: 1.0
"One Language. Two Memory Models. One Unified IR."
100% Pure Python Implementation
"""

from typing import Dict, List, Set, Optional, Any, Callable
from dataclasses import dataclass, field
from blume.ast import OwnershipKind

class BlumeRuntimeError(Exception):
    pass

class BlumeUnownedReferenceError(BlumeRuntimeError):
    pass

@dataclass
class BlumeObject:
    obj_id: int
    class_name: str
    domain: OwnershipKind
    fields: Dict[str, Any] = field(default_factory=dict)
    retain_count: int = 1
    is_alive: bool = True
    weak_refs: List["BlumeWeakRef"] = field(default_factory=list)
    deinit_fn: Optional[Callable[["BlumeObject"], None]] = None

    def __repr__(self) -> str:
        status = "alive" if self.is_alive else "deallocated"
        if self.domain == OwnershipKind.OWNED:
            return f"<{self.class_name} id={self.obj_id} domain=owned rc={self.retain_count} {status}>"
        else:
            return f"<{self.class_name} id={self.obj_id} domain=shared gc {status}>"

class BlumeWeakRef:
    def __init__(self, target: Optional[BlumeObject]):
        self.target = target
        if target and target.is_alive:
            target.weak_refs.append(self)

    def get(self) -> Optional[BlumeObject]:
        if self.target is None or not self.target.is_alive:
            return None
        return self.target

    def target_deallocated(self):
        self.target = None

    def __repr__(self) -> str:
        tgt = self.get()
        return f"<WeakRef -> {tgt}>"

class BlumeUnownedRef:
    def __init__(self, target: BlumeObject):
        self.target = target

    def get(self) -> BlumeObject:
        if not self.target.is_alive:
            raise BlumeUnownedReferenceError(
                f"Panic: Attempted to access unowned reference to deallocated object '{self.target.class_name}' (id={self.target.obj_id})!"
            )
        return self.target

    def __repr__(self) -> str:
        return f"<UnownedRef -> {self.target}>"

@dataclass
class HeapStats:
    total_allocated: int = 0
    arc_allocated: int = 0
    gc_allocated: int = 0
    arc_deallocated: int = 0
    gc_collected: int = 0
    collections_run: int = 0

    def arc_live(self) -> int:
        return self.arc_allocated - self.arc_deallocated

    def gc_live(self) -> int:
        return self.gc_allocated - self.gc_collected

class HybridMemoryCoordinator:
    def __init__(self):
        self.next_obj_id = 1
        self.stats = HeapStats()

        # ARC Heap
        self.arc_objects: Dict[int, BlumeObject] = {}

        # GC Heap & Roots
        self.gc_objects: Dict[int, BlumeObject] = {}
        # gc_roots maps slot_name -> callable or getter that returns the current object
        self.gc_root_slots: Dict[str, Callable[[], Any]] = {}
        self.gc_explicit_roots: Set[int] = set()

        # Cross-Domain Bridge:
        # 1. ARC object holding GC object -> GC object is kept as a bridged root while ARC object lives
        # arc_obj_id -> set of gc_obj_ids
        self.bridge_arc_to_gc: Dict[int, Set[int]] = {}

        # 2. GC object holding ARC object -> GC object holds an ARC retain count
        # gc_obj_id -> list of arc_obj_ids
        self.bridge_gc_to_arc: Dict[int, List[int]] = {}

        # GC Trigger threshold
        self.gc_threshold = 100
        self.alloc_counter = 0

    # ---------------- Allocation (blume.alloc) ----------------

    def allocate(
        self,
        class_name: str,
        domain: OwnershipKind,
        fields: Optional[List[str]] = None,
        deinit_fn: Optional[Callable[[BlumeObject], None]] = None
    ) -> BlumeObject:
        obj_id = self.next_obj_id
        self.next_obj_id += 1

        field_dict = {fld: None for fld in (fields or [])}
        obj = BlumeObject(
            obj_id=obj_id,
            class_name=class_name,
            domain=domain,
            fields=field_dict,
            retain_count=1,
            is_alive=True,
            deinit_fn=deinit_fn
        )

        self.stats.total_allocated += 1
        self.alloc_counter += 1

        if domain == OwnershipKind.OWNED:
            self.stats.arc_allocated += 1
            self.arc_objects[obj_id] = obj
        else: # SHARED
            self.stats.gc_allocated += 1
            self.gc_objects[obj_id] = obj

        # Auto GC trigger if threshold reached
        if self.alloc_counter >= self.gc_threshold:
            self.collect_garbage()
            self.alloc_counter = 0

        return obj

    # ---------------- Swift-Inspired ARC Operations ----------------

    def retain(self, obj: Any) -> int:
        if not isinstance(obj, BlumeObject):
            return 0
        if obj.domain != OwnershipKind.OWNED:
            return -1 # Not ARC managed
        if not obj.is_alive:
            raise BlumeRuntimeError(f"Attempted to retain already deallocated object: {obj}")

        obj.retain_count += 1
        return obj.retain_count

    def release(self, obj: Any) -> int:
        if not isinstance(obj, BlumeObject):
            return 0
        if obj.domain != OwnershipKind.OWNED:
            return -1 # Not ARC managed
        if not obj.is_alive:
            return 0

        obj.retain_count -= 1
        if obj.retain_count <= 0:
            self._deallocate_arc_object(obj)
            return 0
        return obj.retain_count

    def _deallocate_arc_object(self, obj: BlumeObject):
        if not obj.is_alive:
            return

        obj.is_alive = False
        self.stats.arc_deallocated += 1

        # 1. Execute deterministic deinit callback
        if obj.deinit_fn:
            try:
                obj.deinit_fn(obj)
            except Exception as e:
                print(f"[Blume Runtime] Exception in deinit for {obj}: {e}")

        # 2. Invalidate weak references
        for wref in obj.weak_refs:
            wref.target_deallocated()
        obj.weak_refs.clear()

        # 3. Clean up cross-domain bridged roots held by this ARC object
        if obj.obj_id in self.bridge_arc_to_gc:
            del self.bridge_arc_to_gc[obj.obj_id]

        # 4. Release any ARC fields this object was holding
        for fld_val in obj.fields.values():
            if isinstance(fld_val, BlumeObject) and fld_val.domain == OwnershipKind.OWNED:
                self.release(fld_val)

        # 5. Remove from arc_objects
        if obj.obj_id in self.arc_objects:
            del self.arc_objects[obj.obj_id]

    def create_weak_ref(self, obj: Any) -> BlumeWeakRef:
        if isinstance(obj, BlumeObject):
            return BlumeWeakRef(obj)
        elif isinstance(obj, BlumeWeakRef):
            return obj
        return BlumeWeakRef(None)

    def create_unowned_ref(self, obj: Any) -> BlumeUnownedRef:
        if not isinstance(obj, BlumeObject):
            raise BlumeRuntimeError(f"Cannot create unowned reference to non-object: {obj}")
        return BlumeUnownedRef(obj)

    # ---------------- Kotlin-Inspired GC Operations ----------------

    def register_gc_root_slot(self, slot_name: str, getter: Callable[[], Any]):
        self.gc_root_slots[slot_name] = getter

    def unregister_gc_root_slot(self, slot_name: str):
        if slot_name in self.gc_root_slots:
            del self.gc_root_slots[slot_name]

    def add_explicit_gc_root(self, obj_id: int):
        self.gc_explicit_roots.add(obj_id)

    def remove_explicit_gc_root(self, obj_id: int):
        self.gc_explicit_roots.discard(obj_id)

    def collect_garbage(self) -> int:
        """
        Tracing Garbage Collector: Mark-and-Sweep.
        Traces all reachable objects from GC roots and Cross-Domain Bridge roots,
        reclaiming unreferenced objects and cyclic references.
        """
        self.stats.collections_run += 1

        # 1. Gather all roots
        visited_ids: Set[int] = set()
        queue: List[BlumeObject] = []

        # From stack root slots
        for getter in list(self.gc_root_slots.values()):
            try:
                val = getter()
                if isinstance(val, BlumeObject) and val.domain == OwnershipKind.SHARED and val.is_alive:
                    if val.obj_id not in visited_ids:
                        visited_ids.add(val.obj_id)
                        queue.append(val)
            except Exception:
                pass

        # From explicit roots
        for obj_id in self.gc_explicit_roots:
            if obj_id in self.gc_objects and self.gc_objects[obj_id].is_alive:
                if obj_id not in visited_ids:
                    visited_ids.add(obj_id)
                    queue.append(self.gc_objects[obj_id])

        # From Cross-Domain Bridge roots (ARC objects holding GC objects)
        for arc_id, gc_ids in self.bridge_arc_to_gc.items():
            if arc_id in self.arc_objects and self.arc_objects[arc_id].is_alive:
                for gc_id in gc_ids:
                    if gc_id in self.gc_objects and self.gc_objects[gc_id].is_alive:
                        if gc_id not in visited_ids:
                            visited_ids.add(gc_id)
                            queue.append(self.gc_objects[gc_id])

        # 2. Mark Phase (Reachability Analysis)
        while queue:
            curr = queue.pop(0)
            for fld_val in curr.fields.values():
                if isinstance(fld_val, BlumeObject) and fld_val.domain == OwnershipKind.SHARED and fld_val.is_alive:
                    if fld_val.obj_id not in visited_ids:
                        visited_ids.add(fld_val.obj_id)
                        queue.append(fld_val)
                elif isinstance(fld_val, list):
                    for item in fld_val:
                        if isinstance(item, BlumeObject) and item.domain == OwnershipKind.SHARED and item.is_alive:
                            if item.obj_id not in visited_ids:
                                visited_ids.add(item.obj_id)
                                queue.append(item)

        # 3. Sweep Phase
        unreachable_ids = [oid for oid in self.gc_objects if oid not in visited_ids]
        collected_count = 0

        for oid in unreachable_ids:
            dead_obj = self.gc_objects[oid]
            dead_obj.is_alive = False
            collected_count += 1
            self.stats.gc_collected += 1

            # Execute deinit if present
            if dead_obj.deinit_fn:
                try:
                    dead_obj.deinit_fn(dead_obj)
                except Exception as e:
                    print(f"[Blume Runtime] Exception in deinit for GC {dead_obj}: {e}")

            # Clean up bridged ARC retain handles held by this GC object
            if oid in self.bridge_gc_to_arc:
                for arc_id in self.bridge_gc_to_arc[oid]:
                    if arc_id in self.arc_objects:
                        self.release(self.arc_objects[arc_id])
                del self.bridge_gc_to_arc[oid]

            # Invalidate weak refs
            for wref in dead_obj.weak_refs:
                wref.target_deallocated()
            dead_obj.weak_refs.clear()

            del self.gc_objects[oid]

        return collected_count

    # ---------------- Cross-Domain Bridge Management (blume.bridge) ----------------

    def bridge_reference(self, source_obj: Any, field_name: str, target_val: Any):
        """
        Coordinates cross-domain memory safety when storing references between ARC and GC domains.
        """
        if not isinstance(source_obj, BlumeObject) or not isinstance(target_val, BlumeObject):
            return

        # Case 1: ARC (owned) object references GC (shared) object
        # -> Target GC object registered as bridged root while ARC container is alive
        if source_obj.domain == OwnershipKind.OWNED and target_val.domain == OwnershipKind.SHARED:
            if source_obj.obj_id not in self.bridge_arc_to_gc:
                self.bridge_arc_to_gc[source_obj.obj_id] = set()
            self.bridge_arc_to_gc[source_obj.obj_id].add(target_val.obj_id)

        # Case 2: GC (shared) object references ARC (owned) object
        # -> Container GC object retains target ARC object until container is collected by GC
        elif source_obj.domain == OwnershipKind.SHARED and target_val.domain == OwnershipKind.OWNED:
            if source_obj.obj_id not in self.bridge_gc_to_arc:
                self.bridge_gc_to_arc[source_obj.obj_id] = []
            self.retain(target_val)
            self.bridge_gc_to_arc[source_obj.obj_id].append(target_val.obj_id)

    # ---------------- Diagnostics & Stats ----------------

    def print_heap_stats(self):
        print("====== Blume Hybrid Memory Coordinator Stats ======")
        print(f"Total Allocations:   {self.stats.total_allocated}")
        print(f"ARC Allocations:     {self.stats.arc_allocated}")
        print(f"ARC Deallocations:   {self.stats.arc_deallocated} (Deterministic)")
        print(f"ARC Live Objects:    {self.stats.arc_live()}")
        print(f"GC Allocations:      {self.stats.gc_allocated}")
        print(f"GC Collections:      {self.stats.collections_run}")
        print(f"GC Objects Swept:    {self.stats.gc_collected} (Cycles Collected)")
        print(f"GC Live Objects:     {self.stats.gc_live()}")
        print(f"Active Cross-Bridges:{len(self.bridge_arc_to_gc) + len(self.bridge_gc_to_arc)}")
        print("====================================================")
