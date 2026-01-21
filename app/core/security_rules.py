
# Security Configuration

# SQL Injection / Destructive Query Prevention
FORBIDDEN_SQL_KEYWORDS = [
    "insert", 
    "update", 
    "delete", 
    "drop", 
    "alter", 
    "truncate", 
    "grant", 
    "revoke", 
    "into outfile", 
    "sleep", 
    "benchmark"
]

# PII Redaction Patterns (Regex)
PII_PATTERNS = {
    "email": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
    # "phone": r"..." 
}

# Jailbreak / Harmful Prompt Detection
BLOCKED_PROMPTS = [
    "ignore all instructions", 
    "system prompt", 
    "delete database", 
    "drop table"
]
