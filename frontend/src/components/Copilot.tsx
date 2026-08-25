import { useState, useRef, useEffect } from 'react'
import axios from 'axios'
import { Send, X, Bot, Sparkles, RefreshCw } from 'lucide-react'

interface Message {
  role: 'user' | 'assistant'
  content: string
}

export default function Copilot() {
  const [isOpen, setIsOpen] = useState(false)
  const [messages, setMessages] = useState<Message[]>([
    { role: 'assistant', content: 'Hello! I am your Validata AI Copilot. Ask me anything about current anomalies, match rates, or remediation steps.' }
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)

  const quickQuestions = [
    'Summarize current health',
    'Any high risk anomalies?',
    'Remediation for missing txns'
  ]

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages])

  const handleSend = async (textToSend?: string) => {
    const query = (textToSend || input).trim()
    if (!query || loading) return

    if (!textToSend) setInput('')

    const updated = [...messages, { role: 'user', content: query } as Message]
    setMessages(updated)
    setLoading(true)

    try {
      const history = updated.slice(1, -1).map(m => ({
        role: m.role,
        content: m.content
      }))
      const res = await axios.post('/api/chat', { message: query, history })
      setMessages(prev => [...prev, { role: 'assistant', content: res.data.reply }])
    } catch (e) {
      setMessages(prev => [
        ...prev,
        { role: 'assistant', content: 'Sorry, I encountered an error communicating with the validation engine AI.' }
      ])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed bottom-6 right-6 z-50 select-none">
      {/* Floating Toggle Button */}
      {!isOpen && (
        <button
          onClick={() => setIsOpen(true)}
          className="flex items-center justify-center w-12 h-12 rounded-full bg-blue-600 hover:bg-blue-700 text-white shadow-xl hover:shadow-blue-500/20 hover:-translate-y-0.5 active:translate-y-0 transition-all duration-200"
          title="Ask AI Copilot"
        >
          <Bot size={22} className="animate-pulse" />
        </button>
      )}

      {/* Chat Window Panel */}
      {isOpen && (
        <div className="bg-white border border-slate-200/80 rounded-xl shadow-2xl w-80 sm:w-96 h-[460px] flex flex-col overflow-hidden animate-in slide-in-from-bottom-5 duration-200">
          {/* Header */}
          <div className="bg-slate-900 px-4 py-3 flex items-center justify-between border-b border-slate-800">
            <div className="flex items-center gap-2">
              <div className="p-1.5 bg-blue-500/10 rounded-lg border border-blue-500/20">
                <Sparkles size={14} className="text-blue-400" />
              </div>
              <div>
                <p className="text-slate-100 font-bold text-xs leading-none">Validata Copilot</p>
                <div className="flex items-center gap-1 mt-1">
                  <span className="h-1 w-1 rounded-full bg-emerald-500 animate-ping absolute"></span>
                  <span className="relative h-1 w-1 rounded-full bg-emerald-500"></span>
                  <span className="text-[9px] text-slate-500 font-bold uppercase tracking-wider leading-none">GenAI Live</span>
                </div>
              </div>
            </div>
            <button
              onClick={() => setIsOpen(false)}
              className="p-1 rounded hover:bg-slate-800 text-slate-400 hover:text-slate-200 transition-colors"
            >
              <X size={14} />
            </button>
          </div>

          {/* Messages container */}
          <div
            ref={scrollRef}
            className="flex-1 p-4 overflow-y-auto space-y-3.5 bg-slate-50/50 scrollbar-thin scrollbar-thumb-slate-200"
          >
            {messages.map((m, i) => (
              <div
                key={i}
                className={`flex gap-2.5 max-w-[85%] ${m.role === 'user' ? 'ml-auto flex-row-reverse' : 'mr-auto'}`}
              >
                {m.role === 'assistant' && (
                  <div className="w-6 h-6 rounded-full bg-blue-50 border border-blue-100 flex items-center justify-center shrink-0">
                    <Bot size={12} className="text-blue-600" />
                  </div>
                )}
                <div
                  className={`rounded-lg px-3 py-2 text-xs font-semibold leading-relaxed shadow-sm ${
                    m.role === 'user'
                      ? 'bg-blue-600 text-white border border-blue-700/20 rounded-tr-none'
                      : 'bg-white text-slate-600 border border-slate-200/60 rounded-tl-none'
                  }`}
                >
                  {m.content}
                </div>
              </div>
            ))}

            {loading && (
              <div className="flex gap-2.5 max-w-[85%] mr-auto">
                <div className="w-6 h-6 rounded-full bg-blue-50 border border-blue-100 flex items-center justify-center shrink-0">
                  <RefreshCw size={12} className="text-blue-600 animate-spin" />
                </div>
                <div className="rounded-lg px-3 py-2 text-xs font-semibold leading-relaxed bg-white text-slate-400 border border-slate-200/60 rounded-tl-none">
                  Analyzing Snowflake logs...
                </div>
              </div>
            )}
          </div>

          {/* Quick suggestions */}
          <div className="px-3 py-2 bg-white border-t border-slate-100 flex gap-1.5 overflow-x-auto whitespace-nowrap scrollbar-none">
            {quickQuestions.map((q, i) => (
              <button
                key={i}
                onClick={() => handleSend(q)}
                disabled={loading}
                className="px-2 py-1 text-[10px] font-bold text-slate-500 bg-slate-50 hover:bg-slate-100 border border-slate-200 rounded-md transition-all shrink-0 disabled:opacity-40"
              >
                {q}
              </button>
            ))}
          </div>

          {/* Footer Input Form */}
          <form
            onSubmit={e => {
              e.preventDefault()
              handleSend()
            }}
            className="p-3 bg-white border-t border-slate-200/80 flex gap-2"
          >
            <input
              type="text"
              placeholder="Ask Copilot (e.g. Find region errors)…"
              value={input}
              onChange={e => setInput(e.target.value)}
              disabled={loading}
              className="flex-1 px-3 py-1.5 text-xs border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-slate-50/50 text-slate-700 placeholder-slate-400 disabled:opacity-50"
            />
            <button
              type="submit"
              disabled={loading || !input.trim()}
              className="flex items-center justify-center p-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white disabled:opacity-40 disabled:hover:bg-blue-650 transition-colors"
            >
              <Send size={13} />
            </button>
          </form>
        </div>
      )}
    </div>
  )
}
