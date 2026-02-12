import { useState, useRef, useEffect } from 'react';
import { api } from '../lib/api';
import {
  RobotIcon,
  HistoryIcon,
  PlusIcon,
  SendIcon,
  ChevronRightIcon,
  UserIcon
} from '../components/icons';

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
    <div className="flex flex-col h-full min-h-[calc(100vh-120px)]">
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b-3 border-[var(--border-color)] bg-[var(--bg-card)]">
        <h2 className="font-heading text-lg font-bold">Network Agent</h2>
        <div className="flex items-center gap-2">
          <button
            className="btn-neo p-2"
            onClick={() => setShowSessions(!showSessions)}
            title="History"
            aria-label="View chat history"
          >
            <HistoryIcon size={20} />
          </button>
          <button
            className="btn-neo p-2"
            onClick={startNewChat}
            title="New chat"
            aria-label="Start new chat"
          >
            <PlusIcon size={20} />
          </button>
        </div>
      </div>

      {/* Sessions Dropdown */}
      {showSessions && (
        <div className="absolute top-16 right-4 left-4 z-50 card-neo max-h-64 overflow-y-auto animate-neo-slide-up">
          <div className="p-2">
            {sessions.length === 0 ? (
              <div className="text-center py-4 text-[var(--text-muted)]">
                No previous chats
              </div>
            ) : (
              <div className="flex flex-col gap-2">
                {sessions.map(s => (
                  <button
                    key={s.session_id}
                    className={`flex items-center justify-between p-3 text-left border-2 border-[var(--border-color)] transition-all ${
                      sessionId === s.session_id
                        ? 'bg-[var(--accent-primary)] text-white shadow-[1px_1px_0_var(--shadow-color)]'
                        : 'bg-[var(--bg-card)] hover:bg-[var(--bg-secondary)] hover:shadow-[1px_1px_0_var(--shadow-color)]'
                    }`}
                    onClick={() => loadSession(s.session_id)}
                  >
                    <div className="flex-1 min-w-0">
                      <span className="block font-medium truncate">{s.title}</span>
                      <span className={`text-xs ${sessionId === s.session_id ? 'text-white/70' : 'text-[var(--text-muted)]'}`}>
                        {new Date(s.updated_at).toLocaleDateString()}
                      </span>
                    </div>
                    <ChevronRightIcon size={16} className="flex-shrink-0 ml-2" />
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Messages Area */}
      <div className="flex-1 overflow-y-auto p-4">
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center py-8">
            {/* Welcome Card */}
            <div className="card-neo p-6 max-w-sm w-full">
              <div className="flex justify-center mb-4">
                <div className="p-3 bg-[var(--accent-primary)] border-2 border-[var(--border-color)] shadow-[1px_1px_0_var(--shadow-color)]">
                  <RobotIcon size={32} className="text-white" />
                </div>
              </div>
              <h3 className="font-heading text-xl font-bold mb-2">Ask me about your network</h3>
              <p className="text-[var(--text-secondary)] text-sm mb-6">
                I can help you find people, look up contacts, and remember who you know.
              </p>

              {/* Example Query Chips */}
              <div className="flex flex-col gap-2">
                {exampleQueries.map((q, i) => (
                  <button
                    key={i}
                    className="badge-neo text-left py-2 px-3 text-xs normal-case tracking-normal cursor-pointer hover:translate-x-1 hover:translate-y-1 hover:shadow-[1px_1px_0_var(--shadow-color)] active:translate-x-1 active:translate-y-1 active:shadow-none transition-all"
                    onClick={() => setInput(q)}
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          </div>
        ) : (
          <div className="flex flex-col gap-4">
            {messages.map(msg => (
              <div
                key={msg.id}
                className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                <div
                  className={`max-w-[85%] ${
                    msg.role === 'user'
                      ? 'bg-[var(--accent-primary)] text-white border-2 border-[var(--border-color)] shadow-[1px_1px_0_var(--shadow-color)] p-3'
                      : 'card-neo border-l-[6px] border-l-[var(--accent-primary)]'
                  }`}
                >
                  {msg.role === 'assistant' && (
                    <div className="flex items-center gap-2 mb-2 pb-2 border-b border-[var(--border-color)]/20">
                      <RobotIcon size={16} className="text-[var(--accent-primary)]" />
                      <span className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wide">Assistant</span>
                    </div>
                  )}
                  {msg.role === 'user' && (
                    <div className="flex items-center gap-2 mb-2 pb-2 border-b border-white/20">
                      <UserIcon size={16} />
                      <span className="text-xs font-semibold text-white/70 uppercase tracking-wide">You</span>
                    </div>
                  )}
                  <div className="space-y-2">
                    {msg.content.split('\n').map((line, i) => (
                      <p key={i} className={line ? '' : 'h-2'}>{line}</p>
                    ))}
                  </div>
                </div>
              </div>
            ))}

            {/* Typing Indicator */}
            {loading && (
              <div className="flex justify-start">
                <div className="card-neo border-l-[6px] border-l-[var(--accent-primary)] p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <RobotIcon size={16} className="text-[var(--accent-primary)]" />
                    <span className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wide">Thinking</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <span className="w-2.5 h-2.5 bg-[var(--accent-primary)] rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                    <span className="w-2.5 h-2.5 bg-[var(--accent-primary)] rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                    <span className="w-2.5 h-2.5 bg-[var(--accent-primary)] rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                  </div>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      {/* Input Area */}
      <div className="p-4 border-t-3 border-[var(--border-color)] bg-[var(--bg-card)]">
        <div className="flex items-end gap-3">
          <textarea
            className="input-neo flex-1 resize-none min-h-[48px] max-h-32"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about your network..."
            rows={1}
            disabled={loading}
          />
          <button
            className={`btn-neo btn-neo-primary p-3 rounded-full flex-shrink-0 ${
              !input.trim() || loading ? 'opacity-50 cursor-not-allowed' : ''
            }`}
            onClick={sendMessage}
            disabled={!input.trim() || loading}
            aria-label="Send message"
          >
            <SendIcon size={20} />
          </button>
        </div>
      </div>
    </div>
  );
}
