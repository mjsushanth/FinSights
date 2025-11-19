# ============================================================================
# File: ModelPipeline/finrag_ml_tg1/rag_modules_src/utilities/notebook_display.py
# ============================================================================
"""
Jupyter notebook display utilities for FinRAG synthesis results.

Provides clean, scrollable HTML rendering for query/answer comparisons
without emojis or excessive decoration.
"""

from html import escape
from typing import Optional, Dict, List, Any
from IPython.display import HTML, display


def display_qa_comparison(
    question_id: str,
    question_text: str,
    gold_answer: str | List[str],
    synthesis_output: str,
    metadata: Optional[Dict[str, Any]] = None,
    stdout_logs: Optional[str] = None,  # NEW: Separate logs section
    max_height: str = "400px",
    wrap_width: str = "95%",
) -> None:
    """
    Display gold answer vs synthesis output with Option B layout:
    - Top: Gold vs LLM side-by-side
    - Bottom: Expandable stdout logs section
    """
    # Sanitize inputs
    question_id_safe = escape(question_id)
    question_text_safe = escape(question_text)
    synthesis_output_safe = escape(synthesis_output)
    stdout_logs_safe = escape(stdout_logs) if stdout_logs else ""

    # Handle gold answer (may be list or string)
    if isinstance(gold_answer, list):
        gold_answer_html = "<br><br>".join([f"<strong>Item {i+1}:</strong><br>{escape(item)}" for i, item in enumerate(gold_answer)])
    else:
        gold_answer_html = escape(gold_answer)

    # Build metadata section
    meta_html = ""
    if metadata:
        meta_items = []
        for key, val in metadata.items():
            if isinstance(val, list):
                val_str = ", ".join(str(v) for v in val)
            else:
                val_str = str(val)
            meta_items.append(f"<span class='meta-item'><strong>{escape(key)}:</strong> {escape(val_str)}</span>")
        meta_html = " | ".join(meta_items)

    # Logs section (collapsible)
    logs_section = ""
    if stdout_logs:
        logs_section = f"""
        <details class="logs-details" open>
            <summary class="logs-summary">EXECUTION LOGS & METADATA</summary>
            <div class="logs-content">{stdout_logs_safe}</div>
        </details>
        """

    html = f"""
    <style>
        .qa-comparison {{
            font-family: 'Consolas', 'Courier New', monospace;
            background-color: #1e1e1e;
            border: 2px solid #3794ff;
            border-radius: 6px;
            overflow: hidden;
            margin: 15px 0;
            color: #d4d4d4;
        }}
        .qa-header {{
            background: #2d2d30;
            padding: 12px 20px;
            border-bottom: 1px solid #3794ff;
        }}
        .qa-id {{
            color: #4EC9B0;
            font-weight: bold;
            font-size: 16px;
            margin-bottom: 8px;
        }}
        .qa-question {{
            color: #d4d4d4;
            line-height: 1.6;
            margin-bottom: 10px;
            white-space: pre-wrap;
            word-wrap: break-word;
            max-width: {wrap_width};
        }}
        .qa-metadata {{
            color: #808080;
            font-size: 11px;
            padding-top: 8px;
            border-top: 1px solid #3e3e42;
        }}
        .meta-item {{
            margin-right: 12px;
        }}
        .qa-body {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 1px;
            background: #3e3e42;
        }}
        .qa-column {{
            background: #252526;
            padding: 15px 20px;
            max-height: {max_height};
            overflow-y: auto;
        }}
        .qa-column-label {{
            color: #4EC9B0;
            font-weight: bold;
            font-size: 13px;
            margin-bottom: 10px;
            position: sticky;
            top: 0;
            background: #252526;
            padding-bottom: 8px;
            border-bottom: 1px solid #3e3e42;
        }}
        .qa-content {{
            color: #d4d4d4;
            line-height: 1.7;
            white-space: pre-wrap;
            word-wrap: break-word;
            font-size: 13px;
        }}
        .logs-details {{
            background: #252526;
            border-top: 1px solid #3e3e42;
            padding: 15px 20px;
        }}
        .logs-summary {{
            color: #4EC9B0;
            font-weight: bold;
            font-size: 13px;
            cursor: pointer;
            padding: 5px 0;
            user-select: none;
        }}
        .logs-summary:hover {{
            color: #6CD9C0;
        }}
        .logs-content {{
            margin-top: 10px;
            padding: 15px;
            background: #1e1e1e;
            border-radius: 4px;
            color: #d4d4d4;
            font-size: 12px;
            line-height: 1.6;
            white-space: pre-wrap;
            max-height: 300px;
            overflow-y: auto;
        }}
        .qa-column::-webkit-scrollbar,
        .logs-content::-webkit-scrollbar {{
            width: 8px;
        }}
        .qa-column::-webkit-scrollbar-track,
        .logs-content::-webkit-scrollbar-track {{
            background: #1e1e1e;
        }}
        .qa-column::-webkit-scrollbar-thumb,
        .logs-content::-webkit-scrollbar-thumb {{
            background: #424242;
            border-radius: 4px;
        }}
        .qa-column::-webkit-scrollbar-thumb:hover,
        .logs-content::-webkit-scrollbar-thumb:hover {{
            background: #4e4e4e;
        }}
    </style>

    <div class="qa-comparison">
        <div class="qa-header">
            <div class="qa-id">TEST: {question_id_safe}</div>
            <div class="qa-question">{question_text_safe}</div>
            {f'<div class="qa-metadata">{meta_html}</div>' if meta_html else ''}
        </div>
        
        <div class="qa-body">
            <div class="qa-column">
                <div class="qa-column-label">GOLD REFERENCE ANSWER</div>
                <div class="qa-content">{gold_answer_html}</div>
            </div>
            
            <div class="qa-column">
                <div class="qa-column-label">LLM SYNTHESIS OUTPUT</div>
                <div class="qa-content">{synthesis_output_safe}</div>
            </div>
        </div>
        
        {logs_section}
    </div>
    """

    display(HTML(html))



