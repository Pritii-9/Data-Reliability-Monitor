import { useEffect, useState, useRef, useCallback } from 'react'
import apiClient from '../services/api'
import { Search, Download, RefreshCw, ChevronUp, ChevronDown, ChevronRight, Database, Calendar } from 'lucide-react'
import { toast } from '../components/Toast'

const STATUSES = ['ALL', 'MATCH', 'AMOUNT_MISMATCH', 'STATUS_MISMATCH', 'MISSING', 'PHANTOM']

const STATUS_BADGE: Record<string, string> = {
  MATCH: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  AMOUNT_MISMATCH: 'bg-amber-50 text-amber-700 border-amber-200',
  STATUS_MISMATCH: 'bg-orange-50 text-orange-700 border-orange-200',
  MISSING: 'bg-red-50 text-red-700 border-red-200',
  PHANTOM: 'bg-violet-50 text-violet-700 border-violet-200',
}

interface Row {
  txn_id: string
  validation_status: string
  customer_id: string
  currency: string
  region: string
  channel: string
  legacy_amount: number | null
  new_system_amount: number | null
  amount_diff_pct: number | null
  legacy_status: string | null
  new_system_status: string | null
  txn_date: string
}

type SortKey = keyof Row
type SortDir = 'asc' | 'desc'

