import { useState } from 'react'
import { CheckCircle2, XCircle, Info } from 'lucide-react'

export type ToastType = 'success' | 'error' | 'info'

export interface ToastMessage {
  id: number
  message: string
  type: ToastType
}

let _setToasts: React.Dispatch<React.SetStateAction<ToastMessage[]>> | null = null

export function toast(message: string, type: ToastType = 'success') {
  if (_setToasts) {
    const id = Date.now()
    _setToasts(prev => [...prev, { id, message, type }])
    setTimeout(() => {
      _setToasts!(prev => prev.filter(t => t.id !== id))
    }, 3500)
  }
}

const ICON = { success: CheckCircle2, error: XCircle, info: Info }
const STYLE = {
  success: 'bg-slate-900 border-green-500 text-green-400',
  error: 'bg-slate-900 border-red-500 text-red-400',
  info: 'bg-slate-900 border-indigo-500 text-indigo-400',
}

export function ToastContainer() {
  const [toasts, setToasts] = useState<ToastMessage[]>([])
  _setToasts = setToasts

  return (
    <div className="fixed bottom-5 right-5 z-50 flex flex-col gap-2 pointer-events-none">
      {toasts.map(t => {
        const Icon = ICON[t.type]
        return (
          <div
            key={t.id}
            className={`flex items-center gap-2.5 px-4 py-3 rounded-lg border-l-4 shadow-lg text-sm font-medium text-white animate-slide-in ${STYLE[t.type]}`}
            style={{ animation: 'slideIn 0.2s ease' }}
          >
            <Icon size={15} />
            {t.message}
          </div>
        )
      })}
    </div>
  )
}
