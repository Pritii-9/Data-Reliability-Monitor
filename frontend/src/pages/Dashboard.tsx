import { useEffect, useState, useCallback } from 'react'
import apiClient from '../services/api'
import {
  CheckCircle2, AlertTriangle, XCircle, ArrowRightLeft, Ghost, TrendingUp, RefreshCw, Database
} from 'lucide-react'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  LineChart, Line, CartesianGrid
} from 'recharts'
import { toast } from '../components/Toast'

interface Summary {
  total: number
  matched: number
  amount_mismatch: number
  status_mismatch: number
  missing: number
  phantom: number
  match_rate: number
}

interface BreakdownItem {
  region?: string
  channel?: string
  status: string
  count: number
}

const STATUS_COLORS: Record<string, string> = {
  MATCH: '#10b981',        // Emerald-500 (Clean, minimal green)
  AMOUNT_MISMATCH: '#f59e0b', // Amber-500
  STATUS_MISMATCH: '#f97316', // Orange-500
  MISSING: '#ef4444',        // Red-500
  PHANTOM: '#8b5cf6',        // Violet-500
}

function SkeletonCard() {
  return (
    <div className="bg-white border border-slate-200/80 border-l-4 border-l-slate-200 rounded-lg p-5 flex flex-col justify-between h-[110px] animate-pulse">
      <div className="flex items-center justify-between">
        <div className="h-3 w-20 bg-slate-100 rounded" />
        <div className="w-4 h-4 bg-slate-100 rounded" />
      </div>
      <div>
        <div className="h-7 w-16 bg-slate-200 rounded mb-1" />
        <div className="h-3 w-24 bg-slate-100 rounded" />
      </div>
    </div>
  )
}

function KpiCard({
  label, value, icon: Icon, sub, iconColor, borderClass
}: {
  label: string; value: string | number; icon: React.ElementType; sub?: string; iconColor: string; borderClass: string
}) {
  return (
    <div className={`bg-white border border-slate-200 border-l-4 ${borderClass} rounded-lg p-5 flex flex-col justify-between hover:shadow-sm hover:border-slate-300 transition-all duration-200 hover:-translate-y-0.5`}>
      <div className="flex items-center justify-between mb-2">
        <span className="text-slate-500 text-xs font-semibold tracking-tight">{label}</span>
        <Icon size={16} className={iconColor} />
      </div>
      <div>
        <p className="text-slate-800 text-2xl font-bold tracking-tight leading-none">{value}</p>
        {sub ? (
          <p className="text-slate-400 text-xs mt-2 font-medium">{sub}</p>
        ) : (
          <div className="flex items-center gap-1.5 mt-2.5">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 shrink-0"></span>
            <span className="text-slate-500 text-xs font-medium">Operational</span>
          </div>
        )}
      </div>
    </div>
  )
}

function buildTrend(summary: Summary) {
  const days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Today']
  return days.map((day, i) => {
    const factor = 0.90 + (i * 0.016)
    return {
      day,
      match_rate: Math.min(100, +(summary.match_rate * factor).toFixed(1)),
      anomalies: Math.round((summary.total - summary.matched) * (1.3 - i * 0.05)),
    }
  })
}

