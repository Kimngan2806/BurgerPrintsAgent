import time
from typing import Dict, Any
from core.config import settings

class SessionManager:
    def __init__(self, ttl_minutes: int = 30):
        self.ttl_seconds = ttl_minutes * 60
        self.sessions: Dict[str, Dict[str, Any]] = {}
        
    def get_session(self, session_id: str) -> Dict[str, Any]:
        now = time.time()
        
        # Cleanup old sessions
        self._cleanup(now)
        
        # Create if not exists
        if session_id not in self.sessions:
            self.sessions[session_id] = {
                "chat_session": None, # Sẽ lưu Gemini ChatSession object
                "created_at": now,
                "last_active": now
            }
            
        self.sessions[session_id]["last_active"] = now
        return self.sessions[session_id]

    def set_chat_session(self, session_id: str, chat_session):
        sess = self.get_session(session_id)
        sess["chat_session"] = chat_session

    def _cleanup(self, current_time: float):
        """Xóa các session đã quá TTL để giải phóng RAM"""
        expired = [sid for sid, data in self.sessions.items() 
                  if current_time - data["last_active"] > self.ttl_seconds]
        for sid in expired:
            del self.sessions[sid]

session_manager = SessionManager(ttl_minutes=settings.SESSION_TTL_MINUTES)
