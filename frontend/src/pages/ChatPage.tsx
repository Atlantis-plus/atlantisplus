import { useState, useRef, useEffect } from 'react';
import { api } from '../lib/api';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
}

interface Session {
  session_id: string;
  title: string;
  updated_at: string;
}

export function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [showSessions, setShowSessions] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    loadSessions();
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const loadSessions = async () => {
    try {
      const data = await api.getChatSessions();
      setSessions(data.sessions);
    } catch (err) {
      console.error('Failed to load sessions:', err);
    }
  };

  const loadSession = async (sid: string) => {
    try {
      const data = await api.getChatMessages(sid);
      setMessages(data.messages.map((m: any) => ({
        id: m.message_id,
        role: m.role,
        content: m.content
      })));
      setSessionId(sid);
      setShowSessions(false);
    } catch (err) {
      console.error('Failed to load session:', err);
    }
  };

  const startNewChat = () => {
    setMessages([]);
    setSessionId(null);
    setShowSessions(false);
  };

  const sendMessage = async () => {
    if (!input.trim() || loading) return;

    const userMessage = input.trim();
    setInput('');
    setLoading(true);

    // Add user message immediately
    const userMsg: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: userMessage
    };
    setMessages(prev => [...prev, userMsg]);

    try {
      const response = await api.chat(userMessage, sessionId || undefined);

      // Update session ID if new
      if (!sessionId) {
        setSessionId(response.session_id);
        loadSessions(); // Refresh sessions list
      }

      // Add assistant response
      const assistantMsg: Message = {
        id: Date.now().toString() + '-assistant',
        role: 'assistant',
        content: response.message
      };
      setMessages(prev => [...prev, assistantMsg]);
    } catch (err) {
      console.error('Chat error:', err);
      const errorMsg: Message = {
        id: Date.now().toString() + '-error',
        role: 'assistant',
        content: 'Sorry, something went wrong. Please try again.'
      };
      setMessages(prev => [...prev, errorMsg]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const exampleQueries = [
    "Who can help me with fundraising?",
    "What do I know about my contacts?",
    "Who works in tech?",
  ];

  return (
    <div className="chat-page">
      <div className="chat-header">
        <h2>Network Agent</h2>
        <div className="chat-header-actions">
          <button
            className="btn-icon"
            onClick={() => setShowSessions(!showSessions)}
            title="History"
          >
            <span>📋</span>
          </button>
          <button
            className="btn-icon"
            onClick={startNewChat}
            title="New chat"
          >
            <span>✨</span>
          </button>
        </div>
      </div>

      {showSessions && (
        <div className="sessions-dropdown">
          <div className="sessions-list">
            {sessions.length === 0 ? (
              <div className="sessions-empty">No previous chats</div>
            ) : (
              sessions.map(s => (
                <button
                  key={s.session_id}
                  className={`session-item ${sessionId === s.session_id ? 'active' : ''}`}
                  onClick={() => loadSession(s.session_id)}
                >
                  <span className="session-title">{s.title}</span>
                  <span className="session-date">
                    {new Date(s.updated_at).toLocaleDateString()}
                  </span>
                </button>
              ))
            )}
          </div>
        </div>
      )}

      <div className="chat-messages">
        {messages.length === 0 ? (
          <div className="chat-welcome">
            <div className="welcome-icon">🤖</div>
            <h3>Ask me about your network</h3>
            <p>I can help you find people, look up contacts, and remember who you know.</p>
            <div className="example-queries">
              {exampleQueries.map((q, i) => (
                <button
                  key={i}
                  className="example-query"
                  onClick={() => setInput(q)}
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map(msg => (
            <div key={msg.id} className={`chat-message ${msg.role}`}>
              <div className="message-content">
                {msg.content.split('\n').map((line, i) => (
                  <p key={i}>{line}</p>
                ))}
              </div>
            </div>
          ))
        )}
        {loading && (
          <div className="chat-message assistant">
            <div className="message-content typing">
              <span className="dot"></span>
              <span className="dot"></span>
              <span className="dot"></span>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <div className="chat-input-container">
        <textarea
          className="chat-input"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask about your network..."
          rows={1}
          disabled={loading}
        />
        <button
          className="chat-send-btn"
          onClick={sendMessage}
          disabled={!input.trim() || loading}
        >
          <span>➤</span>
        </button>
      </div>
    </div>
  );
}
