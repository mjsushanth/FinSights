"""
Minimal response cleaner - LaTeX prevention only.

Philosophy: Don't fix spacing, just prevent Streamlit from rendering LaTeX/markdown.
"""

import re
import logging

logger = logging.getLogger(__name__)


class ResponseCleaner:
    """
    Line-aware cleaner that prevents LaTeX triggering.
    
    Strategy:
        1. Classify each line (heading, bullet, ordinary)
        2. Remove markdown wrappers ($...$, **bold**, *italic*)
        3. Escape residual triggers (* _ $) on body text
        4. Keep headers and bullets as-is
    
    Does NOT:
        - Fix spacing issues (billionin2016 stays as-is)
        - Remove headers or structure
        - Try to be smart about patterns
    """
    
    def __init__(self, log_changes: bool = False):
        self.log_changes = log_changes
        self._changes_made = []
    
    def clean(self, text: str) -> str:
        """
        Clean LLM response line-by-line.
        
        Args:
            text: Raw LLM output
            
        Returns:
            Cleaned text safe for st.markdown()
        """
        if not text:
            return text
        
        self._changes_made = []
        
        # Process line-by-line
        cleaned_lines = []
        for line in text.split('\n'):
            cleaned_line = self._clean_line(line)
            cleaned_lines.append(cleaned_line)
        
        result = '\n'.join(cleaned_lines)
        
        if self.log_changes:
            logger.info(
                f"ResponseCleaner: {len(self._changes_made)} operations, "
                f"{len(text)} → {len(result)} chars"
            )
        
        return result
    
    def _clean_line(self, line: str) -> str:
        """
        Clean a single line based on its type.
        
        Line types:
            1. Heading (starts with #) → Keep untouched
            2. Bullet/List (starts with -, *, +, 1.) → Preserve prefix, clean body
            3. Ordinary → Remove wrappers, escape triggers
        """
        stripped = line.lstrip()
        
        # ================================================================
        # Type 1: Heading - PRESERVE COMPLETELY
        # ================================================================
        if stripped.startswith('#'):
            return line
        
        # ================================================================
        # Type 2: Bullet/List - PRESERVE PREFIX, CLEAN BODY
        # ================================================================
        # Patterns: "- item", "  * item", "1. item", "  + item"
        bullet_match = re.match(r'^(\s*)([-*+]|\d+\.)\s+(.*)$', line)
        if bullet_match:
            indent = bullet_match.group(1)
            prefix = bullet_match.group(2)
            body = bullet_match.group(3)
            
            # Clean the body part only
            body = self._strip_wrappers(body)
            body = self._escape_triggers(body)
            
            return f"{indent}{prefix} {body}"
        
        # ================================================================
        # Type 3: Ordinary Line - FULL CLEANING
        # ================================================================
        line = self._strip_wrappers(line)
        line = self._escape_triggers(line)
        
        return line
    
    def _strip_wrappers(self, text: str) -> str:
        """
        Remove markdown wrappers (** __ * _ ~~ $...$).
        
        This is simple unwrapping - no complex pattern matching.
        """
        # Remove LaTeX: $content$ → content
        text = re.sub(r'\$([^\$]+)\$', r'\1', text)
        
        # Remove bold: **text** and __text__
        text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
        text = re.sub(r'__(.+?)__', r'\1', text)
        
        # Remove italic: *text* and _text_
        text = re.sub(r'\*(.+?)\*', r'\1', text)
        text = re.sub(r'_(.+?)_', r'\1', text)
        
        # Remove strikethrough: ~~text~~
        text = re.sub(r'~~(.+?)~~', r'\1', text)
        
        return text
    
    def _escape_triggers(self, text: str) -> str:
        """
        Escape markdown/LaTeX triggers so Streamlit can't interpret them.
        
        Escapes:
            $ → \$
            * → \* (if not already escaped)
            _ → \_ (if not already escaped)
        """
        # Escape dollar signs (LaTeX trigger)
        text = text.replace('$', r'\$')
        
        # Escape asterisks (italic/bold trigger)
        # Only if not already escaped
        text = re.sub(r'(?<!\\)\*', r'\*', text)
        
        # Escape underscores (italic/bold trigger)
        text = re.sub(r'(?<!\\)_', r'\_', text)
        
        return text


def clean_llm_response(text: str, log_changes: bool = False) -> str:
    """Convenience function."""
    cleaner = ResponseCleaner(log_changes=log_changes)
    return cleaner.clean(text)
