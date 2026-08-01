"""
Response cleaner - prevent Streamlit's dollar-sign LaTeX trigger without
destroying markdown formatting.

Background: Streamlit's st.markdown renders $...$ and $$...$$ as LaTeX math
by default, with no parameter to disable it (verified against current
Streamlit docs, 2026-08). Two earlier versions of this module (see
response_cleaner_bkv1.py) worked around this by stripping ALL markdown
emphasis (**bold**, *italic*, _underline-ish_) and either deleting $ or
replacing it with the word "USD" - which incidentally solved the $ problem
by removing the character that triggers it, but took bold/italic down with
it for no reason connected to the actual bug.

This version escapes the dollar sign (\\$) instead of removing or replacing
it - the standard fix used elsewhere for this exact Streamlit behavior - and
leaves every other markdown construct untouched. Bold and italic were never
the problem; only the literal $ character is.

This domain (SEC filing answers) never legitimately needs real LaTeX math,
so there is no ambiguous case to resolve here: every $ is currency, always.
"""

import re
import logging

logger = logging.getLogger(__name__)


class ResponseCleaner:
    """
    Escapes the one character that breaks Streamlit rendering ($) and
    leaves every other markdown construct (bold, italic, headers, bullets)
    untouched.
    """

    def __init__(self, log_changes: bool = False):
        self.log_changes = log_changes

    def clean(self, text: str) -> str:
        """
        Escape literal dollar signs so Streamlit's markdown renderer
        cannot interpret them as LaTeX math delimiters.

        Args:
            text: Raw LLM output

        Returns:
            Text safe for st.markdown(), with bold/italic/headers/bullets
            rendering exactly as the model wrote them.
        """
        if not text:
            return text

        original_length = len(text)

        # Escape every literal $ as \$. This is the standard CommonMark
        # escape and is respected by the markdown renderer Streamlit uses -
        # the dollar sign still displays, it just can no longer open a math
        # block. Skip any $ already escaped (idempotent on repeated calls).
        cleaned = re.sub(r'(?<!\\)\$', r'\\$', text)

        if self.log_changes:
            n_escaped = cleaned.count(r'\$') - text.count(r'\$')
            logger.info(
                f"ResponseCleaner: escaped {n_escaped} dollar sign(s), "
                f"{original_length} -> {len(cleaned)} chars"
            )

        return cleaned


def clean_llm_response(text: str, log_changes: bool = False) -> str:
    """Convenience function."""
    cleaner = ResponseCleaner(log_changes=log_changes)
    return cleaner.clean(text)
