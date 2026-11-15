package com.blume.studio.ui

import android.content.Context
import android.graphics.Color
import android.graphics.Typeface
import android.text.Editable
import android.text.Spannable
import android.text.TextWatcher
import android.text.style.ForegroundColorSpan
import android.text.style.StyleSpan
import android.util.AttributeSet
import androidx.appcompat.widget.AppCompatEditText
import java.util.regex.Pattern

class CodeEditorView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
    defStyleAttr: Int = android.R.attr.editTextStyle
) : AppCompatEditText(context, attrs, defStyleAttr) {

    private var isFormatting = false

    companion object {
        // Highlighting Colors
        private val COLOR_KEYWORD = Color.parseColor("#FF4081")       // Pink
        private val COLOR_OWNERSHIP = Color.parseColor("#00E5FF")     // Cyan
        private val COLOR_STRING = Color.parseColor("#A6E22E")        // Lime green
        private val COLOR_NUMBER = Color.parseColor("#FD971F")        // Orange
        private val COLOR_COMMENT = Color.parseColor("#75715E")       // Gray
        private val COLOR_TYPE = Color.parseColor("#66D9EF")          // Light Blue

        private val PATTERN_KEYWORDS = Pattern.compile(
            "\\b(fn|let|var|class|struct|init|deinit|if|else|while|for|in|return|defer|self|new)\\b"
        )
        private val PATTERN_OWNERSHIP = Pattern.compile(
            "\\b(owned|shared|weak|unowned|automatic)\\b"
        )
        private val PATTERN_LITERALS = Pattern.compile(
            "\\b(true|false|nil)\\b"
        )
        private val PATTERN_STRINGS = Pattern.compile(
            "\"(\\\\.|[^\"\\\\])*\""
        )
        private val PATTERN_NUMBERS = Pattern.compile(
            "\\b\\d+(\\.\\d+)?\\b"
        )
        private val PATTERN_COMMENTS = Pattern.compile(
            "//.*|/\\*[\\s\\S]*?\\*/"
        )
        private val PATTERN_TYPES = Pattern.compile(
            "\\b(Int|Float|String|Bool|Void)\\b"
        )
    }

    init {
        typeface = Typeface.MONOSPACE
        textSize = 14f
        setBackgroundColor(Color.TRANSPARENT)
        setTextColor(Color.parseColor("#F4F4F8"))

        addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {}
            override fun afterTextChanged(s: Editable?) {
                if (isFormatting || s == null) return
                highlightSyntax(s)
            }
        })
    }

    private fun highlightSyntax(editable: Editable) {
        isFormatting = true

        // Clear existing spans
        val existingSpans = editable.getSpans(0, editable.length, ForegroundColorSpan::class.java)
        for (span in existingSpans) {
            editable.removeSpan(span)
        }

        // Apply Syntax Rules
        applyPattern(editable, PATTERN_KEYWORDS, COLOR_KEYWORD, isBold = true)
        applyPattern(editable, PATTERN_OWNERSHIP, COLOR_OWNERSHIP, isBold = true)
        applyPattern(editable, PATTERN_TYPES, COLOR_TYPE)
        applyPattern(editable, PATTERN_LITERALS, COLOR_NUMBER)
        applyPattern(editable, PATTERN_NUMBERS, COLOR_NUMBER)
        applyPattern(editable, PATTERN_STRINGS, COLOR_STRING)
        applyPattern(editable, PATTERN_COMMENTS, COLOR_COMMENT)

        isFormatting = false
    }

    private fun applyPattern(
        editable: Editable,
        pattern: Pattern,
        color: Int,
        isBold: Boolean = false
    ) {
        val matcher = pattern.matcher(editable)
        while (matcher.find()) {
            editable.setSpan(
                ForegroundColorSpan(color),
                matcher.start(),
                matcher.end(),
                Spannable.SPAN_EXCLUSIVE_EXCLUSIVE
            )
            if (isBold) {
                editable.setSpan(
                    StyleSpan(Typeface.BOLD),
                    matcher.start(),
                    matcher.end(),
                    Spannable.SPAN_EXCLUSIVE_EXCLUSIVE
                )
            }
        }
    }
}
