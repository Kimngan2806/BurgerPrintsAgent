import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface MessageBubbleProps {
  role: 'user' | 'agent';
  content: string;
}

export default function MessageBubble({ role, content }: MessageBubbleProps) {
  const isUser = role === 'user';

  return (
    <div className={`msg-row ${isUser ? 'user' : 'agent'} animate-fade-in`}>
      <span className="msg-label">{isUser ? 'You' : 'Agent'}</span>

      <div className={`msg-bubble ${isUser ? 'user' : 'agent'}`}>
        <div className="markdown-body">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              table: ({node, ...props}) => <div className="table-wrap"><table {...props} /></div>,
            }}
          >
            {content}
          </ReactMarkdown>
        </div>
      </div>
    </div>
  );
}