def display_synthesis_result(
    question_text: str,
    synthesis_output: str,
    metadata: Optional[Dict[str, Any]] = None,
    max_height: str = "500px",
    wrap_width: str = "95%",
) -> None:
    """
    Display a single synthesis result with optional metadata footer.

    Args:
        question_text: The original question
        synthesis_output: LLM-generated synthesis response
        metadata: Optional dict with model, tokens, latency, sources, etc.
        max_height: CSS height for scrollable response area
        wrap_width: CSS width constraint for text wrapping
    """
    # Sanitize inputs
    question_text_safe = escape(question_text)
    synthesis_output_safe = escape(synthesis_output)

    # Build metadata footer
    meta_html = ""
    if metadata:
        meta_items = [f"<strong>{escape(str(k))}:</strong> {escape(str(v))}" for k, v in metadata.items()]
        meta_html = " | ".join(meta_items)

    html = f"""
    <style>
        .synthesis-result {{
            font-family: 'Consolas', 'Courier New', monospace;
            background-color: #1e1e1e;
            border: 2px solid #4CAF50;
            border-radius: 6px;
            overflow: hidden;
            margin: 15px 0;
            color: #d4d4d4;
        }}
        .synthesis-question {{
            padding: 15px 20px;
            background: #2d2d30;
            border-bottom: 1px solid #4CAF50;
        }}
        .synthesis-question-label {{
            color: #4EC9B0;
            font-weight: bold;
            font-size: 13px;
            margin-bottom: 8px;
        }}
        .synthesis-question-text {{
            color: #d4d4d4;
            line-height: 1.6;
            white-space: pre-wrap;
            word-wrap: break-word;
            font-size: 13px;
            max-width: {wrap_width};
        }}
        .synthesis-response {{
            padding: 15px 20px;
            background: #252526;
            max-height: {max_height};
            overflow-y: auto;
        }}
        .synthesis-response-label {{
            color: #4EC9B0;
            font-weight: bold;
            font-size: 13px;
            margin-bottom: 10px;
            position: sticky;
            top: 0;
            background: #252526;
            padding-bottom: 8px;
            border-bottom: 1px solid #3e3e42;
        }}
        .synthesis-content {{
            color: #d4d4d4;
            line-height: 1.7;
            white-space: pre-wrap;
            word-wrap: break-word;
            font-size: 13px;
        }}
        .synthesis-metadata {{
            padding: 10px 20px;
            background: #2d2d30;
            border-top: 1px solid #3e3e42;
            color: #808080;
            font-size: 11px;
        }}
        .synthesis-response::-webkit-scrollbar {{
            width: 8px;
        }}
        .synthesis-response::-webkit-scrollbar-track {{
            background: #1e1e1e;
        }}
        .synthesis-response::-webkit-scrollbar-thumb {{
            background: #424242;
            border-radius: 4px;
        }}
        .synthesis-response::-webkit-scrollbar-thumb:hover {{
            background: #4e4e4e;
        }}
    </style>

    <div class="synthesis-result">
        <div class="synthesis-question">
            <div class="synthesis-question-label">USER QUERY</div>
            <div class="synthesis-question-text">{question_text_safe}</div>
        </div>
        
        <div class="synthesis-response">
            <div class="synthesis-response-label">LLM SYNTHESIS</div>
            <div class="synthesis-content">{synthesis_output_safe}</div>
        </div>
        
        {f'<div class="synthesis-metadata">{meta_html}</div>' if meta_html else ''}
    </div>
    """

    display(HTML(html))