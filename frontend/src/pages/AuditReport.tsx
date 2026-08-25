import { useEffect, useState } from 'react'
import apiClient from '../services/api'
import { Bot, AlertTriangle, XCircle, ArrowRightLeft, Ghost, Download, RefreshCw, Database } from 'lucide-react'
import jsPDF from 'jspdf'
import autoTable from 'jspdf-autotable'
import { toast } from '../components/Toast'

const STATUS_ICON: Record<string, React.ElementType> = {
  AMOUNT_MISMATCH: AlertTriangle,
  STATUS_MISMATCH: ArrowRightLeft,
  MISSING: XCircle,
  PHANTOM: Ghost,
}

const STATUS_STYLE: Record<string, string> = {
  AMOUNT_MISMATCH: 'border-l-amber-400 bg-amber-50/20',
  STATUS_MISMATCH: 'border-l-orange-400 bg-orange-50/20',
  MISSING: 'border-l-red-400 bg-red-50/20',
  PHANTOM: 'border-l-violet-400 bg-violet-50/20',
}

const STATUS_ICON_COLOR: Record<string, string> = {
  AMOUNT_MISMATCH: 'text-amber-500',
  STATUS_MISMATCH: 'text-orange-500',
  MISSING: 'text-red-500',
  PHANTOM: 'text-violet-500',
}

interface Anomaly {
  txn_id: string
  validation_status: string
  currency: string
  region: string
  channel: string
  legacy_amount: number | null
  new_system_amount: number | null
  amount_diff_pct: number | null
  legacy_status: string | null
  new_system_status: string | null
  ai_explanation: string | null
}

function fmt(n: number | null) {
  if (n === null || n === undefined) return '—'
  return Number(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function SkeletonCard() {
  return (
    <div className="bg-white border border-slate-200 border-l-4 border-l-slate-200 rounded-lg p-5 animate-pulse space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-2.5">
          <div className="w-4 h-4 bg-slate-100 rounded" />
          <div className="h-4 w-32 bg-slate-100 rounded" />
          <div className="h-5 w-20 bg-slate-50/80 rounded" />
        </div>
        <div className="flex gap-3">
          <div className="h-3.5 w-12 bg-slate-100 rounded" />
          <div className="h-3.5 w-12 bg-slate-100 rounded" />
        </div>
      </div>
      <div className="flex gap-6 pt-1">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="space-y-1.5">
            <div className="h-2 w-16 bg-slate-50 rounded" />
            <div className="h-4.5 w-14 bg-slate-100 rounded" />
          </div>
        ))}
      </div>
      <div className="mt-4 pt-4 border-t border-slate-100/80">
        <div className="h-3 w-28 bg-slate-100 rounded mb-2" />
        <div className="h-3.5 w-full bg-slate-50 rounded" />
        <div className="h-3.5 w-2/3 bg-slate-50 rounded mt-1.5" />
      </div>
    </div>
  )
}