function fmt(n: number | null) {
  if (n === null || n === undefined) return '—'
  return Number(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const PAGE_SIZE_OPTIONS = [10, 30, 50]

function SkeletonRow() {
  return (
    <tr className="animate-pulse">
      <td className="px-3 py-3.5"><div className="h-3 bg-slate-100 rounded w-4" /></td>
      {Array.from({ length: 11 }).map((_, i) => (
        <td key={i} className="px-4 py-3.5">
          <div className="h-3 bg-slate-100 rounded w-full" />
        </td>
      ))}
    </tr>
  )
}

function SortIcon({ col, sortKey, sortDir }: { col: SortKey; sortKey: SortKey | null; sortDir: SortDir }) {
  if (sortKey !== col) return <ChevronUp size={12} className="opacity-20" />
  return sortDir === 'asc' ? <ChevronUp size={12} className="text-indigo-500" /> : <ChevronDown size={12} className="text-indigo-500" />
}

function DetailRow({ row }: { row: Row }) {
  return (
    <tr className="bg-slate-50/50 border-b border-slate-100">
      <td colSpan={12} className="px-8 py-5">
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-x-6 gap-y-4 text-xs">
          {[
            { label: 'Transaction ID', value: row.txn_id, mono: true },
            { label: 'Customer ID', value: row.customer_id || '—' },
            { label: 'Currency', value: row.currency },
            { label: 'Region', value: row.region },
            { label: 'Channel', value: row.channel },
            { label: 'Validation Status', value: row.validation_status.replace(/_/g, ' ') },
            { label: 'Legacy Amount', value: fmt(row.legacy_amount), font: 'font-semibold text-slate-700' },
            { label: 'New System Amount', value: fmt(row.new_system_amount), font: 'font-semibold text-slate-700' },
            { label: 'Difference %', value: row.amount_diff_pct !== null ? `${Number(row.amount_diff_pct).toFixed(2)}%` : '—', font: row.amount_diff_pct && Math.abs(row.amount_diff_pct) > 1 ? 'font-bold text-red-600' : 'font-medium text-slate-500' },
            { label: 'Legacy Status', value: row.legacy_status || '—' },
            { label: 'New System Status', value: row.new_system_status || '—' },
          ].map(({ label, value, mono, font }) => (
            <div key={label} className="space-y-1">
              <p className="text-slate-400 font-semibold uppercase tracking-wider text-[9px]">{label}</p>
              <p className={`text-slate-600 ${mono ? 'font-mono text-[11px]' : ''} ${font || ''}`}>{value}</p>
            </div>
          ))}
        </div>
      </td>
    </tr>
  )
}

export default function Results() {
  const [status, setStatus] = useState('ALL')
  const [selectedMonth, setSelectedMonth] = useState('ALL')
  const [search, setSearch] = useState('')
  const [data, setData] = useState<Row[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(0)
  const [pageSize, setPageSize] = useState(10)
  const [sortKey, setSortKey] = useState<SortKey | null>(null)
  const [sortDir, setSortDir] = useState<SortDir>('asc')
  const [expandedRow, setExpandedRow] = useState<string | null>(null)
  const [dropdownOpen, setDropdownOpen] = useState(false)
  const searchRef = useRef<HTMLInputElement>(null)
  const dropdownRef = useRef<HTMLDivElement>(null)

  // Click outside to close custom dropdown
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setDropdownOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const fetchData = useCallback((silent = false, force = false) => {
    if (!silent) setLoading(true)
    setPage(0)
    apiClient.get('/api/results', {
      params: {
        status: status === 'ALL' ? undefined : status,
        limit: 1000,
        offset: 0,
        refresh: force ? true : undefined
      }
    })
      .then(r => {
        setData(r.data.data)
        setTotal(r.data.total)
        if (silent) toast('Results data synchronized ✓', 'success')
      })
      .finally(() => { if (!silent) setLoading(false) })
  }, [status])

  useEffect(() => { fetchData() }, [fetchData])
  useEffect(() => { setPage(0) }, [search, selectedMonth, pageSize, sortKey, sortDir])

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName
      if (e.key === '/' && !['INPUT', 'TEXTAREA'].includes(tag)) {
        e.preventDefault()
        searchRef.current?.focus()
      }
      if (e.key === 'r' && !['INPUT', 'TEXTAREA'].includes(tag)) {
        fetchData(true)
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [fetchData])

  const handleSort = (key: SortKey) => {
    if (sortKey === key) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortKey(key); setSortDir('asc') }
  }

  const filtered = data.filter(r => {
    const matchesSearch = !search || r.txn_id.toLowerCase().includes(search.toLowerCase()) ||
      (r.customer_id || '').toLowerCase().includes(search.toLowerCase())
    const matchesMonth = selectedMonth === 'ALL' || (r.txn_date && r.txn_date.startsWith(selectedMonth))
    return matchesSearch && matchesMonth
  })

  // Get unique months present in data
  const months = Array.from(new Set(data.map(r => r.txn_date ? r.txn_date.substring(0, 7) : ''))).filter(Boolean).sort()

  // Group months by year
  const groupedMonths = months.reduce((acc, m) => {
    const [year, month] = m.split('-')
    const date = new Date(parseInt(year), parseInt(month) - 1, 1)
    const monthName = date.toLocaleDateString('en-US', { month: 'long' })
    if (!acc[year]) acc[year] = []
    acc[year].push({ value: m, label: monthName })
    return acc
  }, {} as Record<string, { value: string; label: string }[]>)

  const sorted = sortKey
    ? [...filtered].sort((a, b) => {
        const av = a[sortKey] ?? ''
        const bv = b[sortKey] ?? ''
        if (typeof av === 'number' && typeof bv === 'number') return sortDir === 'asc' ? av - bv : bv - av
        return sortDir === 'asc' ? String(av).localeCompare(String(bv)) : String(bv).localeCompare(String(av))
      })
    : filtered

  const totalPages = Math.max(1, Math.ceil(sorted.length / pageSize))
  const paginated = sorted.slice(page * pageSize, page * pageSize + pageSize)

  const exportCSV = () => {
    const headers = ['TXN ID', 'Status', 'Date', 'Customer', 'Currency', 'Region', 'Channel', 'Legacy Amt', 'New Amt', 'Diff %', 'Legacy Status', 'New Status']
    const rows = sorted.map(r => [
      r.txn_id, r.validation_status, r.txn_date || '', r.customer_id || '', r.currency, r.region, r.channel,
      r.legacy_amount ?? '', r.new_system_amount ?? '',
      r.amount_diff_pct !== null ? Number(r.amount_diff_pct).toFixed(2) : '',
      r.legacy_status || '', r.new_system_status || ''
    ])
    const csv = [headers, ...rows].map(r => r.map(v => `"${v}"`).join(',')).join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `validata_results_${new Date().toISOString().split('T')[0]}.csv`
    a.click()
    URL.revokeObjectURL(url)
    toast(`Exported ${sorted.length} records as CSV ✓`, 'success')
  }

  const visiblePages = () => {
    const pages: (number | '…')[] = []
    if (totalPages <= 7) {
      for (let i = 0; i < totalPages; i++) pages.push(i)
    } else {
      pages.push(0)
      if (page > 2) pages.push('…')
      for (let i = Math.max(1, page - 1); i <= Math.min(totalPages - 2, page + 1); i++) pages.push(i)
      if (page < totalPages - 3) pages.push('…')
      pages.push(totalPages - 1)
    }
    return pages
  }

  const COLUMNS: { label: string; key: SortKey; sortable?: boolean }[] = [
    { label: 'TXN ID', key: 'txn_id', sortable: true },
    { label: 'Status', key: 'validation_status', sortable: true },
    { label: 'Date', key: 'txn_date', sortable: true },
    { label: 'Customer', key: 'customer_id', sortable: true },
    { label: 'Currency', key: 'currency', sortable: true },
    { label: 'Region', key: 'region', sortable: true },
    { label: 'Channel', key: 'channel', sortable: true },
    { label: 'Legacy Amt', key: 'legacy_amount', sortable: true },
    { label: 'New Amt', key: 'new_system_amount', sortable: true },
    { label: 'Diff %', key: 'amount_diff_pct', sortable: true },
    { label: 'Leg Status', key: 'legacy_status' },
    { label: 'New Status', key: 'new_system_status' },
  ]

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
            <h1 className="text-slate-800 text-2xl font-bold tracking-tight">Validation Results</h1>
          </div>
          <p className="text-slate-400 text-sm mt-1 font-medium">
            Transaction-level reconciliation logs · {total.toLocaleString()} records
          </p>
        </div>

        <div className="flex items-center gap-2">
          {/* Database Info Badge */}
          <div className="flex items-center gap-1.5 px-3 py-1.5 bg-white border border-slate-200 rounded-md text-[11px] font-semibold text-slate-500">
            <Database size={12} className="text-blue-500" />
            <span>ue74066.snowflake</span>
          </div>

          <button
            id="results-refresh"
            onClick={() => fetchData(true, true)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-md border border-slate-200 bg-white text-slate-600 hover:bg-slate-50 transition-all"
          >
            <RefreshCw size={12} /> Sync
          </button>
          <button
            id="export-csv"
            onClick={exportCSV}
            disabled={loading || sorted.length === 0}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-md border border-slate-200 bg-white text-slate-600 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed transition-all"
          >
            <Download size={12} /> Export CSV
          </button>
        </div>
      </div>

      {/* Filters & Actions Bar */}
      <div className="flex items-center justify-between gap-4 flex-wrap bg-white border border-slate-200/80 p-4 rounded-lg shadow-sm">
        <div className="flex items-center gap-3 flex-wrap flex-1">
          <div className="relative">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              id="txn-search"
              ref={searchRef}
              type="text"
              placeholder="Search TXN ID or customer… (/)"
              value={search}
              onChange={e => setSearch(e.target.value)}
              className="pl-8 pr-4 py-2 text-xs border border-slate-200 rounded-md bg-white text-slate-700 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent w-64 transition-all"
            />
          </div>

          {/* Custom Month Filter Dropdown */}
          <div className="relative" ref={dropdownRef}>
            <button
              id="month-filter-toggle"
              onClick={() => setDropdownOpen(!dropdownOpen)}
              className="flex items-center gap-2 px-3 py-2 text-xs font-semibold border border-slate-200 rounded-md bg-white text-slate-600 hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-blue-500 transition-all cursor-pointer shadow-sm min-w-[140px]"
            >
              <Calendar size={13} className="text-slate-400 shrink-0" />
              <span className="flex-1 text-left">
                {selectedMonth === 'ALL'
                  ? 'All Months'
                  : (() => {
                      const [year, month] = selectedMonth.split('-')
                      const date = new Date(parseInt(year), parseInt(month) - 1, 1)
                      return date.toLocaleDateString('en-US', { month: 'long', year: 'numeric' })
                    })()}
              </span>
              <ChevronDown size={12} className={`text-slate-400 transition-transform ${dropdownOpen ? 'rotate-180' : ''}`} />
            </button>

            {dropdownOpen && (
              <div className="absolute left-0 mt-1.5 w-56 bg-white border border-slate-200 rounded-lg shadow-lg py-1.5 z-50 animate-in fade-in duration-100 slide-in-from-top-1 max-h-72 overflow-y-auto">
                <button
                  onClick={() => {
                    setSelectedMonth('ALL')
                    setDropdownOpen(false)
                  }}
                  className={`w-full text-left px-4 py-2 text-xs font-semibold transition-colors ${
                    selectedMonth === 'ALL'
                      ? 'bg-blue-50 text-blue-600'
                      : 'text-slate-600 hover:bg-slate-50'
                  }`}
                >
                  All Months
                </button>

                {Object.entries(groupedMonths).map(([year, monthsList]) => (
                  <div key={year} className="border-t border-slate-100 mt-1.5 pt-1.5">
                    <div className="px-4 py-1 text-[9px] font-bold text-slate-400 uppercase tracking-wider bg-slate-50/50">
                      {year}
                    </div>
                    {monthsList.map(({ value, label }) => (
                      <button
                        key={value}
                        onClick={() => {
                          setSelectedMonth(value)
                          setDropdownOpen(false)
                        }}
                        className={`w-full text-left px-6 py-1.5 text-xs font-medium transition-colors ${
                          selectedMonth === value
                            ? 'bg-blue-50 text-blue-600 font-semibold'
                            : 'text-slate-600 hover:bg-slate-50'
                        }`}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                ))}
              </div>
            )}
          </div>
          <div className="flex gap-1 flex-wrap">
            {STATUSES.map(s => (
              <button
                key={s}
                id={`filter-${s.toLowerCase()}`}
                onClick={() => setStatus(s)}
                className={`px-2.5 py-1.5 text-xs font-semibold rounded-md border transition-all ${
                  status === s
                    ? 'bg-blue-50 text-blue-600 border-blue-200 shadow-sm shadow-blue-500/5'
                    : 'bg-white text-slate-500 border-slate-200 hover:bg-slate-50 hover:text-slate-700'
                }`}
              >
                {s === 'ALL' ? 'All' : s.replace(/_/g, ' ')}
              </button>
            ))}
          </div>
        </div>

        {/* Rows per page */}
        <div className="flex items-center gap-2 shrink-0">
          <span className="text-xs text-slate-400 font-medium">Rows per page:</span>
          <div className="flex gap-1">
            {PAGE_SIZE_OPTIONS.map(sz => (
              <button
                key={sz}
                id={`page-size-${sz}`}
                onClick={() => setPageSize(sz)}
                className={`px-2.5 py-1.5 text-xs font-semibold rounded-md border transition-all ${
                  pageSize === sz
                    ? 'bg-blue-50 text-blue-600 border-blue-200'
                    : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50 hover:text-slate-700'
                }`}
              >
                {sz}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Main Table Grid */}
      <div className="bg-white border border-slate-200 rounded-lg overflow-hidden shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-200 text-slate-400 font-semibold uppercase tracking-wider text-[10px]">
                <th className="w-8 px-3 py-3" />
                {COLUMNS.map(({ label, key, sortable }) => (
                  <th
                    key={key}
                    className={`px-4 py-3.5 text-left whitespace-nowrap ${sortable ? 'cursor-pointer hover:text-slate-700 select-none' : ''}`}
                    onClick={sortable ? () => handleSort(key) : undefined}
                  >
                    <div className="flex items-center gap-1.5">
                      <span>{label}</span>
                      {sortable && <SortIcon col={key} sortKey={sortKey} sortDir={sortDir} />}
                    </div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading ? (
                Array.from({ length: pageSize }).map((_, i) => <SkeletonRow key={i} />)
              ) : paginated.length === 0 ? (
                <tr><td colSpan={12} className="px-4 py-8 text-center text-slate-400 text-sm">No validation entries match parameters.</td></tr>
              ) : paginated.flatMap(row => {
                const isExpanded = expandedRow === row.txn_id
                return [
                  <tr
                    key={row.txn_id}
                    className="hover:bg-slate-50/60 transition-colors cursor-pointer text-slate-600"
                    onClick={() => setExpandedRow(isExpanded ? null : row.txn_id)}
                  >
                    <td className="px-3 py-3 text-slate-400 text-center">
                      <ChevronRight size={14} className={`transition-transform duration-200 ${isExpanded ? 'rotate-90 text-blue-500' : ''}`} />
                    </td>
                    <td className="px-4 py-3 font-mono text-[11px] text-slate-700 font-semibold">{row.txn_id}</td>
                    <td className="px-4 py-3">
                      <span className={`inline-block px-2 py-0.5 text-[10px] font-semibold rounded border ${STATUS_BADGE[row.validation_status] || ''}`}>
                        {row.validation_status.replace(/_/g, ' ')}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-slate-500 font-medium">{row.txn_date || '—'}</td>
                    <td className="px-4 py-3 text-slate-500">{row.customer_id || '—'}</td>
                    <td className="px-4 py-3 font-semibold text-slate-700">{row.currency}</td>
                    <td className="px-4 py-3 font-medium">{row.region}</td>
                    <td className="px-4 py-3 font-medium text-slate-500">{row.channel}</td>
                    <td className="px-4 py-3 text-slate-700 font-semibold">{fmt(row.legacy_amount)}</td>
                    <td className="px-4 py-3 text-slate-700 font-semibold">{fmt(row.new_system_amount)}</td>
                    <td className="px-4 py-3">
                      {row.amount_diff_pct !== null && row.amount_diff_pct !== undefined
                        ? <span className={`font-semibold ${Math.abs(row.amount_diff_pct) > 1 ? 'text-red-600' : 'text-slate-600'}`}>
                            {Number(row.amount_diff_pct).toFixed(2)}%
                          </span>
                        : <span className="text-slate-300">—</span>}
                    </td>
                    <td className="px-4 py-3 text-slate-500 font-medium">{row.legacy_status || '—'}</td>
                    <td className="px-4 py-3 text-slate-500 font-medium">{row.new_system_status || '—'}</td>
                  </tr>,
                  ...(isExpanded ? [<DetailRow key={`${row.txn_id}-detail`} row={row} />] : [])
                ]
              })}
            </tbody>
          </table>
        </div>

        {/* Footer info */}
        {!loading && (
          <div className="px-6 py-4 border-t border-slate-100 flex items-center justify-between flex-wrap gap-4 text-xs font-semibold text-slate-400">
            <p>
              Showing {sorted.length === 0 ? 0 : page * pageSize + 1}–{Math.min((page + 1) * pageSize, sorted.length)} of {sorted.length.toLocaleString()} rows
              {sortKey && <span className="ml-2 text-blue-500 font-medium">· sorted by {sortKey.replace(/_/g, ' ')}</span>}
            </p>
            <div className="flex items-center gap-1.5">
              <button
                id="pagination-prev"
                onClick={() => setPage(p => Math.max(0, p - 1))}
                disabled={page === 0}
                className="px-3 py-1.5 text-xs font-bold rounded-md border border-slate-200 bg-white text-slate-600 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed transition-all"
              >
                ← Prev
              </button>
              {visiblePages().map((p, i) =>
                p === '…' ? (
                  <span key={`ellipsis-${i}`} className="px-2 text-slate-300 text-xs">…</span>
                ) : (
                  <button
                    key={p}
                    id={`pagination-page-${p}`}
                    onClick={() => setPage(p as number)}
                    className={`w-8 h-8 text-xs font-bold rounded-md border transition-all ${
                      page === p
                        ? 'bg-blue-50 text-blue-600 border-blue-200 shadow-sm shadow-blue-500/5'
                        : 'bg-white text-slate-500 border-slate-200 hover:bg-slate-50 hover:text-slate-700'
                    }`}
                  >
                    {(p as number) + 1}
                  </button>
                )
              )}
              <button
                id="pagination-next"
                onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}
                disabled={page >= totalPages - 1}
                className="px-3 py-1.5 text-xs font-bold rounded-md border border-slate-200 bg-white text-slate-600 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed transition-all"
              >
                Next →
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