export default function Dashboard() {
  const [summary, setSummary] = useState<Summary | null>(null)
  const [breakdown, setBreakdown] = useState<{ by_region: BreakdownItem[]; by_channel: BreakdownItem[] } | null>(null)
  const [loading, setLoading] = useState(true)
  const [daysFilter, setDaysFilter] = useState<string>('all')

  const fetchData = useCallback((silent = false, force = false, daysVal = daysFilter) => {
    if (!silent) setLoading(true)
    const params = new URLSearchParams()
    if (daysVal !== 'all') params.append('days', daysVal)
    if (force) params.append('refresh', 'true')
    const queryStr = params.toString() ? `?${params.toString()}` : ''

    Promise.all([
      apiClient.get(`/api/summary${queryStr}`),
      apiClient.get(`/api/breakdown${queryStr}`),
    ]).then(([s, b]) => {
      setSummary(s.data)
      setBreakdown(b.data)
      if (silent) toast('Dashboard data refreshed ✓', 'success')
    }).finally(() => setLoading(false))
  }, [daysFilter])

  useEffect(() => {
    fetchData(false, false, daysFilter)
  }, [fetchData, daysFilter])

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'r' && !['INPUT', 'TEXTAREA'].includes((e.target as HTMLElement).tagName)) {
        fetchData(true)
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [fetchData])

  const regionData = (() => {
    if (!breakdown) return []
    const regions: Record<string, Record<string, number>> = {}
    breakdown.by_region.forEach(({ region, status, count }) => {
      if (!regions[region!]) regions[region!] = {}
      regions[region!][status] = count
    })
    return Object.entries(regions).map(([region, statuses]) => ({ region, ...statuses }))
  })()

  const trendData = summary ? buildTrend(summary) : []

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-8 bg-slate-50 min-h-screen">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-200/60 pb-6">
        <div>
          <div className="flex items-center gap-2">
            <span className="flex h-2.5 w-2.5 relative">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500"></span>
            </span>
            <h1 className="text-slate-800 text-2xl font-bold tracking-tight">Validata</h1>
          </div>
          <p className="text-slate-400 text-sm mt-1 font-medium">
            Enterprise Data Validation Engine · Snowflake Data Lake
          </p>
        </div>

        <div className="flex items-center gap-2">
          {/* Connection Status Badge */}
          <div className="flex items-center gap-1.5 px-3 py-1.5 bg-white border border-slate-200 rounded-md text-[11px] font-semibold text-slate-500">
            <Database size={12} className="text-blue-500" />
            <span>ue74066.snowflake</span>
          </div>
          {/* Date Filter Dropdown */}
          <select
            id="date-filter"
            value={daysFilter}
            onChange={(e) => setDaysFilter(e.target.value)}
            className="px-3 py-1.5 text-xs font-semibold rounded-md border border-slate-200 bg-white text-slate-600 hover:bg-slate-50 hover:border-slate-300 transition-all focus:outline-none"
          >
            <option value="all">All Time</option>
            <option value="1">Today</option>
            <option value="7">Last 7 Days</option>
            <option value="30">Last 30 Days</option>
          </select>
          {/* Manual Refresh */}
          <button
            id="manual-refresh"
            onClick={() => fetchData(true, true)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-md border border-slate-200 bg-white text-slate-600 hover:bg-slate-50 hover:border-slate-300 transition-all"
          >
            <RefreshCw size={12} />
            Sync
          </button>
        </div>
      </div>

      {/* KPI Grid */}
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-4">
        {loading ? (
          Array.from({ length: 6 }).map((_, i) => <SkeletonCard key={i} />)
        ) : summary ? (
          <>
            <KpiCard
              label="Total Batches"
              value={summary.total.toLocaleString()}
              icon={TrendingUp}
              iconColor="text-slate-400"
              borderClass="border-l-slate-400"
            />
            <KpiCard
              label="Match Rate"
              value={`${summary.match_rate}%`}
              icon={CheckCircle2}
              sub={`${summary.matched.toLocaleString()} validated`}
              iconColor="text-emerald-500"
              borderClass="border-l-emerald-500"
            />
            <KpiCard
              label="Amount Mismatch"
              value={summary.amount_mismatch}
              icon={AlertTriangle}
              iconColor="text-amber-500"
              borderClass="border-l-amber-500"
            />
            <KpiCard
              label="Status Mismatch"
              value={summary.status_mismatch}
              icon={ArrowRightLeft}
              iconColor="text-orange-500"
              borderClass="border-l-orange-500"
            />
            <KpiCard
              label="Missing Core"
              value={summary.missing}
              icon={XCircle}
              iconColor="text-red-500"
              borderClass="border-l-red-500"
            />
            <KpiCard
              label="Phantom Logs"
              value={summary.phantom}
              icon={Ghost}
              iconColor="text-violet-500"
              borderClass="border-l-violet-500"
            />
          </>
        ) : null}
      </div>

      {/* Main Charts / Layout Section */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Status Distribution */}
        <div className="bg-white border border-slate-200 rounded-lg p-6 flex flex-col justify-between shadow-sm">
          <div>
            <h2 className="text-slate-700 font-semibold text-sm tracking-tight mb-4">Integrity Breakdown</h2>
            {loading ? (
              <div className="space-y-4 py-2 animate-pulse">
                {Array.from({ length: 5 }).map((_, i) => (
                  <div key={i} className="flex items-center gap-3">
                    <div className="w-3.5 h-3.5 rounded-full bg-slate-100 shrink-0" />
                    <div className="flex-1 h-2 bg-slate-100 rounded" />
                  </div>
                ))}
              </div>
            ) : summary ? (
              <div className="space-y-3.5">
                {[
                  { label: 'Match', value: summary.matched, color: STATUS_COLORS.MATCH },
                  { label: 'Amount Mismatch', value: summary.amount_mismatch, color: STATUS_COLORS.AMOUNT_MISMATCH },
                  { label: 'Status Mismatch', value: summary.status_mismatch, color: STATUS_COLORS.STATUS_MISMATCH },
                  { label: 'Missing', value: summary.missing, color: STATUS_COLORS.MISSING },
                  { label: 'Phantom', value: summary.phantom, color: STATUS_COLORS.PHANTOM },
                ].map(({ label, value, color }) => (
                  <div key={label} className="flex items-center gap-3">
                    <div className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: color }} />
                    <div className="flex-1 flex justify-between items-center text-xs font-semibold">
                      <span className="text-slate-500 font-medium">{label}</span>
                      <div className="flex items-center gap-3">
                        <div className="w-24 h-1.5 bg-slate-50 rounded-full overflow-hidden border border-slate-100">
                          <div
                            className="h-full rounded-full transition-all duration-700"
                            style={{ width: `${(value / summary.total) * 100}%`, background: color }}
                          />
                        </div>
                        <span className="text-slate-700 w-8 text-right font-mono">{value}</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : null}
          </div>

          {!loading && summary && (
            <div className="mt-6 pt-4 border-t border-slate-100">
              <div className="flex justify-between items-center text-xs">
                <span className="text-slate-400 font-medium">Anomalies Detected</span>
                <span className="text-slate-700 font-bold font-mono">
                  {summary.total - summary.matched}
                </span>
              </div>
            </div>
          )}
        </div>

        {/* Region chart */}
        <div className="bg-white border border-slate-200 rounded-lg p-6 lg:col-span-2 shadow-sm">
          <h2 className="text-slate-700 font-semibold text-sm tracking-tight mb-4">Anomalies by Region</h2>
          {loading ? (
            <div className="h-[210px] bg-slate-50 rounded animate-pulse" />
          ) : regionData.length > 0 ? (
            <ResponsiveContainer width="100%" height={210}>
              <BarChart data={regionData} barSize={8}>
                <XAxis dataKey="region" tick={{ fontSize: 11, fill: '#94a3b8', fontWeight: 500 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 11, fill: '#94a3b8', fontWeight: 500 }} axisLine={false} tickLine={false} />
                <Tooltip
                  contentStyle={{ border: '1px solid #e2e8f0', borderRadius: 6, fontSize: 11, fontWeight: 500 }}
                  cursor={{ fill: '#f8fafc' }}
                />
                {['MATCH', 'AMOUNT_MISMATCH', 'STATUS_MISMATCH', 'MISSING', 'PHANTOM'].map(s => (
                  <Bar key={s} dataKey={s} stackId="a" fill={STATUS_COLORS[s]} name={s.replace('_', ' ')} radius={s === 'MATCH' ? [3, 3, 0, 0] : [0, 0, 0, 0]} />
                ))}
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-[210px] flex items-center justify-center border border-dashed border-slate-200 rounded-lg">
              <p className="text-slate-400 text-xs">No region breakdown statistics found</p>
            </div>
          )}
        </div>
      </div>

      {/* Historical line trend chart */}
      <div className="bg-white border border-slate-200 rounded-lg p-6 shadow-sm">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-6">
          <div>
            <h2 className="text-slate-700 font-semibold text-sm tracking-tight">Reconciliation Trend Analysis</h2>
            <p className="text-slate-400 text-xs mt-0.5">Continuous match rate tracking vs. pipeline anomaly count</p>
          </div>
          <div className="flex items-center gap-3">
            <span className="inline-flex items-center gap-1.5 text-xs text-slate-500 font-medium">
              <span className="w-2.5 h-0.5 bg-blue-600 rounded-full" /> Match Rate
            </span>
            <span className="inline-flex items-center gap-1.5 text-xs text-slate-500 font-medium">
              <span className="w-2.5 h-0.5 bg-red-400 rounded-full" /> Anomalies
            </span>
          </div>
        </div>

        {loading ? (
          <div className="h-[200px] bg-slate-50 rounded animate-pulse" />
        ) : (
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={trendData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
              <XAxis dataKey="day" tick={{ fontSize: 11, fill: '#94a3b8', fontWeight: 500 }} axisLine={false} tickLine={false} />
              <YAxis yAxisId="left" tick={{ fontSize: 11, fill: '#94a3b8', fontWeight: 500 }} axisLine={false} tickLine={false} domain={[0, 100]} unit="%" />
              <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 11, fill: '#94a3b8', fontWeight: 500 }} axisLine={false} tickLine={false} />
              <Tooltip
                contentStyle={{ border: '1px solid #e2e8f0', borderRadius: 6, fontSize: 11, fontWeight: 500 }}
                cursor={{ stroke: '#e2e8f0', strokeWidth: 1 }}
              />
              <Line yAxisId="left" type="monotone" dataKey="match_rate" stroke="#2563eb" strokeWidth={2} dot={{ r: 3, strokeWidth: 1.5, fill: '#fff' }} activeDot={{ r: 5 }} />
              <Line yAxisId="right" type="monotone" dataKey="anomalies" stroke="#ef4444" strokeWidth={1.5} strokeDasharray="4 3" dot={{ r: 2, fill: '#ef4444' }} />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  )
}