export default function AuditReport() {
  const [anomalies, setAnomalies] = useState<Anomaly[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('ALL')

  const fetchData = (silent = false, force = false) => {
    if (!silent) setLoading(true)
    const suffix = force ? '?refresh=true' : ''
    apiClient.get(`/api/anomalies${suffix}`)
      .then(r => {
        setAnomalies(r.data)
        if (silent) toast('Anomaly logs synchronized ✓', 'success')
      })
      .finally(() => { if (!silent) setLoading(false) })
  }

  useEffect(() => { fetchData() }, [])

  const statuses = ['ALL', ...Array.from(new Set(anomalies.map(a => a.validation_status)))]
  const visible = filter === 'ALL' ? anomalies : anomalies.filter(a => a.validation_status === filter)

  const exportPDF = () => {
    const doc = new jsPDF({ orientation: 'landscape' })

    doc.setFontSize(18)
    doc.setTextColor(15, 23, 42)
    doc.text('Validata — AI Audit Report', 14, 18)

    doc.setFontSize(10)
    doc.setTextColor(100, 116, 139)
    doc.text(`Generated: ${new Date().toLocaleString()} · ${visible.length} anomalies`, 14, 26)
    doc.text(`Filter: ${filter}`, 14, 32)

    autoTable(doc, {
      startY: 38,
      head: [['TXN ID', 'Status', 'Region', 'Channel', 'Currency', 'Legacy Amt', 'New Amt', 'Diff %', 'Leg Status', 'New Status', 'AI Root Cause']],
      body: visible.map(a => [
        a.txn_id,
        a.validation_status.replace(/_/g, ' '),
        a.region,
        a.channel,
        a.currency,
        fmt(a.legacy_amount),
        fmt(a.new_system_amount),
        a.amount_diff_pct !== null ? `${Number(a.amount_diff_pct).toFixed(2)}%` : '—',
        a.legacy_status || '—',
        a.new_system_status || '—',
        a.ai_explanation && a.ai_explanation !== 'Explanation unavailable.'
          ? a.ai_explanation.slice(0, 120) + (a.ai_explanation.length > 120 ? '…' : '')
          : 'No AI explanation',
      ]),
      styles: { fontSize: 7, cellPadding: 3, textColor: [51, 65, 85] },
      headStyles: { fillColor: [15, 23, 42], textColor: 255, fontStyle: 'bold', fontSize: 8 },
      alternateRowStyles: { fillColor: [248, 250, 252] },
      columnStyles: { 10: { cellWidth: 60 } },
    })

    const pageCount = (doc as jsPDF & { internal: { getNumberOfPages: () => number } }).internal.getNumberOfPages()
    for (let i = 1; i <= pageCount; i++) {
      doc.setPage(i)
      doc.setFontSize(8)
      doc.setTextColor(148, 163, 184)
      doc.text(`Validata Audit Report — Page ${i} of ${pageCount}`, 14, doc.internal.pageSize.height - 8)
    }

    doc.save(`validata_audit_${new Date().toISOString().split('T')[0]}.pdf`)
    toast(`PDF exported · ${visible.length} anomalies ✓`, 'success')
  }

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-8 bg-slate-50 min-h-screen">
      {/* Standard Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-200/60 pb-6">
        <div>
          <div className="flex items-center gap-2">
            <span className="flex h-2.5 w-2.5 relative">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-blue-500"></span>
            </span>
            <h1 className="text-slate-800 text-2xl font-bold tracking-tight">AI Audit Report</h1>
          </div>
          <p className="text-slate-400 text-sm mt-1 font-medium">
            Anomalous validation summaries · Gemini GenAI Assisted
          </p>
        </div>

        <div className="flex items-center gap-2">
          {/* Connection Status Badge */}
          <div className="flex items-center gap-1.5 px-3 py-1.5 bg-white border border-slate-200 rounded-md text-[11px] font-semibold text-slate-500">
            <Database size={12} className="text-blue-500" />
            <span>ue74066.snowflake</span>
          </div>

          <button
            id="audit-refresh"
            onClick={() => fetchData(true, true)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-md border border-slate-200 bg-white text-slate-600 hover:bg-slate-50 transition-all"
          >
            <RefreshCw size={12} /> Sync
          </button>
          <button
            id="export-pdf"
            onClick={exportPDF}
            disabled={loading || visible.length === 0}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-md border border-slate-200 bg-white text-slate-600 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed transition-all"
          >
            <Download size={12} /> Export PDF
          </button>
        </div>
      </div>

      {/* Filter Tabs Box */}
      <div className="flex items-center justify-between gap-4 flex-wrap bg-white border border-slate-200/80 p-4 rounded-lg shadow-sm">
        <div className="flex gap-1 flex-wrap">
          {loading ? (
            Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="h-8 w-24 bg-slate-100 rounded-md animate-pulse" />
            ))
          ) : (
            statuses.map(s => (
              <button
                key={s}
                id={`audit-filter-${s.toLowerCase()}`}
                onClick={() => setFilter(s)}
                className={`px-3 py-1.5 text-xs font-semibold rounded-md border transition-all ${
                  filter === s
                    ? 'bg-blue-50 text-blue-600 border-blue-200 shadow-sm shadow-blue-500/5'
                    : 'bg-white text-slate-500 border-slate-200 hover:bg-slate-50 hover:text-slate-700'
                }`}
              >
                {s === 'ALL'
                  ? `All anomalies (${anomalies.length})`
                  : `${s.replace(/_/g, ' ')} (${anomalies.filter(a => a.validation_status === s).length})`}
              </button>
            ))
          )}
        </div>
        {!loading && (
          <span className="text-xs text-slate-400 font-semibold font-mono">
            showing {visible.length} entries
          </span>
        )}
      </div>

      {/* Cards List */}
      <div className="space-y-4">
        {loading ? (
          Array.from({ length: 3 }).map((_, i) => <SkeletonCard key={i} />)
        ) : visible.length === 0 ? (
          <div className="bg-white border border-slate-200 rounded-lg p-10 text-center">
            <p className="text-slate-400 text-sm">No validation anomalies detected in selection parameters.</p>
          </div>
        ) : (
          visible.map(a => {
            const Icon = STATUS_ICON[a.validation_status] || AlertTriangle
            const hasExplanation = a.ai_explanation && a.ai_explanation !== 'Explanation unavailable.'
            return (
              <div
                key={a.txn_id}
                className={`bg-white border border-slate-200 border-l-4 rounded-lg p-5 hover:shadow-md hover:border-slate-300 transition-all duration-200 ${STATUS_STYLE[a.validation_status] || ''}`}
              >
                {/* Header info */}
                <div className="flex items-start justify-between gap-4">
                  <div className="flex items-center gap-2.5">
                    <Icon size={15} className={STATUS_ICON_COLOR[a.validation_status]} />
                    <span className="font-mono text-xs font-bold text-slate-700">{a.txn_id}</span>
                    <span className="text-[10px] text-slate-500 font-bold uppercase tracking-wide px-2 py-0.5 bg-white border border-slate-100 rounded">
                      {a.validation_status.replace(/_/g, ' ')}
                    </span>
                  </div>
                  <div className="flex items-center gap-4 text-xs font-semibold text-slate-400 shrink-0">
                    <span>{a.region}</span>
                    <span className="h-3 w-px bg-slate-200"></span>
                    <span>{a.channel}</span>
                    <span className="h-3 w-px bg-slate-200"></span>
                    <span className="text-slate-500 font-bold">{a.currency}</span>
                  </div>
                </div>

                {/* Amount grid */}
                <div className="mt-4 grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-5 gap-y-3 gap-x-4 text-xs border-b border-slate-200/40 pb-4">
                  <div>
                    <p className="text-[9px] text-slate-400 font-semibold uppercase tracking-wider">Legacy Amount</p>
                    <p className="text-slate-700 font-bold mt-0.5">{fmt(a.legacy_amount)}</p>
                  </div>
                  <div>
                    <p className="text-[9px] text-slate-400 font-semibold uppercase tracking-wider">New System Amount</p>
                    <p className="text-slate-700 font-bold mt-0.5">{fmt(a.new_system_amount)}</p>
                  </div>
                  {a.amount_diff_pct !== null && (
                    <div>
                      <p className="text-[9px] text-slate-400 font-semibold uppercase tracking-wider">Difference %</p>
                      <p className={`font-bold mt-0.5 ${Math.abs(Number(a.amount_diff_pct)) > 1 ? 'text-red-600' : 'text-amber-600'}`}>
                        {Number(a.amount_diff_pct).toFixed(2)}%
                      </p>
                    </div>
                  )}
                  {a.legacy_status && (
                    <div>
                      <p className="text-[9px] text-slate-400 font-semibold uppercase tracking-wider">Legacy Status</p>
                      <p className="text-slate-500 font-semibold mt-0.5">{a.legacy_status}</p>
                    </div>
                  )}
                  {a.new_system_status && (
                    <div>
                      <p className="text-[9px] text-slate-400 font-semibold uppercase tracking-wider">New Status</p>
                      <p className="text-slate-500 font-semibold mt-0.5">{a.new_system_status}</p>
                    </div>
                  )}
                </div>

                {/* AI Explanation details */}
                <div className="mt-4">
                  <div className="flex items-center gap-1.5 mb-1.5">
                    <Bot size={14} className="text-blue-500" />
                    <span className="text-[9px] font-bold text-slate-400 uppercase tracking-wider">AI Root Cause Analysis</span>
                  </div>
                  {hasExplanation ? (
                    <p className="text-slate-600 text-xs leading-relaxed font-medium">{a.ai_explanation}</p>
                  ) : (
                    <p className="text-slate-400 text-xs italic font-medium">AI explanation not yet generated (daily quota reached).</p>
                  )}
                </div>
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}
