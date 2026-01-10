import { useEffect, useMemo, useState } from 'react'
import Plot from 'react-plotly.js'

import { FilterBar } from '../components/FilterBar.jsx'
import { useItemSuggestions } from '../hooks/useItemSuggestions.js'
import {
  estimateItemPrice,
  getNonEquipmentHistory,
  listCategories,
  listEnchantments,
} from '../lib/api.js'
import { formatYang } from '../lib/format.js'
import { useTheme } from '../lib/theme.js'

export default function PriceHistoryPage() {
  const { isDark } = useTheme()

  const servers = useMemo(
    () => [
      { value: '502', label: 'Europe' },
      { value: '71', label: 'Teutonia' },
    ],
    [],
  )

  const [serverId, setServerId] = useState('502')
  const [category, setCategory] = useState('')
  const [selectedEnchantments, setSelectedEnchantments] = useState([])
  const [enchantMode, setEnchantMode] = useState('AND')

  const [q, setQ] = useState('')
  const [selected, setSelected] = useState([]) // [{item_vnum,item_name}]
  const [days, setDays] = useState(60)

  const [categoryOptions, setCategoryOptions] = useState([])
  const [enchantmentOptions, setEnchantmentOptions] = useState([])

  const [loadingSeries, setLoadingSeries] = useState(false)
  const [error, setError] = useState('')
  const [series, setSeries] = useState([])

  const {
    results: searchResults,
    loading: loadingSearch,
    error: searchError,
  } = useItemSuggestions(q, { limit: 30, debounceMs: 250 })

  const [estimating, setEstimating] = useState(false)
  const [estimateByVnum, setEstimateByVnum] = useState({})

  useEffect(() => {
    let cancelled = false

    async function loadReference() {
      try {
        const [cats, enchs] = await Promise.all([listCategories(), listEnchantments()])
        if (cancelled) return

        // FilterBar expects {value,label}
        setCategoryOptions((cats || []).map((c) => ({ value: c.id, label: c.label })))
        setEnchantmentOptions((enchs || []).map((e) => ({ value: e.id, label: e.label })))
      } catch (e) {
        // Keep page usable if reference files are missing; show as a non-blocking error.
        if (!cancelled) setError(String(e.message || e))
      }
    }

    loadReference()
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    // Keep existing error UI but treat search errors as non-blocking.
    if (searchError) setError(searchError)
  }, [searchError])

  function toggleSelected(item) {
    setSelected((prev) => {
      const exists = prev.some((p) => p.item_vnum === item.item_vnum)
      if (exists) return prev.filter((p) => p.item_vnum !== item.item_vnum)
      return [...prev, { item_vnum: item.item_vnum, item_name: item.item_name }]
    })
  }

  function removeSelected(vnum) {
    setSelected((prev) => prev.filter((p) => p.item_vnum !== vnum))
  }

  async function loadSeries() {
    setError('')
    if (selected.length === 0) {
      setSeries([])
      return
    }
    setLoadingSeries(true)
    try {
      const vnums = selected.map((s) => s.item_vnum)
      const data = await getNonEquipmentHistory(vnums, days, {
        serverId: serverId ? Number(serverId) : null,
        categoryId: category || null,
        enchantments: selectedEnchantments,
        enchantMode,
      })
      setSeries(data.series || [])
    } catch (e) {
      setError(String(e.message || e))
    } finally {
      setLoadingSeries(false)
    }
  }

  const plotData = useMemo(() => {
    const traces = []
    for (const s of series) {
      const minY = (s.min_price_yang || []).map((v) => {
        if (v === null || v === undefined) return null
        const n = Number(v)
        if (!Number.isFinite(n)) return null
        return n > 0 ? n : null
      })
      const avgY = (s.avg_price_yang || []).map((v) => {
        if (v === null || v === undefined) return null
        const n = Number(v)
        if (!Number.isFinite(n)) return null
        return n > 0 ? n : null
      })

      const minText = minY.map((v) => formatYang(v))
      traces.push({
        x: s.dates,
        y: minY,
        type: 'scatter',
        mode: 'lines+markers',
        name: `${s.item_name} (min)`,
        text: minText,
        hovertemplate: '%{x}<br>%{text}<extra></extra>',
      })

      const avgText = avgY.map((v) => formatYang(v))
      traces.push({
        x: s.dates,
        y: avgY,
        type: 'scatter',
        mode: 'lines',
        name: `${s.item_name} (avg)`,
        line: { dash: 'dot' },
        text: avgText,
        hovertemplate: '%{x}<br>%{text}<extra></extra>',
      })
    }
    return traces
  }, [series])

  const yRange = useMemo(() => {
    const values = []
    for (const s of series || []) {
      for (const arr of [s.min_price_yang, s.avg_price_yang]) {
        for (const v of arr || []) {
          if (v === null || v === undefined) continue
          const n = Number(v)
          if (!Number.isFinite(n)) continue
          if (n <= 0) continue
          values.push(n)
        }
      }
    }
    if (values.length === 0) return null
    const max = Math.max(...values)
    if (!Number.isFinite(max)) return null
    const padUp = Math.max(1, max * 0.04)
    return [0, max + padUp]
  }, [series])

  const yTicks = useMemo(() => {
    if (!yRange) return null
    const [min, max] = yRange
    const n = 6
    if (!Number.isFinite(min) || !Number.isFinite(max) || n < 2) return null
    const step = (max - min) / (n - 1)
    const tickvals = Array.from({ length: n }, (_, i) => Math.round(min + step * i))
    const ticktext = tickvals.map((v) => formatYang(v))
    return { tickvals, ticktext }
  }, [yRange])

  const tableRows = useMemo(() => {
    return series
      .map((s) => {
        const n = s.dates?.length || 0
        if (!n) return null
        return {
          item_vnum: s.item_vnum,
          item_name: s.item_name,
          date: s.dates[n - 1],
          min_price_yang: s.min_price_yang?.[n - 1],
          min_price_count: s.min_price_count?.[n - 1],
          median_lowest5_yang: s.median_lowest5_yang?.[n - 1],
        }
      })
      .filter(Boolean)
  }, [series])

  useEffect(() => {
    setEstimateByVnum({})
  }, [serverId, category, selectedEnchantments, enchantMode, days])

  async function estimateForSnapshot() {
    if (!tableRows || tableRows.length === 0) return
    setEstimating(true)
    setError('')
    try {
      const results = await Promise.all(
        tableRows.map(async (row) => {
          const resp = await estimateItemPrice({
            itemVnum: row.item_vnum,
            serverId: serverId ? Number(serverId) : null,
            categoryId: category || null,
            days,
            enchantments: selectedEnchantments,
            enchantMode,
          })
          return [row.item_vnum, resp]
        }),
      )
      setEstimateByVnum((prev) => {
        const next = { ...prev }
        for (const [vnum, resp] of results) next[vnum] = resp
        return next
      })
    } catch (e) {
      setError(String(e.message || e))
    } finally {
      setEstimating(false)
    }
  }

  return (
    <div>
      <FilterBar
        serverId={serverId}
        servers={servers}
        onServerIdChange={setServerId}
        category={category}
        categories={categoryOptions}
        onCategoryChange={setCategory}
        enchantments={enchantmentOptions}
        selectedEnchantments={selectedEnchantments}
        onSelectedEnchantmentsChange={setSelectedEnchantments}
        enchantMode={enchantMode}
        onEnchantModeChange={setEnchantMode}
        search={q}
        onSearchChange={setQ}
      />

      <div className="mt-4 rounded-lg border border-slate-200 bg-white p-4 flex flex-col md:flex-row gap-3 md:items-end md:justify-between dark:border-slate-800 dark:bg-slate-950">
        <label>
          <div className="text-xs font-medium text-slate-700 mb-1 dark:text-slate-300">Window</div>
          <select
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100"
          >
            <option value={30}>30 days</option>
            <option value={60}>60 days</option>
            <option value={90}>90 days</option>
            <option value={180}>180 days</option>
            <option value={365}>365 days</option>
          </select>
        </label>

        <button
          className="rounded-md bg-slate-100 px-3 py-2 text-sm text-slate-900 hover:bg-white disabled:opacity-50"
          onClick={loadSeries}
          disabled={loadingSeries || selected.length === 0}
        >
          {loadingSeries ? 'Loading…' : 'Plot'}
        </button>
      </div>

      {error ? <div className="mt-3 text-sm text-red-300">{error}</div> : null}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mt-4">
        <div className="lg:col-span-2">
          <div className="rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-950">
            <div className="text-sm font-semibold text-slate-900 dark:text-slate-100">Search results</div>
            {loadingSearch ? <div className="mt-2 text-sm text-slate-600 dark:text-slate-400">Searching…</div> : null}

            <div className="mt-3 max-h-[360px] overflow-auto rounded border border-slate-200 dark:border-slate-800">
              {(searchResults || []).map((it) => {
                const checked = selected.some((p) => p.item_vnum === it.item_vnum)
                return (
                  <label
                    key={it.item_vnum}
                    className="flex gap-3 px-3 py-2 border-b border-slate-200 hover:bg-slate-100 cursor-pointer dark:border-slate-800 dark:hover:bg-slate-900/40"
                  >
                    <input type="checkbox" checked={checked} onChange={() => toggleSelected(it)} />
                    <div className="flex-1">
                      <div className="text-slate-900 font-medium dark:text-slate-100">{it.item_name}</div>
                      <div className="text-xs text-slate-600 dark:text-slate-400">vnum: {it.item_vnum}</div>
                    </div>
                  </label>
                )
              })}
              {q.trim() && !loadingSearch && (searchResults || []).length === 0 ? (
                <div className="px-3 py-3 text-sm text-slate-600 dark:text-slate-400">No matches.</div>
              ) : null}
            </div>
          </div>
        </div>

        <div>
          <div className="rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-950">
            <div className="text-sm font-semibold text-slate-900 dark:text-slate-100">Selected items</div>
            {selected.length === 0 ? (
              <div className="mt-2 text-sm text-slate-600 dark:text-slate-400">Select one or more items.</div>
            ) : null}
            <div className="mt-3 flex flex-col gap-2">
              {selected.map((s) => (
                <div key={s.item_vnum} className="flex items-center justify-between gap-2">
                  <div className="text-sm">
                    <div className="text-slate-900 font-medium dark:text-slate-100">{s.item_name}</div>
                    <div className="text-xs text-slate-600 dark:text-slate-400">{s.item_vnum}</div>
                  </div>
                  <button
                    className="rounded-md border border-slate-300 bg-white px-2 py-1 text-sm text-slate-900 hover:bg-slate-100 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-200 dark:hover:bg-slate-900/40"
                    onClick={() => removeSelected(s.item_vnum)}
                  >
                    remove
                  </button>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {plotData.length > 0 ? (
        <div className="mt-6 rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-950">
          <div className="text-sm font-semibold mb-3 text-slate-900 dark:text-slate-100">Daily lowest price</div>
          <div className="flex justify-center">
            <Plot
              data={plotData}
              layout={{
                title: 'Daily lowest price',
                xaxis: { title: 'Date' },
                yaxis: {
                  title: 'Price (w + y)',
                  rangemode: 'normal',
                  zeroline: false,
                  range: yRange || undefined,
                  tickmode: yTicks ? 'array' : undefined,
                  tickvals: yTicks?.tickvals,
                  ticktext: yTicks?.ticktext,
                },
                template: isDark ? 'plotly_dark' : 'plotly_white',
                paper_bgcolor: 'rgba(0,0,0,0)',
                plot_bgcolor: 'rgba(0,0,0,0)',
                legend: { orientation: 'h' },
              }}
              style={{ width: '100%', maxWidth: 1200, height: 520 }}
              config={{ displayModeBar: true }}
            />
          </div>
        </div>
      ) : null}

      {tableRows.length > 0 ? (
        <div className="mt-6 rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-950">
          <div className="flex items-center justify-between mb-3">
            <div className="text-sm font-semibold text-slate-900 dark:text-slate-100">Latest snapshot</div>
            <button
              className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 hover:bg-slate-100 disabled:opacity-50 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100 dark:hover:bg-slate-900"
              onClick={estimateForSnapshot}
              disabled={estimating || tableRows.length === 0}
            >
              {estimating ? 'Estimating…' : 'Estimate prices'}
            </button>
          </div>
          <div className="overflow-auto rounded border border-slate-200 dark:border-slate-800">
            <table className="w-full text-sm">
              <thead className="bg-slate-100 text-slate-700 dark:bg-slate-900/40 dark:text-slate-200">
                <tr>
                  <th className="text-left px-3 py-2">Item</th>
                  <th className="text-left px-3 py-2">Date</th>
                  <th className="text-right px-3 py-2">Min</th>
                  <th className="text-right px-3 py-2">Count@Min</th>
                  <th className="text-right px-3 py-2">Median(lowest5)</th>
                  <th className="text-right px-3 py-2">Obs(match)</th>
                  <th className="text-right px-3 py-2">Estimate</th>
                  <th className="text-left px-3 py-2">Basis</th>
                </tr>
              </thead>
              <tbody>
                {tableRows.map((r) => {
                  const est = estimateByVnum?.[r.item_vnum]
                  const obsMatch = est?.observed_min_price_yang
                  const estimate = est?.estimated_price_yang
                  const basis = est?.estimate_basis || ''
                  return (
                    <tr key={r.item_vnum} className="border-t border-slate-200 dark:border-slate-800">
                      <td className="px-3 py-2 text-slate-900 font-medium dark:text-slate-100">{r.item_name}</td>
                      <td className="px-3 py-2">{r.date}</td>
                      <td className="px-3 py-2 text-right">{formatYang(r.min_price_yang)}</td>
                      <td className="px-3 py-2 text-right">{r.min_price_count}</td>
                      <td className="px-3 py-2 text-right">{formatYang(r.median_lowest5_yang)}</td>
                      <td className="px-3 py-2 text-right">{obsMatch != null ? formatYang(obsMatch) : '-'}</td>
                      <td className="px-3 py-2 text-right">{estimate != null ? formatYang(estimate) : '-'}</td>
                      <td className="px-3 py-2">{basis}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </div>
  )
}
