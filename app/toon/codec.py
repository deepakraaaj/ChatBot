
import json
import uuid
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

from datetime import date, datetime

def json_serial(obj):
    """JSON serializer for objects not serializable by default json code"""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, bytes):
        return str(obj) # Or obj.decode('utf-8', errors='ignore')
    raise TypeError (f"Type {type(obj)} not serializable")

class ToonCodec:
    """
    Token-Oriented Object Notation (TOON) Codec.
    
    Real Implementation:
    1. Normalizes data (handles datetime, bytes).
    2. Scans for all strings (keys and values).
    3. Builds a lookup table (dictionary) of unique strings.
    4. Replaces actual strings with their lookup table index (formatted as reference tag).
    5. Calculates true 'compressed' size vs raw JSON size.
    """
    def __init__(self):
        self.lookup_table = []
        self.reverse_lookup = {}
        self.raw_size = 0
        self.toon_size = 0

    def encode(self, data: Any) -> Dict[str, Any]:
        """
        Encodes data into TOON format by extracting common strings.
        Output format: {"data": <structure_with_refs>, "lookup": [<strings>]}
        """
        # 1. Normalize data first (handle dates, bytes, etc.)
        # We dump and load to ensure we are working with standard JSON primitives
        json_str = json.dumps(data, default=json_serial)
        normalized_data = json.loads(json_str)
        
        self.raw_size = len(json_str)

        # 2. Reset state for this encoding pass
        self.lookup_table = []
        self.reverse_lookup = {}

        # 3. Perform compression (extract strings)
        encoded_data = self._compress_recursive(normalized_data)

        # 4. Construct the TOON payload
        toon_payload = {
            "lookup": self.lookup_table,
            "data": encoded_data
        }
        
        # 5. Measure compressed size
        toon_str = json.dumps(toon_payload)
        self.toon_size = len(toon_str)

        # Avoid division by zero
        reduction_pct = 0.0
        if self.raw_size > 0:
            reduction_pct = ((self.raw_size - self.toon_size) / self.raw_size) * 100.0

        return {
            "data": toon_payload, # The actual compressed structure
            "toon_meta": {
                "raw_tokens": self.raw_size,
                "toon_tokens": self.toon_size,
                "reduction_pct": round(reduction_pct, 2)
            }
        }

    def decode(self, toon_outer: Dict[str, Any]) -> Any:
        """
        Decodes a TOON payload back to the original object.
        toon_outer should be the object containing {"lookup": [...], "data": ...}
        """
        # Support both wrapped and direct payload formats depending on how it's passed
        payload = toon_outer.get("data", toon_outer)
        
        lookup = payload.get("lookup", [])
        data = payload.get("data")
        
        return self._decompress_recursive(data, lookup)

    def _compress_recursive(self, node: Any) -> Any:
        if isinstance(node, dict):
            # Keys must be strings in JSON, so we get ref for key too
            return {
                self._get_ref(k): self._compress_recursive(v) 
                for k, v in node.items()
            }
        elif isinstance(node, list):
            return [self._compress_recursive(item) for item in node]
        elif isinstance(node, str):
            return self._get_ref(node)
        else:
            # maintain ints, floats, bools, None as is
            return node

    def _get_ref(self, value: str) -> str:
        """Get 'tag + index' string for a string value."""
        # Compression Strategy:
        # Use a tilde '~' to indicate a reference index. e.g. "~12"
        # If the original string starts with '~', escape it as '~~'.
        
        if value.startswith("~"):
             # It's an escape case, store it literally but escaped, don't look it up?
             # OR treat it as just another string in the table. 
             # Simpler: Treat EVERYTHING as a string to be looked up.
             # But then the lookup table itself has strings.
             # 
             # Wait, the lookup table holds the RAW strings.
             # The structure holds references.
             # So if the original string is "~foo", we put "~foo" in lookup table at idx 5.
             # We return "~5".
             # Decoder sees "~5", looks up index 5, gets "~foo". Correct.
             # 
             # WHAT IF legitimate string is "123"? lookup index 0 -> "123". Ref: "~0".
             # Decoder sees "~0", gets "123". Correct.
             pass

        if value not in self.reverse_lookup:
            idx = len(self.lookup_table)
            self.lookup_table.append(value)
            self.reverse_lookup[value] = idx
        
        return f"~{self.reverse_lookup[value]}"

    def _decompress_recursive(self, node: Any, lookup: list) -> Any:
        if isinstance(node, dict):
            decoded_dict = {}
            for k, v in node.items():
                # Resolve key
                key_str = self._resolve_ref(k, lookup)
                decoded_dict[key_str] = self._decompress_recursive(v, lookup)
            return decoded_dict
            
        elif isinstance(node, list):
            return [self._decompress_recursive(item, lookup) for item in node]
            
        elif isinstance(node, str):
             return self._resolve_ref(node, lookup)
             
        return node

    def _resolve_ref(self, val: str, lookup: list) -> str:
        # Check if it matches reference pattern ~<int>
        if val.startswith("~"):
            # Check if it is an escaped tilde "~~" (not implemented in encode above, but good for robust logic)
            # Actually, my encode logic above ALWAYS encodes strings into refs. 
            # So ANY string found in the structure MUST be a reference.
            # There represent NO raw strings in the compressed structure's values, ONLY references.
            # The only raw strings are in the lookup table.
            try:
                idx = int(val[1:])
                if 0 <= idx < len(lookup):
                    return lookup[idx]
            except ValueError:
                pass
        return val

toon_codec = ToonCodec()
