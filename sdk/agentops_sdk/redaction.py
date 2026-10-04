from typing import Any, Dict

def redact_sensitive_data(data: Dict[str, Any], capture_payloads: bool = False) -> Dict[str, Any]:
    """
    Redact sensitive fields from the data dictionary if payload capture is off.
    In the MVP, this mostly ensures raw prompts and responses are not included by default.
    """
    if capture_payloads:
        return data
        
    redacted_data = {}
    sensitive_keys = {"prompt", "response", "input", "output", "messages"}
    
    for key, value in data.items():
        if key.lower() in sensitive_keys:
            redacted_data[key] = "[REDACTED]"
        else:
            redacted_data[key] = value
            
    return redacted_data
