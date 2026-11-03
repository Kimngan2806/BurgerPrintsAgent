'use client';

import React, { useState, useEffect, useRef } from 'react';
import { Send, Menu, Plus, Sun, Moon } from 'lucide-react';
import MessageBubble from '@/components/MessageBubble';
import StreamingIndicator from '@/components/StreamingIndicator';
import { generateSessionId, getApiBaseUrl } from '@/lib/api';

type Message = {
  id: string;
  role: 'user' | 'agent';
  content: string;
};

export default function ChatPage() {
  const [sessionId, setSessionId] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [theme, setTheme] = useState<'light' | 'dark'>('light');

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Init session on first load
    setSessionId(generateSessionId());
    
    // Auto-welcome message
    setMessages([
      {
        id: 'welcome',
        role: 'agent',
        content: '👋 Chào bạn! Tôi là **BurgerPrintsAgent**.\n\nTôi có thể giúp bạn tìm kiếm sản phẩm, so sánh xưởng fulfillment, và tính toán lợi nhuận. Bạn muốn tìm sản phẩm gì hôm nay?'
      }
    ]);
  }, []);

  useEffect(() => {
    // Scroll to bottom when messages change
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, isLoading]);

  useEffect(() => {
    // Khôi phục theme đã lưu (mặc định: light)
    const saved = typeof window !== 'undefined' ? localStorage.getItem('theme') : null;
    const initial = saved === 'dark' ? 'dark' : 'light';
    setTheme(initial);
    document.documentElement.setAttribute('data-theme', initial);
  }, []);

  const toggleTheme = () => {
    setTheme(prev => {
      const next = prev === 'light' ? 'dark' : 'light';
      document.documentElement.setAttribute('data-theme', next);
      try { localStorage.setItem('theme', next); } catch {}
      return next;
    });
  };

  const handleSend = async (text: string = inputValue) => {
    if (!text.trim() || isLoading) return;

    const activeSessionId = sessionId || generateSessionId();
    if (!sessionId) {
      setSessionId(activeSessionId);
    }
    
    const userMsgId = Date.now().toString();
    const agentMsgId = (Date.now() + 1).toString();
    
    // Add user message
    setMessages(prev => [...prev, { id: userMsgId, role: 'user', content: text }]);
    setInputValue('');
    setIsLoading(true);

    try {
      const url = getApiBaseUrl();
      const response = await fetch(`${url}/api/chat/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          message: text,
          session_id: activeSessionId
        }),
      });

      if (!response.ok) {
        let errorMessage = `Server trả lỗi ${response.status}`;
        try {
          // Dùng clone() để tránh lỗi "body stream already read"
          // khi Next.js proxy đã đọc body trước đó
          const cloned = response.clone();
          const errorText = await cloned.text();
          if (errorText) {
            try {
              const errorPayload = JSON.parse(errorText);
              errorMessage = errorPayload.detail || errorPayload.error || errorMessage;
            } catch {
              errorMessage = errorText.slice(0, 200); // Giới hạn độ dài
            }
          }
        } catch {
          // Không đọc được body — dùng status code
        }
        throw new Error(errorMessage);
      }
      
      if (!response.body) {
        throw new Error('No response body');
      }

      // Add empty agent message that we will stream into
      setMessages(prev => [...prev, { id: agentMsgId, role: 'agent', content: '' }]);
      
      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      
      let done = false;
      let streamedContent = '';
      let eventBuffer = '';
      
      while (!done) {
        const { value, done: readerDone } = await reader.read();
        done = readerDone;
        
        if (value) {
          eventBuffer += decoder.decode(value, { stream: true });
          const events = eventBuffer.split(/(?:\r?\n){2}/);
          eventBuffer = events.pop() || '';
          
          for (const event of events) {
            const dataStr = event
              .split('\n')
              .filter(line => line.startsWith('data:'))
              .map(line => line.replace(/^data:\s?/, ''))
              .join('\n')
              .trim();

            if (dataStr) {
              if (dataStr === '[DONE]') {
                done = true;
                break;
              }
              try {
                const data = JSON.parse(dataStr);
                if (data.text) {
                  streamedContent += data.text;
                  setMessages(prev => 
                    prev.map(msg => 
                      msg.id === agentMsgId 
                        ? { ...msg, content: streamedContent }
                        : msg
                    )
                  );
                } else if (data.error) {
                  streamedContent += `\n\n**Lỗi:** ${data.error}`;
                  setMessages(prev => 
                    prev.map(msg => 
                      msg.id === agentMsgId 
                        ? { ...msg, content: streamedContent }
                        : msg
                    )
                  );
                }
              } catch (e) {
                console.error('Invalid SSE payload:', dataStr, e);
              }
            }
          }
        }
      }

      if (!streamedContent) {
        setMessages(prev =>
          prev.map(msg =>
            msg.id === agentMsgId
              ? { ...msg, content: '**Lỗi:** Server kết thúc phản hồi nhưng không gửi nội dung.' }
              : msg
          )
        );
      }
    } catch (error) {
      console.error('Error fetching stream:', error);
      const message = error instanceof Error ? error.message : 'Không rõ nguyên nhân';
      setMessages(prev => [...prev, { 
        id: Date.now().toString(), 
        role: 'agent', 
        content: `**Lỗi:** ${message}` 
      }]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="app-container">
      {/* Sidebar */}
      <div className={`sidebar ${isSidebarOpen ? 'open' : ''}`}>
        <div className="sidebar-header">
          <img className="brand-logo" src="/burgerprint-logo.svg" alt="BurgerPrint" />
        </div>
        
        <button className="new-chat-btn" onClick={() => {
          setSessionId(generateSessionId());
          setMessages([{
            id: 'welcome',
            role: 'agent',
            content: 'Đã tạo phiên chat mới. Bạn cần hỗ trợ gì?'
          }]);
        }}>
          <Plus size={18} />
          <span>New Chat</span>
        </button>

        <div className="sidebar-spacer" />

        <button className="theme-toggle" onClick={toggleTheme}>
          {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
          <span>{theme === 'dark' ? 'Light mode' : 'Dark mode'}</span>
        </button>

      </div>

      {/* Main Chat Area */}
      <div className="main-content">
        {/* Mobile Header */}
        <div className="mobile-header">
          <button className="icon-btn" onClick={() => setIsSidebarOpen(!isSidebarOpen)}>
            <Menu size={24} />
          </button>
          <img className="mobile-brand-logo" src="/burgerprint-logo.svg" alt="BurgerPrint" />
        </div>

        <div className="chat-window" ref={scrollContainerRef}>
          {messages.map(msg => (
            <MessageBubble key={msg.id} role={msg.role} content={msg.content} />
          ))}
          {isLoading && <StreamingIndicator />}
          <div ref={messagesEndRef} />
        </div>

        <div className="input-area">
          <div className="input-container glass">
            <input
              type="text"
              className="chat-input"
              placeholder="Hỏi về sản phẩm, giá, so sánh xưởng..."
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={isLoading}
            />
            <button
              className="send-button"
              onClick={() => handleSend()}
              disabled={!inputValue.trim() || isLoading}
            >
              <Send size={16} />
              <span>Send</span>
            </button>
          </div>
          <div className="input-hint">
            AI Agent có thể mắc lỗi. Vui lòng kiểm tra lại thông tin quan trọng.
          </div>
        </div>
      </div>
    </div>
  );
}
