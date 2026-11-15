"""
Blume Programming Language - Interactive REPL & Memory Visualizer
Version: 1.0
"One Language. Two Memory Models. One Unified IR."
100% Pure Python Implementation
"""

import sys
import traceback
from blume.lexer import Lexer
from blume.parser import Parser
from blume.type_checker import TypeChecker
from blume.ownership_analyzer import OwnershipAnalyzer
from blume.ir_generator import IRGenerator
from blume.runtime import HybridMemoryCoordinator
from blume.vm import BlumeVM

BANNER = r"""
   ____  __    __  ____  ___  ____ 
  (  _ \(  )  (  )(  _ \(  _)(  __)
   ) _ ( )(__  )(  )   / ) _) ) _) 
  (____/(____)(__)(_)\_)(___)(____)
  
  Blume Programming Language (v1.0)
  One Language. Two Memory Models. One Unified IR.
  [Swift ARC + Kotlin Tracing GC + Blume Memory IR]
  Type :help for interactive commands, :mem for heap stats, :quit to exit.
"""

HELP_TEXT = """
Blume REPL Commands:
  :help           Show this help message
  :mem, :heap     Inspect Blume Hybrid Memory heap (ARC objects, GC objects, Bridge)
  :collect        Trigger Kotlin-inspired Tracing GC collection manually
  :ir             Toggle printing Blume Unified Memory IR for evaluated code
  :llvm           Emit LLVM IR for the current session
  :reset          Reset runtime state and heaps
  :quit, :exit    Exit the Blume REPL
"""

class BlumeREPL:
    def __init__(self):
        self.coordinator = HybridMemoryCoordinator()
        self.show_ir = False
        self.history: list[str] = []

    def start(self):
        print(BANNER)
        while True:
            try:
                line = input("blume> ").strip()
                if not line:
                    continue

                if line in (":quit", ":exit"):
                    print("Goodbye!")
                    break

                if line == ":help":
                    print(HELP_TEXT)
                    continue

                if line in (":mem", ":heap"):
                    self.coordinator.print_heap_stats()
                    self._print_live_objects()
                    continue

                if line == ":collect":
                    swept = self.coordinator.collect_garbage()
                    print(f"[Blume GC] Sweep complete. Collected {swept} unreachable object(s).")
                    continue

                if line == ":ir":
                    self.show_ir = not self.show_ir
                    print(f"Blume Memory IR printing: {'ON' if self.show_ir else 'OFF'}")
                    continue

                if line == ":reset":
                    self.coordinator = HybridMemoryCoordinator()
                    print("Blume Runtime heap reset.")
                    continue

                self.eval_line(line)

            except (KeyboardInterrupt, EOFError):
                print("\nGoodbye!")
                break
            except Exception as e:
                print(f"Error: {e}")

    def eval_line(self, code: str):
        try:
            lexer = Lexer(code, filename="<repl>")
            tokens = lexer.tokenize()

            parser = Parser(tokens)
            ast = parser.parse()

            type_checker = TypeChecker()
            type_checker.check_program(ast)

            analyzer = OwnershipAnalyzer()
            analyzer.analyze_program(ast)

            ir_gen = IRGenerator(analyzer)
            ir_mod = ir_gen.generate(ast)

            if self.show_ir:
                print("\n--- Blume Memory IR ---")
                print(ir_mod)
                print("-----------------------\n")

            vm = BlumeVM(ir_mod, coordinator=self.coordinator)
            res = vm.execute()
            if res is not None:
                print(f"=> {vm._format_val(res)}")

        except Exception as e:
            print(f"Error: {e}")

    def _print_live_objects(self):
        print("\n--- Live ARC Managed Objects (Swift Model) ---")
        if not self.coordinator.arc_objects:
            print("  (none)")
        for oid, obj in self.coordinator.arc_objects.items():
            print(f"  [{oid}] {obj.class_name}: retain_count={obj.retain_count}, fields={obj.fields}")

        print("\n--- Live GC Managed Objects (Kotlin Model) ---")
        if not self.coordinator.gc_objects:
            print("  (none)")
        for oid, obj in self.coordinator.gc_objects.items():
            print(f"  [{oid}] {obj.class_name}: fields={obj.fields}")

        print("\n--- Cross-Domain Bridges (blume.bridge) ---")
        arc_to_gc = self.coordinator.bridge_arc_to_gc
        gc_to_arc = self.coordinator.bridge_gc_to_arc
        if not arc_to_gc and not gc_to_arc:
            print("  (none)")
        for arc_id, gc_ids in arc_to_gc.items():
            print(f"  ARC object #{arc_id} -> keeps GC objects {list(gc_ids)} alive as GC Bridge Roots")
        for gc_id, arc_ids in gc_to_arc.items():
            print(f"  GC object #{gc_id} -> holds ARC Retain Handle on objects {arc_ids}")
        print()
