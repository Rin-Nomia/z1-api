"""
Continuum Logger - GitHub API Version
For cloud environments like Hugging Face Spaces
"""

import json
import os
import base64
from datetime import datetime
from typing import Dict, Any
import requests


class ContinuumLogger:
    """Logger using GitHub API"""
    
    def __init__(self):
        """Initialize Logger"""
        self.github_token = os.environ.get('GITHUB_TOKEN')
        self.github_repo = os.environ.get('GITHUB_REPO')
        
        if not self.github_token or not self.github_repo:
            print("GitHub credentials not set, logging disabled")
            self.enabled = False
        else:
            self.enabled = True
            print(f"Logger enabled, repo: {self.github_repo}")
    
    def log_request(
        self,
        input_text: str,
        mode: str,
        freq_type: str,
        confidence: float,
        scenario: str,
        scenario_confidence: float,
        rhythm: Dict[str, float],
        repair_mode: str,
        repair_method: str,
        repaired_text: str,
        processing_time_ms: float,
        api_calls: int = 1,
        api_cost_usd: float = 0.0
    ) -> str:
        """Log a request"""
        
        if not self.enabled:
            return "logging_disabled"
        
        timestamp = datetime.utcnow().isoformat() + "Z"
        session_id = self._generate_session_id()
        
        log_entry = {
            "timestamp": timestamp,
            "session_id": session_id,
            "input": {
                "text": input_text,
                "text_length": len(input_text),
                "mode": mode
            },
            "detection": {
                "freq_type": freq_type,
                "confidence": confidence,
                "scenario": scenario,
                "scenario_confidence": scenario_confidence,
                "rhythm": rhythm
            },
            "repair": {
                "mode": repair_mode,
                "method": repair_method,
                "repaired_text": repaired_text,
                "text_length": len(repaired_text),
                "length_change": len(repaired_text) - len(input_text)
            },
            "performance": {
                "processing_time_ms": processing_time_ms,
                "api_calls": api_calls,
                "api_cost_usd": api_cost_usd
            },
            "flags": self._generate_flags(
                freq_type, confidence, repair_mode, 
                input_text, repaired_text
            )
        }
        
        try:
            self._write_to_github(log_entry)
        except Exception as e:
            print(f"Failed to write log: {e}")
        
        return session_id
    
    def _generate_session_id(self) -> str:
        """Generate random session ID"""
        import random
        import string
        chars = string.ascii_lowercase + string.digits
        return ''.join(random.choices(chars, k=8))
    
    def _generate_flags(
        self,
        freq_type: str,
        confidence: float,
        repair_mode: str,
        input_text: str,
        repaired_text: str
    ) -> Dict[str, bool]:
        """Generate flags automatically"""
        flags = {
            "unknown_type": freq_type == "Unknown",
            "low_confidence": confidence < 0.4,
            "manual_review_needed": repair_mode == "manual_review",
            "repair_quality_concern": False
        }
        
        if repair_mode == "repair":
            concerns = self._detect_repair_concerns(input_text, repaired_text, confidence)
            flags["repair_quality_concern"] = len(concerns) > 0
        
        return flags
    
    def _detect_repair_concerns(
        self,
        input_text: str,
        repaired_text: str,
        confidence: float
    ) -> list:
        """Detect repair quality issues"""
        concerns = []
        
        input_len = len(input_text)
        repaired_len = len(repaired_text)
        
        if input_len > 0:
            length_change_pct = abs(repaired_len - input_len) / input_len
            if length_change_pct > 0.5:
                concerns.append("length_change_too_large")
        
        if repaired_len > 200:
            concerns.append("repaired_text_too_long")
        
        if confidence < 0.5:
            concerns.append("low_confidence_repair")
        
        warning_words = ["career", "relationship", "family", "health", "money"]
        input_words = set(input_text.lower().split())
        repaired_words = set(repaired_text.lower().split())
        added_words = repaired_words - input_words
        
        if any(word in added_words for word in warning_words):
            concerns.append("added_sensitive_context")
        
        return concerns
    
    def _write_to_github(self, log_entry: Dict[str, Any]):
        """Write log to GitHub via API"""
        
        date_str = datetime.utcnow().strftime("%Y%m%d")
        year_month = datetime.utcnow().strftime("%Y-%m")
        file_path = f"logs/{year_month}/{date_str}.jsonl"
        
        log_line = json.dumps(log_entry, ensure_ascii=False) + '\n'
        
        url = f"https://api.github.com/repos/{self.github_repo}/contents/{file_path}"
        headers = {
            "Authorization": f"token {self.github_token}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        try:
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                file_data = response.json()
                existing_content = base64.b64decode(file_data['content']).decode('utf-8')
                new_content = existing_content + log_line
                sha = file_data['sha']
            else:
                new_content = log_line
                sha = None
            
            encoded_content = base64.b64encode(new_content.encode('utf-8')).decode('utf-8')
            
            data = {
                "message": f"Add log {log_entry['session_id']}",
                "content": encoded_content
            }
            
            if sha:
                data["sha"] = sha
            
            response = requests.put(url, headers=headers, json=data, timeout=10)
            
            if response.status_code in [200, 201]:
                print(f"Log written: {log_entry['session_id']}")
            else:
                print(f"GitHub API error: {response.status_code}")
        
        except Exception as e:
            print(f"Failed to write log: {e}")
