package com.blume.studio

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.*
import androidx.activity.viewModels
import androidx.appcompat.app.AppCompatActivity
import androidx.fragment.app.Fragment
import androidx.viewpager2.adapter.FragmentStateAdapter
import androidx.viewpager2.widget.ViewPager2
import com.blume.studio.databinding.ActivityMainBinding
import com.blume.studio.ui.CodeEditorView
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import com.google.android.material.tabs.TabLayoutMediator

class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    val viewModel: BlumeStudioViewModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        setupViewPager()
        setupTopBarActions()
    }

    private fun setupViewPager() {
        val adapter = StudioPagerAdapter(this)
        binding.viewPager.adapter = adapter
        binding.viewPager.offscreenPageLimit = 4

        val tabTitles = listOf(
            getString(R.string.tab_editor),
            getString(R.string.tab_console),
            getString(R.string.tab_memory),
            getString(R.string.tab_mir),
            getString(R.string.tab_repl)
        )

        TabLayoutMediator(binding.tabLayout, binding.viewPager) { tab, position ->
            tab.text = tabTitles[position]
        }.attach()
    }

    private fun setupTopBarActions() {
        // Run code button
        binding.btnRun.setOnClickListener {
            viewModel.runCode()
            // Switch to console or memory view
            binding.viewPager.currentItem = 1
        }

        // Examples picker dialog
        binding.btnExamples.setOnClickListener {
            val exampleNames = viewModel.exampleList.map { it.second }.toTypedArray()
            MaterialAlertDialogBuilder(this)
                .setTitle("Select Blume Example")
                .setItems(exampleNames) { _, which ->
                    val chosenFile = viewModel.exampleList[which].first
                    viewModel.loadExample(chosenFile)
                    binding.viewPager.currentItem = 0
                }
                .show()
        }

        viewModel.isRunning.observe(this) { running ->
            binding.btnRun.isEnabled = !running
            binding.btnRun.text = if (running) getString(R.string.status_running) else getString(R.string.action_run)
        }
    }

    inner class StudioPagerAdapter(activity: AppCompatActivity) : FragmentStateAdapter(activity) {
        override fun getItemCount(): Int = 5

        override fun createFragment(position: Int): Fragment {
            return when (position) {
                0 -> EditorFragment()
                1 -> ConsoleFragment()
                2 -> MemoryFragment()
                3 -> MirFragment()
                4 -> ReplFragment()
                else -> EditorFragment()
            }
        }
    }

    // ---------------- Fragments ----------------

    class EditorFragment : Fragment() {
        override fun onCreateView(inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?): View? {
            val root = inflater.inflate(R.layout.fragment_editor, container, false)
            val editor = root.findViewById<CodeEditorView>(R.id.editor)
            val activity = requireActivity() as MainActivity

            activity.viewModel.sourceCode.observe(viewLifecycleOwner) { code ->
                if (editor.text.toString() != code) {
                    editor.setText(code)
                }
            }

            editor.setOnFocusChangeListener { _, _ ->
                activity.viewModel.sourceCode.value = editor.text.toString()
            }

            // Quick symbol bar wiring
            fun insertText(str: String) {
                val start = editor.selectionStart.coerceAtLeast(0)
                val end = editor.selectionEnd.coerceAtLeast(0)
                editor.text?.replace(start.coerceAtMost(end), start.coerceAtLeast(end), str)
            }

            root.findViewById<Button>(R.id.symOwned)?.setOnClickListener { insertText("owned ") }
            root.findViewById<Button>(R.id.symShared)?.setOnClickListener { insertText("shared ") }
            root.findViewById<Button>(R.id.symWeak)?.setOnClickListener { insertText("weak ") }
            root.findViewById<Button>(R.id.symFn)?.setOnClickListener { insertText("fn ") }
            root.findViewById<Button>(R.id.symClass)?.setOnClickListener { insertText("class ") }
            root.findViewById<Button>(R.id.symArrow)?.setOnClickListener { insertText(" -> ") }
            root.findViewById<Button>(R.id.symBraces)?.setOnClickListener { insertText("{\n    \n}") }
            root.findViewById<Button>(R.id.symParens)?.setOnClickListener { insertText("()") }
            root.findViewById<Button>(R.id.symRange)?.setOnClickListener { insertText("..") }
            root.findViewById<Button>(R.id.symColon)?.setOnClickListener { insertText(": ") }

            return root
        }

        override fun onPause() {
            super.onPause()
            val editor = view?.findViewById<CodeEditorView>(R.id.editor)
            val activity = activity as? MainActivity
            if (editor != null && activity != null) {
                activity.viewModel.sourceCode.value = editor.text.toString()
            }
        }
    }

    class ConsoleFragment : Fragment() {
        override fun onCreateView(inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?): View? {
            val root = inflater.inflate(R.layout.fragment_console, container, false)
            val tvConsole = root.findViewById<TextView>(R.id.tvConsoleOutput)
            val btnClear = root.findViewById<Button>(R.id.btnClearConsole)
            val activity = requireActivity() as MainActivity

            activity.viewModel.consoleOutput.observe(viewLifecycleOwner) { out ->
                tvConsole.text = out
            }

            btnClear.setOnClickListener {
                activity.viewModel.clearConsole()
            }

            return root
        }
    }

    class MemoryFragment : Fragment() {
        override fun onCreateView(inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?): View? {
            val root = inflater.inflate(R.layout.fragment_memory, container, false)
            val tvArcLive = root.findViewById<TextView>(R.id.tvArcLiveCount)
            val tvArcDealloc = root.findViewById<TextView>(R.id.tvArcDeallocCount)
            val tvGcLive = root.findViewById<TextView>(R.id.tvGcLiveCount)
            val tvGcCollected = root.findViewById<TextView>(R.id.tvGcCollectedCount)
            val tvBridge = root.findViewById<TextView>(R.id.tvBridgeCount)
            val tvDump = root.findViewById<TextView>(R.id.tvMemoryDump)
            val btnCollect = root.findViewById<Button>(R.id.btnCollectGC)
            val activity = requireActivity() as MainActivity

            activity.viewModel.memorySnapshot.observe(viewLifecycleOwner) { snapshot ->
                if (snapshot != null) {
                    tvArcLive.text = "${snapshot.stats.arcLive()}"
                    tvArcDealloc.text = "${snapshot.stats.arcDeallocated} deallocations"
                    tvGcLive.text = "${snapshot.stats.gcLive()}"
                    tvGcCollected.text = "${snapshot.stats.gcCollected} cycles swept"
                    tvBridge.text = "${snapshot.activeBridgesCount}"

                    val sb = StringBuilder()
                    sb.append("=== Swift-Inspired ARC Heap ===\n")
                    if (snapshot.arcObjects.isEmpty()) {
                        sb.append("(No active ARC objects)\n")
                    } else {
                        for (o in snapshot.arcObjects) {
                            sb.append("• [ID ${o.objId}] ${o.className} (rc=${o.retainCount})\n")
                        }
                    }

                    sb.append("\n=== Kotlin-Inspired GC Heap ===\n")
                    if (snapshot.gcObjects.isEmpty()) {
                        sb.append("(No active GC objects)\n")
                    } else {
                        for (o in snapshot.gcObjects) {
                            sb.append("• [ID ${o.objId}] ${o.className} (shared node)\n")
                        }
                    }
                    tvDump.text = sb.toString()
                }
            }

            btnCollect.setOnClickListener {
                activity.viewModel.triggerGC()
            }

            return root
        }
    }

    class MirFragment : Fragment() {
        override fun onCreateView(inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?): View? {
            val root = inflater.inflate(R.layout.fragment_mir, container, false)
            val tvMir = root.findViewById<TextView>(R.id.tvMirOutput)
            val activity = requireActivity() as MainActivity

            activity.viewModel.generatedMIR.observe(viewLifecycleOwner) { mir ->
                tvMir.text = if (mir.isNotEmpty()) mir else "; Tap 'Run' to compile and view Blume Memory IR."
            }

            return root
        }
    }

    class ReplFragment : Fragment() {
        override fun onCreateView(inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?): View? {
            val root = inflater.inflate(R.layout.fragment_repl, container, false)
            val tvLogs = root.findViewById<TextView>(R.id.tvReplLogs)
            val etInput = root.findViewById<EditText>(R.id.etReplInput)
            val btnSend = root.findViewById<ImageButton>(R.id.btnReplSend)
            val scroll = root.findViewById<ScrollView>(R.id.replScroll)
            val activity = requireActivity() as MainActivity

            activity.viewModel.replOutput.observe(viewLifecycleOwner) { logs ->
                if (logs.isNotEmpty()) {
                    tvLogs.text = logs
                    scroll.post { scroll.fullScroll(View.FOCUS_DOWN) }
                }
            }

            fun sendLine() {
                val text = etInput.text.toString().trim()
                if (text.isNotEmpty()) {
                    activity.viewModel.executeReplLine(text)
                    etInput.setText("")
                }
            }

            btnSend.setOnClickListener { sendLine() }
            etInput.setOnEditorActionListener { _, _, _ ->
                sendLine()
                true
            }

            root.findViewById<Button>(R.id.chipMem)?.setOnClickListener { etInput.setText(":mem"); sendLine() }
            root.findViewById<Button>(R.id.chipCollect)?.setOnClickListener { etInput.setText(":collect"); sendLine() }
            root.findViewById<Button>(R.id.chipIr)?.setOnClickListener { etInput.setText(":ir"); sendLine() }
            root.findViewById<Button>(R.id.chipReset)?.setOnClickListener { etInput.setText(":reset"); sendLine() }
            root.findViewById<Button>(R.id.chipHelp)?.setOnClickListener { etInput.setText(":help"); sendLine() }

            return root
        }
    }
}
