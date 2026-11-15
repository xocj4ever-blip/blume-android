# 🌸 Blume Studio Mobile (Android App)

> **Application:** Blume Studio Mobile  
> **Target:** Android (API Level 26–35+, Phone, Tablet, ChromeOS ARCVM)  
> **Language Engine:** Hybrid ARC + Tracing GC + Blume Memory IR (MIR)  
> **Implementation:** 100% Native Kotlin ART Engine + Bundled Python Engine  

---

## 📱 Overview

**Blume Studio Mobile** is a full-featured Android application for developing, compiling, inspecting, and running programs written in the **Blume programming language**. 

The app features Blume's signature dual-memory model:
1. **Swift-Inspired Automatic Reference Counting (ARC)**: Real-time retain/release tracking, deterministic `deinit` destruction upon scope exit, and `weak`/`unowned` references.
2. **Kotlin-Inspired Tracing Garbage Collection (GC)**: Root stack tracking, reachability analysis, and automated cycle reclamation for `shared` node graphs.
3. **Blume Unified Memory IR (MIR)**: Disassembles and displays the intermediate representation instructions (`blume.alloc`, `blume.retain`, `blume.release`, `blume.gc.root`, `blume.gc.collect`, `blume.bridge`, `blume.safepoint`).
4. **Interactive Live Memory Inspector**: Real-time visual monitoring of live ARC objects, retain counts, GC heaps, cross-domain bridges, and on-demand GC trigger.
5. **Interactive REPL Terminal**: REPL environment supporting statements, expressions, and commands (`:mem`, `:collect`, `:ir`, `:reset`, `:help`).

---

## 🏛️ Project Architecture

```
blume-android/
├── app/
│   ├── build.gradle.kts                   # Module build configuration (SDK 35, Java 17, Material 3)
│   ├── proguard-rules.pro
│   └── src/
│       ├── main/
│       │   ├── AndroidManifest.xml        # App declaration, launcher activity, themes
│       │   ├── java/com/blume/
│       │   │   ├── compiler/
│       │   │   │   ├── ast/AST.kt         # AST hierarchy (Program, Classes, Stmts, Exprs, OwnershipKind)
│       │   │   │   ├── lexer/BlumeLexer.kt# High-speed tokenizer
│       │   │   │   ├── parser/BlumeParser.kt # Recursive-descent AST parser
│       │   │   │   ├── analyzer/OwnershipAnalyzer.kt # Automatic ownership inference & bridge detection
│       │   │   │   └── ir/                # Blume Memory IR (MIR) model & generator
│       │   │   │       ├── BlumeIR.kt
│       │   │   │       └── BlumeIRGenerator.kt
│       │   │   ├── runtime/               # Hybrid Memory Coordinator
│       │   │   │   └── HybridMemoryCoordinator.kt # ARC retain/release + Tracing Mark-and-Sweep GC
│       │   │   ├── vm/
│       │   │   │   └── BlumeVM.kt         # Virtual Machine executing MIR instructions
│       │   │   ├── repl/
│       │   │   │   └── BlumeREPLEngine.kt # Interactive REPL evaluator
│       │   │   └── studio/
│       │   │       ├── MainActivity.kt    # Main activity with 5-tab ViewPager2
│       │   │       ├── BlumeStudioViewModel.kt # State management & coroutines
│       │   │       └── ui/
│       │   │           └── CodeEditorView.kt # Syntax highlighter & line editor
│       │   ├── res/                       # Layouts, colors, themes, vector icons
│       │   │   ├── layout/                # Editor, Console, Memory, MIR, REPL layouts
│       │   │   ├── values/                # Strings, Material 3 Dark theme, Blume palette
│       │   │   └── drawable/ic_blume_logo.xml # Vector 🌸 Cherry Blossom Logo
│       │   ├── assets/examples/           # Pre-bundled official Blume examples
│       │   └── python/blume/              # Bundled pure Python Blume package
│       └── test/java/com/blume/
│           └── BlumeEngineTest.kt         # Comprehensive JUnit test suite
├── gradle/
│   ├── libs.versions.toml                 # Version Catalog (AGP 8.7, Kotlin 2.0.21, Material 1.12)
│   └── wrapper/gradle-wrapper.properties
├── simulator/                             # Interactive Mobile Web Preview / Simulator
│   ├── server.py                          # Local VM backend
│   └── index.html                         # Interactive Android device mockup
├── build.gradle.kts                       # Root build configuration
├── settings.gradle.kts                    # Project repositories & modules
├── gradlew                                # Gradle wrapper script
└── run_app.sh                             # Immediate Web Simulator launcher
```

---

## ⚡ Quick Start: Interactive Preview

You can immediately test the Android application interface and run Blume scripts using the included mobile simulator:

```bash
cd /home/soistmancameronjames/blume-android
./run_app.sh
```

Then open your browser to:
👉 **`http://localhost:8088`**

### Features you can test right away:
- **Code Editor**: Type Blume code or insert symbols with the shortcut bar.
- **Examples**: Click `Examples` to load:
  1. *01 Fundamentals & Control Flow*
  2. *02 Swift-Inspired ARC & Deterministic Deinit*
  3. *03 Kotlin-Inspired Tracing GC & Cycle Collection*
  4. *04 Cross-Domain Bridge (`blume.bridge`)*
  5. *05 Non-Owning Weak References*
  6. *06 Defer Scope Cleanup (LIFO)*
  7. *07 Automatic Memory Strategy*
- **Run Button**: Compiles and executes with stdout, timing, and memory metrics.
- **Memory Inspector**: Live tracking of ARC objects, GC objects, bridge roots, and a manual `Collect GC` button.
- **MIR Disassembly**: Inspect the generated intermediate representation opcodes.
- **REPL**: Interactive terminal with `:mem`, `:collect`, `:ir`, and `:reset`.

---

## 🔨 Building the Android APK

### Option A: Using Android Studio
1. Open Android Studio.
2. Select **File -> Open...** and choose `/home/soistmancameronjames/blume-android`.
3. Allow Gradle to sync.
4. Click **Run 'app'** (or **Build -> Build Bundle(s) / APK(s) -> Build APK(s)**).

### Option B: Command Line (with Gradle installed)
```bash
cd /home/soistmancameronjames/blume-android
./gradlew assembleDebug
```
The output APK will be located at:
`app/build/outputs/apk/debug/app-debug.apk`

### Installing on ChromeOS or Android Devices
If ADB debugging is enabled on your Chromebook or connected device:
```bash
adb install -r app/build/outputs/apk/debug/app-debug.apk
```
