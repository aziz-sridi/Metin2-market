import { useEffect, useMemo, useState } from 'react'
import Plot from '../components/Plot.jsx'

import { useItemSuggestions } from '../hooks/useItemSuggestions.js'
import { estimateEquipment, getEquipmentBonusImpact } from '../lib/api.js'
import { formatYang } from '../lib/format.js'

export default function EquipmentAnalysisPage() {
  const [q, setQ] = useState('')
  const [selected, setSelected] = useState(null) // {item_vnum,item_name,item_type}

  const [days, setDays] = useState(30)
  const [topN, setTopN] = useState(12)
  const [examplesPerBonus, setExamplesPerBonus] = useState(3)

  const [bonusesText, setBonusesText] = useState('')

  const [loadingImpact, setLoadingImpact] = useState(false)
  const [loadingEstimate, setLoadingEstimate] = useState(false)
  const [error, setError] = useState('')

  const {
    results: searchResults,
    loading: loadingSearch,
    error: searchError,
  } = useItemSuggestions(q, { limit: 100, debounceMs: 250 })

  const [impact, setImpact] = useState(null) // {rows:[]}
  const [impactLoaded, setImpactLoaded] = useState(false)
  const [estimate, setEstimate] = useState(null)

  useEffect(() => {
    if (searchError) setError(searchError)
  }, [searchError])

  async function loadImpact() {
    setError('')
    setEstimate(null)
    if (!selected) return

    setImpactLoaded(false)
    setLoadingImpact(true)
    try {
      const data = await getEquipmentBonusImpact(selected.item_vnum, days, topN, examplesPerBonus)
      setImpact(data)
    } catch (e) {
      setError(String(e.message || e))
    } finally {
      setLoadingImpact(false)
      setImpactLoaded(true)
    }
  }

  async function runEstimate() {
    setError('')
    if (!selected) return

    setLoadingEstimate(true)
    try {
      const data = await estimateEquipment(selected.item_vnum, bonusesText, days)
      setEstimate(data)
    } catch (e) {
      setError(String(e.message || e))
    } finally {
      setLoadingEstimate(false)
    }
  }

  const plotData = useMemo(() => {
    if (!impact?.rows?.length) return []
    const x = impact.rows.map((r) => String(r.stat_name || r.stat_id))
    const y = impact.rows.map((r) => (r.premium === null ? null : r.premium))
    const text = impact.rows.map((r) => {
      const tv = r.typical_value != null ? `, value≈${r.typical_value}` : ''
      return `count=${r.count}${tv}`
    })
    return [
      {
        type: 'bar',
        x,
        y,
        text,
      },
    ]
  }, [impact])

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-xl font-semibold">Equipment</h1>
        <p className="text-sm text-slate-600 dark:text-slate-400">
          Analyze bonus impact and estimate price for a specific bonus set.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <section className="rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-950">
          <div className="text-sm font-semibold">Pick an item</div>

          <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
            <label className="block">
              <div className="text-xs font-medium text-slate-700 dark:text-slate-300">Search</div>
              <input
                className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100 dark:placeholder:text-slate-500"
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Search equipment item name (e.g. sword, armor)"
              />
            </label>

            <label className="block">
              <div className="text-xs font-medium text-slate-700 dark:text-slate-300">Window</div>
              <select
                className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100"
                value={days}
                onChange={(e) => setDays(Number(e.target.value))}
              >
                <option value={7}>7 days</option>
                <option value={14}>14 days</option>
                <option value={30}>30 days</option>
                <option value={60}>60 days</option>
                <option value={90}>90 days</option>
              </select>
            </label>
          </div>

          {error ? <div className="mt-3 text-sm text-red-300">{error}</div> : null}

          <div className="mt-3 overflow-auto rounded-md border border-slate-200 dark:border-slate-800">
            <table className="min-w-full text-sm">
              <thead className="bg-slate-100 text-slate-700 dark:bg-slate-900/40 dark:text-slate-200">
                <tr>
                  <th className="px-3 py-2 text-left font-medium">VNUM</th>
                  <th className="px-3 py-2 text-left font-medium">Name</th>
                  <th className="px-3 py-2 text-left font-medium">Type</th>
                  <th className="px-3 py-2 text-right font-medium">Action</th>
                </tr>
              </thead>
              <tbody>
                {(searchResults || []).map((r) => (
                  <tr key={r.item_vnum} className="border-t border-slate-200 dark:border-slate-800">
                    <td className="px-3 py-2 text-slate-700 whitespace-nowrap dark:text-slate-300">{r.item_vnum}</td>
                    <td className="px-3 py-2 font-medium text-slate-900 dark:text-slate-100">{r.item_name}</td>
                    <td className="px-3 py-2">
                      <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-700 dark:bg-slate-900/40 dark:text-slate-200">
                        {r.item_type}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right">
                      <button
                        className="rounded-md border border-slate-300 bg-white px-3 py-2 text-xs text-slate-900 hover:bg-slate-100 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-200 dark:hover:bg-slate-900/40"
                        onClick={() => setSelected(r)}
                        type="button"
                      >
                        Use
                      </button>
                    </td>
                  </tr>
                ))}
                {q.trim().length > 0 && (searchResults || []).length === 0 ? (
                  <tr>
                    <td colSpan={4} className="px-3 py-8 text-center text-sm text-slate-600 dark:text-slate-400">
                      {loadingSearch ? 'Searching…' : 'No matches.'}
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>

          <div className="mt-4 rounded-md bg-slate-50 p-3 dark:bg-slate-900/40">
            <div className="text-xs font-medium text-slate-700 dark:text-slate-300">Selected</div>
            <div className="mt-1 text-sm">
              {selected ? (
                <span className="font-semibold text-slate-900 dark:text-slate-100">
                  {selected.item_name} ({selected.item_vnum})
                </span>
              ) : (
                <span className="text-slate-600 dark:text-slate-400">None</span>
              )}
            </div>
          </div>

          <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-3 md:items-end">
            <label className="block">
              <div className="text-xs font-medium text-slate-700 dark:text-slate-300">Top N</div>
              <select
                className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100"
                value={topN}
                onChange={(e) => setTopN(Number(e.target.value))}
              >
                <option value={8}>8</option>
                <option value={12}>12</option>
                <option value={20}>20</option>
                <option value={30}>30</option>
              </select>
            </label>

            <label className="block">
              <div className="text-xs font-medium text-slate-700 dark:text-slate-300">Examples/bonus</div>
              <select
                className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100"
                value={examplesPerBonus}
                onChange={(e) => setExamplesPerBonus(Number(e.target.value))}
              >
                <option value={0}>0</option>
                <option value={1}>1</option>
                <option value={3}>3</option>
                <option value={5}>5</option>
              </select>
            </label>

            <button
              className="rounded-md bg-slate-100 px-3 py-2 text-sm text-slate-900 hover:bg-white disabled:opacity-50"
              onClick={loadImpact}
              disabled={!selected || loadingImpact}
              type="button"
            >
              {loadingImpact ? 'Loading…' : 'Load impact'}
            </button>
          </div>

          <div className="mt-6 border-t border-slate-200 pt-4 dark:border-slate-800">
            <div className="text-sm font-semibold">Estimator</div>
            <div className="mt-1 text-xs text-slate-600 dark:text-slate-400">
              Enter bonuses as stat:value pairs, e.g. 71:10,72:5
            </div>
            <div className="mt-3 flex flex-col gap-2 md:flex-row">
              <input
                className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100 dark:placeholder:text-slate-500"
                value={bonusesText}
                onChange={(e) => setBonusesText(e.target.value)}
                placeholder="71:10,72:5"
              />
              <button
                className="rounded-md bg-slate-100 px-3 py-2 text-sm text-slate-900 hover:bg-white disabled:opacity-50"
                onClick={runEstimate}
                disabled={!selected || loadingEstimate}
                type="button"
              >
                {loadingEstimate ? 'Estimating…' : 'Estimate'}
              </button>
            </div>

            {estimate?.estimated_price_yang != null ? (
              <div className="mt-3 text-sm">
                Estimated price: <span className="font-semibold">{formatYang(estimate.estimated_price_yang)}</span>
              </div>
            ) : null}
          </div>
        </section>

        <section className="rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-950">
          <div className="text-sm font-semibold">Bonus impact</div>
          <div className="text-xs text-slate-600 dark:text-slate-400">
            Which bonuses increase price the most (from historical listings).
          </div>

          {!plotData.length ? (
            <div className="mt-3 text-sm text-slate-600 dark:text-slate-400">
              {selected && impactLoaded && !impact?.rows?.length
                ? 'No bonus impact data found for this item in the selected window.'
                : 'Select an item and load impact.'}
            </div>
          ) : (
            <div className="mt-3 flex justify-center">
              <Plot
                data={plotData}
                layout={{
                  title: 'Bonuses that increase price the most',
                  height: 420,
                  margin: { l: 50, r: 20, t: 50, b: 60 },
                  xaxis: { title: 'bonus' },
                  yaxis: { title: 'Median premium (w + y)' },
                  template: 'plotly_white',
                  paper_bgcolor: 'rgba(0,0,0,0)',
                  plot_bgcolor: 'rgba(0,0,0,0)',
                }}
                style={{ width: '100%', maxWidth: 1000 }}
                useResizeHandler
              />
            </div>
          )}

          {impact?.rows?.length ? (
            <div className="mt-4 overflow-auto rounded-md border border-slate-200 dark:border-slate-800">
              <table className="min-w-full text-sm">
                <thead className="bg-slate-100 text-slate-700 dark:bg-slate-900/40 dark:text-slate-200">
                  <tr>
                    <th className="px-3 py-2 text-left font-medium">Bonus</th>
                    <th className="px-3 py-2 text-right font-medium">Value (typical)</th>
                    <th className="px-3 py-2 text-right font-medium">Count</th>
                    <th className="px-3 py-2 text-right font-medium">Premium</th>
                    <th className="px-3 py-2 text-right font-medium">Median with</th>
                    <th className="px-3 py-2 text-right font-medium">Median without</th>
                    <th className="px-3 py-2 text-left font-medium">Examples</th>
                  </tr>
                </thead>
                <tbody>
                  {impact.rows.map((r) => (
                    <tr key={r.stat_id} className="border-t border-slate-200 dark:border-slate-800">
                      <td className="px-3 py-2 font-medium text-slate-900 dark:text-slate-100">{r.stat_name || r.stat_id}</td>
                      <td className="px-3 py-2 text-right text-slate-700 dark:text-slate-300">
                        {r.typical_value != null ? r.typical_value : '—'}
                      </td>
                      <td className="px-3 py-2 text-right">{r.count}</td>
                      <td className="px-3 py-2 text-right">{formatYang(r.premium)}</td>
                      <td className="px-3 py-2 text-right">{formatYang(r.median_price_with)}</td>
                      <td className="px-3 py-2 text-right">{formatYang(r.median_price_without)}</td>
                      <td className="px-3 py-2">
                        {r.examples?.length ? (
                          <div className="text-xs text-slate-600 dark:text-slate-400">
                            {r.examples.map((ex, idx) => (
                              <div key={idx}>
                                {formatYang(ex.price_yang)} (value={ex.value})
                              </div>
                            ))}
                          </div>
                        ) : (
                          <span className="text-sm text-slate-600 dark:text-slate-400">—</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </section>
      </div>
    </div>
  )
}
