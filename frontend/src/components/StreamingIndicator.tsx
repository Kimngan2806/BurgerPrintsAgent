import React from 'react';

export default function StreamingIndicator() {
  return (
    <div className="msg-row agent animate-fade-in">
      <span className="msg-label">Agent</span>
      <div className="msg-bubble agent" style={{ display: 'flex', alignItems: 'center', gap: '0.55rem' }}>
        <span style={{ fontSize: '0.9rem', color: 'var(--text-secondary)' }}>Đang suy nghĩ</span>
        <span className="typing-dots">
          <span></span>
          <span></span>
          <span></span>
        </span>
      </div>
    </div>
  );
}
