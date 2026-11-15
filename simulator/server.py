#!/usr/bin/env python3
"""
Blume Studio Mobile Simulator Server
Runs the exact Blume VM and Memory Coordinator to power the Android App interactive web preview.
"""

import os
import sys
import json
import time
import io
from http.server import HTTPServer, SimpleHTTPRequestHandler

# Add blume package to sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, "..", ".."))
BLUME_DIR = os.path.join(PROJECT_ROOT, "blume-main")
if BLUME_DIR not in sys.path:
    sys.path.insert(0, BLUME_DIR)

try:
    from blume.lexer import Lexer
    from blume.parser import Parser
    from blume.type_checker import TypeChecker
    from blume.ownership_analyzer import OwnershipAnalyzer
    from blume.ir_generator import IRGenerator
    from blume.vm import BlumeVM
    from blume.runtime import HybridMemoryCoordinator
    from blume.repl import BlumeREPL
except ImportError as e:
    print(f"Error importing Blume: {e}")

global_coordinator = HybridMemoryCoordinator()
global_repl = BlumeREPL()

class BlumeAppHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=BASE_DIR, **kwargs)

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
        try:
            body = json.loads(post_data) if post_data else {}
        except Exception:
            body = {}

        if self.path == "/api/run":
            self.handle_run(body)
        elif self.path == "/api/repl":
            self.handle_repl(body)
        elif self.path == "/api/collect":
            self.handle_collect()
        else:
            self.send_response(404)
            self.end_headers()

    def do_GET(self):
        if self.path == "/api/examples":
            self.handle_examples()
        else:
            super().do_GET()

    def handle_run(self, body):
        global global_coordinator
        code = body.get("code", "")
        start_time = time.time()
        output_io = io.StringIO()
        old_stdout = sys.stdout

        try:
            sys.stdout = output_io

            lexer = Lexer(code, "<editor>")
            tokens = lexer.tokenize()

            parser = Parser(tokens)
            ast = parser.parse()

            type_checker = TypeChecker()
            type_checker.check_program(ast)

            analyzer = OwnershipAnalyzer()
            analyzer.analyze_program(ast)

            ir_gen = IRGenerator(analyzer)
            ir_module = ir_gen.generate(ast)
            mir_text = str(ir_module)

            global_coordinator = HybridMemoryCoordinator()
            vm = BlumeVM(ir_module, coordinator=global_coordinator)
            vm.capture_output = True
            vm.execute()

            for line in vm.output_buffer:
                print(line)

            duration_ms = int((time.time() - start_time) * 1000)
            sys.stdout = old_stdout
            captured = output_io.getvalue()

            arc_objs = [
                {"id": o.obj_id, "class": o.class_name, "rc": o.retain_count}
                for o in global_coordinator.arc_objects.values()
            ]
            gc_objs = [
                {"id": o.obj_id, "class": o.class_name}
                for o in global_coordinator.gc_objects.values()
            ]

            res = {
                "success": True,
                "output": captured,
                "mir": mir_text,
                "timeMs": duration_ms,
                "stats": {
                    "arcLive": global_coordinator.stats.arc_live(),
                    "arcDeallocated": global_coordinator.stats.arc_deallocated,
                    "gcLive": global_coordinator.stats.gc_live(),
                    "gcCollected": global_coordinator.stats.gc_collected,
                    "activeBridges": len(global_coordinator.bridge_arc_to_gc) + len(global_coordinator.bridge_gc_to_arc)
                },
                "arcObjects": arc_objs,
                "gcObjects": gc_objs
            }
        except Exception as e:
            sys.stdout = old_stdout
            duration_ms = int((time.time() - start_time) * 1000)
            res = {
                "success": False,
                "output": output_io.getvalue() + f"\nBlume Error: {e}",
                "mir": "",
                "timeMs": duration_ms,
                "stats": {
                    "arcLive": 0, "arcDeallocated": 0, "gcLive": 0, "gcCollected": 0, "activeBridges": 0
                },
                "arcObjects": [], "gcObjects": []
            }

        self.send_json(res)

    def handle_collect(self):
        global global_coordinator
        collected = global_coordinator.collect_garbage()
        res = {
            "success": True,
            "collected": collected,
            "stats": {
                "arcLive": global_coordinator.stats.arc_live(),
                "arcDeallocated": global_coordinator.stats.arc_deallocated,
                "gcLive": global_coordinator.stats.gc_live(),
                "gcCollected": global_coordinator.stats.gc_collected,
                "activeBridges": len(global_coordinator.bridge_arc_to_gc) + len(global_coordinator.bridge_gc_to_arc)
            }
        }
        self.send_json(res)

    def handle_repl(self, body):
        global global_repl
        line = body.get("line", "").strip()

        if line in (":mem", ":heap"):
            io_buf = io.StringIO()
            old = sys.stdout
            sys.stdout = io_buf
            global_repl.coordinator.print_heap_stats()
            sys.stdout = old
            self.send_json({"output": io_buf.getvalue(), "prompt": "blume> "})
            return
        elif line == ":collect":
            swept = global_repl.coordinator.collect_garbage()
            self.send_json({"output": f"Garbage collection executed: {swept} cyclic object(s) collected.", "prompt": "blume> "})
            return
        elif line == ":reset":
            global_repl.reset()
            self.send_json({"output": "Blume runtime heaps and environment reset.", "prompt": "blume> "})
            return

        io_buf = io.StringIO()
        old = sys.stdout
        sys.stdout = io_buf
        try:
            val = global_repl.eval_line(line)
            if val is not None:
                print(f"=> {val}")
        except Exception as e:
            print(f"Error: {e}")
        finally:
            sys.stdout = old

        self.send_json({"output": io_buf.getvalue(), "prompt": "blume> "})

    def handle_examples(self):
        examples_dir = os.path.join(PROJECT_ROOT, "blume-main", "examples")
        data = []
        if os.path.exists(examples_dir):
            for fname in sorted(os.listdir(examples_dir)):
                if fname.endswith(".blume"):
                    fpath = os.path.join(examples_dir, fname)
                    with open(fpath, "r", encoding="utf-8") as f:
                        data.append({
                            "name": fname,
                            "title": fname.replace("_", " ").replace(".blume", "").title(),
                            "code": f.read()
                        })
        self.send_json({"examples": data})

    def send_json(self, data):
        payload = json.dumps(data).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

if __name__ == "__main__":
    port = 8088
    if len(sys.argv) > 1:
        port = int(sys.argv[1])
    server = HTTPServer(("0.0.0.0", port), BlumeAppHandler)
    print(f"🌸 Blume Studio Android Web Simulator listening on http://localhost:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
