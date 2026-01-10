import { useEffect, useState } from 'react'

import { getDeals } from '../lib/api.js'
import { formatPct, formatYang } from '../lib/format.js'

export default function DealsPage() {
  const [limit, setLimit] = useState(30)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [rows, setRows] = useState([])

  async function load() {
    setError('')
    setLoading(true)
    try {
      const data = await getDeals(limit)
      setRows(data.results || [])
    } catch (e) {
      setError(String(e.message || e))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <section className="space-y-4">
      <div className="flex flex-col gap-1">
        <h1 className="text-xl font-semibold">Deals</h1>
        <p className="text-sm text-slate-600 dark:text-slate-400">Undervalued items computed by ETL (fact_undervalued_items).</p>
      </div>

      <div className="rounded-lg border border-slate-200 bg-white p-4 flex flex-col gap-3 md:flex-row md:items-end md:justify-between dark:border-slate-800 dark:bg-slate-950">
        <label>
          <div className="text-xs font-medium text-slate-700 mb-1 dark:text-slate-300">Limit</div>
          <select
            className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100"
            value={limit}
            onChange={(e) => setLimit(Number(e.target.value))}
          >
          <option value={10}>10</option>
          <option value={30}>30</option>
          <option value={50}>50</option>
          <option value={100}>100</option>
          <option value={200}>200</option>
        </select>
        </label>

        <button
          className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 hover:bg-slate-100 disabled:opacity-50 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100 dark:hover:bg-slate-900"
          onClick={load}
          disabled={loading}
        >
          {loading ? 'Loading…' : 'Refresh'}
        </button>
      </div>

      {error ? <div className="text-sm text-red-300">{error}</div> : null}

      <div className="overflow-auto rounded-lg border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950">
        <table className="min-w-full text-sm">
          <thead className="bg-slate-100 text-slate-700 dark:bg-slate-900/40 dark:text-slate-200">
            <tr>
              <th className="px-3 py-2 text-left font-medium">Date</th>
              <th className="px-3 py-2 text-left font-medium">Item</th>
              <th className="px-3 py-2 text-right font-medium">Current</th>
              <th className="px-3 py-2 text-right font-medium">Fair value</th>
              <th className="px-3 py-2 text-right font-medium">Undervaluation</th>
              <th className="px-3 py-2 text-right font-medium">Profit</th>
              <th className="px-3 py-2 text-left font-medium">Rating</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, idx) => (
              <tr key={idx} className="border-t border-slate-200 dark:border-slate-800">
                <td className="px-3 py-2 whitespace-nowrap text-slate-700 dark:text-slate-300">{r.full_date}</td>
                <td className="px-3 py-2">
                  <div className="font-medium text-slate-900 dark:text-slate-100">{r.item_name}</div>
                  <div className="text-xs text-slate-600 dark:text-slate-400">{r.item_vnum}</div>
                </td>
                <td className="px-3 py-2 text-right whitespace-nowrap">{formatYang(r.current_price_yang)}</td>
                <td className="px-3 py-2 text-right whitespace-nowrap">{formatYang(r.estimated_fair_value_yang)}</td>
                <td className="px-3 py-2 text-right whitespace-nowrap">{formatPct(r.undervaluation_percentage)}</td>
                <td className="px-3 py-2 text-right whitespace-nowrap">{formatYang(r.potential_profit_yang)}</td>
                <td className="px-3 py-2">
                  <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-700 dark:bg-slate-900/40 dark:text-slate-200">
                    {r.deal_rating}
                  </span>
                </td>
              </tr>
            ))}
            {rows.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-3 py-8 text-center text-sm text-slate-600 dark:text-slate-400">
                  No deals found yet. Run a sync+ETL cycle first.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </section>
  )
}
