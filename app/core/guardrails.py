
import re
from typing import List, Optional, Tuple
from app.core.observability import TraceManager
from app.core.security_rules import PII_PATTERNS, BLOCKED_PROMPTS

class SafetyViolation(Exception):
    pass

class Guardrails:
    """
    Basic guardrails for Chatbot I/O.
    """
    

    @staticmethod
    def validate_input(text: str) -> Tuple[bool, Optional[str]]:
        """
        Check input for malicious content or jailbreaks.
        Returns: (is_safe, violation_reason)
        """
        text_lower = text.lower()
        
        for keyword in BLOCKED_PROMPTS:
            if keyword in text_lower:
                TraceManager.info("Guardrail blocked input", keyword=keyword)
                return False, f"Blocked keyword detected: {keyword}"
                
        return True, None

    @staticmethod
    def sanitize_output(text: str) -> str:
        """
        Redact PII from output before sending to user (if any leaked).
        """
        sanitized = text
        for p_name, pattern in PII_PATTERNS.items():
            # In a real app, use a proper PII scrubber like Microsoft Presidio
            # Here we just simple regex replace
            sanitized = re.sub(pattern, f"[{p_name.upper()}_REDACTED]", sanitized)
            
        if sanitized != text:
            TraceManager.info("Guardrail redacted output", original_length=len(text))
            
        return sanitized

    @staticmethod
    async def guard(func):
        """Decorator for async functions to automatically guard inputs/outputs if they return text? Implemented manually in API for now."""
        pass
