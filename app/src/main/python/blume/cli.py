"""
Blume Programming Language - Command Line Interface (CLI)
Version: 1.0
"One Language. Two Memory Models. One Unified IR."
100% Pure Python Implementation
"""

import sys
import os
import argparse
from blume.lexer import Lexer
from blume.parser import Parser
from blume.type_checker import TypeChecker
from blume.ownership_analyzer import OwnershipAnalyzer
from blume.ir_generator import IRGenerator
from blume.llvm_emitter import LLVMEmitter
from blume.runtime import HybridMemoryCoordinator
from blume.vm import BlumeVM
from blume.repl import BlumeREPL

def compile_and_get_ir(source: str, filename: str = "<input>"):
    lexer = Lexer(source, filename=filename)
    tokens = lexer.tokenize()

    parser = Parser(tokens)
    ast = parser.parse()

    type_checker = TypeChecker()
    type_checker.check_program(ast)

    analyzer = OwnershipAnalyzer()
    analyzer.analyze_program(ast)

    ir_gen = IRGenerator(analyzer)
    ir_module = ir_gen.generate(ast)

    return ast, analyzer, ir_module

def cmd_run(args):
    if not os.path.exists(args.file):
        print(f"Error: File '{args.file}' not found.")
        sys.exit(1)

    with open(args.file, "r", encoding="utf-8") as f:
        source = f.read()

    try:
        _, _, ir_module = compile_and_get_ir(source, filename=args.file)
        coordinator = HybridMemoryCoordinator()
        vm = BlumeVM(ir_module, coordinator=coordinator)
        vm.execute()
        if args.stats:
            coordinator.print_heap_stats()
    except Exception as e:
        print(f"Blume Execution Error: {e}", file=sys.stderr)
        sys.exit(1)

def cmd_ir(args):
    if not os.path.exists(args.file):
        print(f"Error: File '{args.file}' not found.")
        sys.exit(1)

    with open(args.file, "r", encoding="utf-8") as f:
        source = f.read()

    try:
        _, _, ir_module = compile_and_get_ir(source, filename=args.file)
        print(ir_module)
    except Exception as e:
        print(f"Blume IR Error: {e}", file=sys.stderr)
        sys.exit(1)

def cmd_llvm(args):
    if not os.path.exists(args.file):
        print(f"Error: File '{args.file}' not found.")
        sys.exit(1)

    with open(args.file, "r", encoding="utf-8") as f:
        source = f.read()

    try:
        _, _, ir_module = compile_and_get_ir(source, filename=args.file)
        emitter = LLVMEmitter(ir_module)
        llvm_text = emitter.emit()

        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(llvm_text)
            print(f"Wrote LLVM IR to {args.output}")
        else:
            print(llvm_text)
    except Exception as e:
        print(f"Blume LLVM Lowering Error: {e}", file=sys.stderr)
        sys.exit(1)

def cmd_check(args):
    if not os.path.exists(args.file):
        print(f"Error: File '{args.file}' not found.")
        sys.exit(1)

    with open(args.file, "r", encoding="utf-8") as f:
        source = f.read()

    try:
        ast, analyzer, ir_mod = compile_and_get_ir(source, filename=args.file)
        print(f"Check successful: '{args.file}' parsed and type-checked cleanly.")
        if analyzer.diagnostics:
            print(f"\nOwnership Diagnostics ({len(analyzer.diagnostics)}):")
            for diag in analyzer.diagnostics:
                prefix = "Warning" if diag.is_warning else "Note"
                print(f"  [{prefix}] {diag.message} at {diag.loc}")
        if analyzer.bridge_edges:
            print(f"\nIdentified Cross-Domain Bridges ({len(analyzer.bridge_edges)}):")
            for edge in analyzer.bridge_edges:
                print(f"  {edge.source_domain.value} -> {edge.target_domain.value} on {edge.source_var_or_field} ({edge.loc})")
    except Exception as e:
        print(f"Check Failed: {e}", file=sys.stderr)
        sys.exit(1)

def cmd_repl(args):
    repl = BlumeREPL()
    repl.start()

def cmd_test(args):
    import unittest
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    tests_dir = os.path.join(project_root, "tests")
    print(f"Running Blume test suite from {tests_dir}...")
    loader = unittest.TestLoader()
    suite = loader.discover(tests_dir, pattern="test_*.py")
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    if not result.wasSuccessful():
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(
        prog="blume",
        description="Blume Programming Language - One Language. Two Memory Models. One Unified IR."
    )
    subparsers = parser.add_subparsers(dest="command", help="Blume commands")

    # Run
    run_p = subparsers.add_parser("run", help="Run a Blume source file")
    run_p.add_argument("file", help="Path to .blume source file")
    run_p.add_argument("--stats", action="store_true", help="Print hybrid heap statistics after execution")
    run_p.set_defaults(func=cmd_run)

    # IR
    ir_p = subparsers.add_parser("ir", help="Generate and inspect Blume Memory IR")
    ir_p.add_argument("file", help="Path to .blume source file")
    ir_p.set_defaults(func=cmd_ir)

    # LLVM
    llvm_p = subparsers.add_parser("llvm", help="Emit LLVM IR (.ll) for native code generation")
    llvm_p.add_argument("file", help="Path to .blume source file")
    llvm_p.add_argument("-o", "--output", help="Output .ll file path")
    llvm_p.set_defaults(func=cmd_llvm)

    # Check
    check_p = subparsers.add_parser("check", help="Syntax, type checking, and ownership analysis")
    check_p.add_argument("file", help="Path to .blume source file")
    check_p.set_defaults(func=cmd_check)

    # REPL
    repl_p = subparsers.add_parser("repl", help="Start the interactive Blume REPL")
    repl_p.set_defaults(func=cmd_repl)

    # Test
    test_p = subparsers.add_parser("test", help="Run the Blume language test suite")
    test_p.set_defaults(func=cmd_test)

    args = parser.parse_args()
    if args.command is None:
        cmd_repl(args)
    else:
        args.func(args)

if __name__ == "__main__":
    main()
