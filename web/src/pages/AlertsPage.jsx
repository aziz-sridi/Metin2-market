import { useEffect, useMemo, useRef, useState } from 'react'

import { useItemSuggestions } from '../hooks/useItemSuggestions.js'
import { listEnchantments, queryListings } from '../lib/api.js'
import { formatYang } from '../lib/format.js'

function normalizeLabel(label, value) {
  const raw = String(label || '').trim()
  const v = Number(value)
  if (!raw) return String(value)
  // Some labels come from server-side templates like "%d%%".
  // If present, substitute the value.
  if (raw.includes('%d')) {
    return raw.replace(/%d/g, String(v)).replace(/%%/g, '%')
  }
  return `${raw} +${v}`
}

function newId() {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID()
  return String(Date.now())
}

function loadSavedAlerts() {
  try {
    const raw = localStorage.getItem('m2_alerts_v1')
    if (!raw) return []
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed
  } catch {
    return []
  }
}

function saveAlerts(alerts) {
  localStorage.setItem('m2_alerts_v1', JSON.stringify(alerts))
}

export default function AlertsPage() {
  const servers = useMemo(
    () => [
      { id: 502, label: 'Europe' },
      { id: 71, label: 'Teutonia' },
    ],
    [],
  )

  // Builder state
  const [name, setName] = useState('')
  const [scope, setScope] = useState('equipment') // any | non_equipment | equipment
  const [selectedServers, setSelectedServers] = useState([502])
  const [maxPriceYang, setMaxPriceYang] = useState('')
  const [minPlus, setMinPlus] = useState('')
  const [maxPlus, setMaxPlus] = useState('')
  const [minQty, setMinQty] = useState('')
  const [bonusMode, setBonusMode] = useState('AND')
  const [bonuses, setBonuses] = useState([{ stat_id: '', stat_query: '', min_value: '0' }])

  // Reference: enchantment labels (stat_id -> label)
  const [enchantOptions, setEnchantOptions] = useState([]) // [{id,label}]

  // Item picker
  const [q, setQ] = useState('')
  const [selectedItems, setSelectedItems] = useState([]) // [{item_vnum,item_name}]

  const {
    results: searchResults,
    loading: loadingSearch,
  } = useItemSuggestions(q, { limit: 30, debounceMs: 250 })

  // Saved alerts
  const [savedAlerts, setSavedAlerts] = useState(() => loadSavedAlerts())

  // Results + monitoring
  const [error, setError] = useState('')
  const [loadingRun, setLoadingRun] = useState(false)
  const [results, setResults] = useState([])

  const [monitoring, setMonitoring] = useState(false)
  const [monitorMatches, setMonitorMatches] = useState([])
  const [lastAlertMessage, setLastAlertMessage] = useState('')

  const lastSeenIsoRef = useRef('')
  const seenKeysRef = useRef(new Set())
  const intervalRef = useRef(null)

  // searchResults/loadingSearch now come from useItemSuggestions

  useEffect(() => {
    let cancelled = false
    async function run() {
      try {
        const data = await listEnchantments()
        const arr = Array.isArray(data) ? data : []
        if (!cancelled) setEnchantOptions(arr)
      } catch {
        if (!cancelled) setEnchantOptions([])
      }
    }
    run()
    return () => {
      cancelled = true
    }
  }, [])

  const enchantLabelById = useMemo(() => {
    const m = new Map()
    for (const opt of enchantOptions || []) {
      m.set(String(opt.id), String(opt.label))
    }
    return m
  }, [enchantOptions])

  // When labels arrive, backfill stat_query for rows that have an id.
  useEffect(() => {
    if (!enchantLabelById.size) return
    setBonuses((prev) =>
      (prev || []).map((b) => {
        if (!b) return b
        const sid = String(b.stat_id || '').trim()
        const qv = String(b.stat_query || '').trim()
        if (!sid || qv) return b
        const label = enchantLabelById.get(sid)
        return label ? { ...b, stat_query: label } : b
      }),
    )
  }, [enchantLabelById])

  useEffect(() => {
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [])

  function toggleServer(id) {
    setSelectedServers((prev) => {
      const exists = prev.includes(id)
      const next = exists ? prev.filter((x) => x !== id) : [...prev, id]
      return next.length ? next : prev
    })
  }

  function addBonusRow() {
    setBonuses((prev) => [...prev, { stat_id: '', stat_query: '', min_value: '0' }])
  }

  function removeBonusRow(idx) {
    setBonuses((prev) => prev.filter((_, i) => i !== idx))
  }

  function updateBonus(idx, key, value) {
    setBonuses((prev) => prev.map((b, i) => (i === idx ? { ...b, [key]: value } : b)))
  }

  function setBonusByOption(idx, opt) {
    if (!opt) return
    updateBonus(idx, 'stat_id', String(opt.id))
    updateBonus(idx, 'stat_query', String(opt.label))
  }

  function addSelectedItem(it) {
    setSelectedItems((prev) => {
      const exists = prev.some((x) => x.item_vnum === it.item_vnum)
      if (exists) return prev
      return [...prev, { item_vnum: it.item_vnum, item_name: it.item_name }]
    })
  }

  function removeSelectedItem(vnum) {
    setSelectedItems((prev) => prev.filter((x) => x.item_vnum !== vnum))
  }

  function buildPayload({ sinceIso = null } = {}) {
    const payload = {
      server_ids: (selectedServers || []).map(Number),
      item_vnums: selectedItems.length ? selectedItems.map((x) => Number(x.item_vnum)) : null,
      item_scope: scope,
      max_price_yang: maxPriceYang.trim() ? Number(maxPriceYang) : null,
      min_enhancement_level: minPlus.trim() ? Number(minPlus) : null,
      max_enhancement_level: maxPlus.trim() ? Number(maxPlus) : null,
      min_quantity: minQty.trim() ? Number(minQty) : null,
      bonus_mode: bonusMode,
      bonuses: (bonuses || [])
        .map((b) => ({
          stat_id: Number(b.stat_id),
          min_value: Number(b.min_value || 0),
        }))
        .filter((b) => Number.isFinite(b.stat_id) && b.stat_id > 0),
      since_iso: sinceIso || null,
      limit: 200,
    }

    if (!payload.item_vnums) delete payload.item_vnums
    if (!payload.max_price_yang) delete payload.max_price_yang
    if (payload.min_enhancement_level == null) delete payload.min_enhancement_level
    if (payload.max_enhancement_level == null) delete payload.max_enhancement_level
    if (payload.min_quantity == null) delete payload.min_quantity
    if (!payload.bonuses || payload.bonuses.length === 0) delete payload.bonuses
    if (!payload.since_iso) delete payload.since_iso

    return payload
  }

  async function runOnce() {
    setError('')
    setLoadingRun(true)
    try {
      const data = await queryListings(buildPayload())
      setResults(data.results || [])
    } catch (e) {
      setError(String(e.message || e))
      setResults([])
    } finally {
      setLoadingRun(false)
    }
  }

  function saveCurrentAlert() {
    const trimmed = name.trim() || 'Untitled alert'
    const alert = {
      id: newId(),
      name: trimmed,
      query: {
        scope,
        selectedServers,
        maxPriceYang,
        minPlus,
        maxPlus,
        minQty,
        bonusMode,
        bonuses,
        selectedItems,
      },
      created_at: new Date().toISOString(),
    }

    const next = [alert, ...(savedAlerts || [])]
    setSavedAlerts(next)
    saveAlerts(next)
    setName('')
  }

  function loadAlert(alert) {
    const q = alert?.query || {}
    setName(alert?.name || '')
    setScope(q.scope || 'equipment')
    setSelectedServers(Array.isArray(q.selectedServers) && q.selectedServers.length ? q.selectedServers : [502])
    setMaxPriceYang(q.maxPriceYang ?? '')
    setMinPlus(q.minPlus ?? '')
    setMaxPlus(q.maxPlus ?? '')
    setMinQty(q.minQty ?? '')
    setBonusMode(q.bonusMode || 'AND')
    const rawBonuses = Array.isArray(q.bonuses) && q.bonuses.length ? q.bonuses : [{ stat_id: '', min_value: '0' }]
    setBonuses(
      rawBonuses.map((b) => ({
        stat_id: String(b?.stat_id ?? ''),
        stat_query: String(b?.stat_query ?? ''),
        min_value: String(b?.min_value ?? '0'),
      })),
    )
    setSelectedItems(Array.isArray(q.selectedItems) ? q.selectedItems : [])
  }

  function deleteAlert(alertId) {
    const next = (savedAlerts || []).filter((a) => a.id !== alertId)
    setSavedAlerts(next)
    saveAlerts(next)
  }

  function startMonitoring() {
    if (intervalRef.current) clearInterval(intervalRef.current)
    intervalRef.current = null

    seenKeysRef.current = new Set()
    lastSeenIsoRef.current = new Date(Date.now() - 60 * 60 * 1000).toISOString() // last 1h
    setMonitorMatches([])
    setLastAlertMessage('')

    setMonitoring(true)

    async function tick() {
      try {
        const data = await queryListings(buildPayload({ sinceIso: lastSeenIsoRef.current }))
        const rows = data.results || []

        // Advance cursor using max timestamp seen.
        let maxIso = lastSeenIsoRef.current
        const newOnes = []
        for (const r of rows) {
          if (typeof r.transaction_timestamp === 'string' && r.transaction_timestamp > maxIso) {
            maxIso = r.transaction_timestamp
          }
          const key = [
            r.server_id,
            r.item_vnum,
            r.transaction_timestamp,
            r.price_yang,
            r.enhancement_level,
            r.seller_name,
          ].join('|')
          if (seenKeysRef.current.has(key)) continue
          seenKeysRef.current.add(key)
          newOnes.push(r)
        }
        lastSeenIsoRef.current = maxIso

        if (newOnes.length) {
          setMonitorMatches((prev) => [...newOnes, ...prev].slice(0, 200))
          setLastAlertMessage(`Matched ${newOnes.length} new listing(s) at ${new Date().toLocaleTimeString()}`)
        }
      } catch {
        // keep monitoring; errors are shown on next manual run
      }
    }

    // Run immediately + every 20s
    tick()
    intervalRef.current = setInterval(tick, 20_000)
  }

  function stopMonitoring() {
    if (intervalRef.current) clearInterval(intervalRef.current)
    intervalRef.current = null
    setMonitoring(false)
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-xl font-semibold">Alerts</h1>
        <p className="text-sm text-slate-600 dark:text-slate-400">
          Build a query with blocks (no SQL). While this page is open, the app can poll for new matching listings.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <section className="rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-950">
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="text-sm font-semibold">Alert builder</div>
              <div className="text-xs text-slate-600 dark:text-slate-400">Define what you want to catch on the market.</div>
            </div>
            <div className="flex gap-2">
              <button
                className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 hover:bg-slate-100 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-200 dark:hover:bg-slate-900/40"
                onClick={saveCurrentAlert}
              >
                Save
              </button>
              {!monitoring ? (
                <button
                  className="rounded-md bg-slate-100 px-3 py-2 text-sm text-slate-900 hover:bg-white"
                  onClick={startMonitoring}
                >
                  Start
                </button>
              ) : (
                <button
                  className="rounded-md bg-slate-100 px-3 py-2 text-sm text-slate-900 hover:bg-white"
                  onClick={stopMonitoring}
                >
                  Stop
                </button>
              )}
            </div>
          </div>

          <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-4">
            <label className="block">
              <div className="text-xs font-medium text-slate-700 dark:text-slate-300">Name</div>
              <input
                className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100 dark:placeholder:text-slate-500"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Triton sword + high STR under 1b"
              />
            </label>

            <label className="block">
              <div className="text-xs font-medium text-slate-700 dark:text-slate-300">Scope</div>
              <select
                className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100"
                value={scope}
                onChange={(e) => setScope(e.target.value)}
              >
                <option value="any">Any</option>
                <option value="non_equipment">Items (non-equipment)</option>
                <option value="equipment">Equipment</option>
              </select>
            </label>

            <div className="md:col-span-2">
              <div className="text-xs font-medium text-slate-700 dark:text-slate-300">Servers</div>
              <div className="mt-2 flex flex-wrap gap-3">
                {servers.map((s) => (
                  <label key={s.id} className="inline-flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={selectedServers.includes(s.id)}
                      onChange={() => toggleServer(s.id)}
                    />
                    <span>{s.label}</span>
                  </label>
                ))}
              </div>
            </div>

            <label className="block">
              <div className="text-xs font-medium text-slate-700 dark:text-slate-300">Max price (total yang)</div>
              <input
                className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100 dark:placeholder:text-slate-500"
                value={maxPriceYang}
                onChange={(e) => setMaxPriceYang(e.target.value)}
                placeholder="e.g. 100000000 (1w)"
                inputMode="numeric"
              />
            </label>

            <label className="block">
              <div className="text-xs font-medium text-slate-700 dark:text-slate-300">Min quantity</div>
              <input
                className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100 dark:placeholder:text-slate-500"
                value={minQty}
                onChange={(e) => setMinQty(e.target.value)}
                placeholder="e.g. 10"
                inputMode="numeric"
              />
            </label>

            {scope === 'equipment' ? (
              <>
                <label className="block">
                  <div className="text-xs font-medium text-slate-700 dark:text-slate-300">Min +</div>
                  <input
                    className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100 dark:placeholder:text-slate-500"
                    value={minPlus}
                    onChange={(e) => setMinPlus(e.target.value)}
                    placeholder="e.g. 9"
                    inputMode="numeric"
                  />
                </label>
                <label className="block">
                  <div className="text-xs font-medium text-slate-700 dark:text-slate-300">Max +</div>
                  <input
                    className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100 dark:placeholder:text-slate-500"
                    value={maxPlus}
                    onChange={(e) => setMaxPlus(e.target.value)}
                    placeholder="e.g. 12"
                    inputMode="numeric"
                  />
                </label>
              </>
            ) : null}
          </div>

          <div className="mt-5 border-t border-slate-200 pt-4 dark:border-slate-800">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-sm font-semibold">Bonuses</div>
                <div className="text-xs text-slate-600 dark:text-slate-400">Pick a bonus name and a minimum value.</div>
              </div>
              <div className="flex items-center gap-2">
                <select
                  className="rounded-md border border-slate-300 bg-white px-2 py-1 text-sm text-slate-900 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100"
                  value={bonusMode}
                  onChange={(e) => setBonusMode(e.target.value)}
                  title="Match mode"
                >
                  <option value="AND">AND</option>
                  <option value="OR">OR</option>
                </select>
                <button
                  className="rounded-md bg-slate-100 px-3 py-2 text-sm text-slate-900 hover:bg-white"
                  onClick={addBonusRow}
                  type="button"
                >
                  Add
                </button>
              </div>
            </div>

            <div className="mt-3 space-y-2">
              {(bonuses || []).map((b, idx) => (
                <div key={idx} className="grid grid-cols-12 gap-2 items-end">
                  <div className="col-span-5 relative">
                    <div className="text-xs font-medium text-slate-700 dark:text-slate-300">Bonus name</div>
                    <input
                      className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100 dark:placeholder:text-slate-500"
                      value={b.stat_query}
                      onChange={(e) => {
                        const v = e.target.value
                        updateBonus(idx, 'stat_query', v)

                        // If user typed an exact numeric id, accept it.
                        const asNum = Number(String(v || '').trim())
                        if (Number.isFinite(asNum) && asNum > 0) {
                          updateBonus(idx, 'stat_id', String(Math.floor(asNum)))
                          const label = enchantLabelById.get(String(Math.floor(asNum)))
                          if (label) updateBonus(idx, 'stat_query', label)
                          return
                        }

                        // Otherwise clear id until a suggestion is chosen.
                        updateBonus(idx, 'stat_id', '')
                      }}
                      placeholder="e.g. Str, Max HP, Critical, ..."
                      autoComplete="off"
                    />

                    {String(b.stat_query || '').trim().length >= 1 && (enchantOptions || []).length ? (
                      <div className="absolute z-20 mt-1 max-h-52 w-full overflow-auto rounded-md border border-slate-300 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-950">
                        {(enchantOptions || [])
                          .filter((opt) => {
                            const qv = String(b.stat_query || '').toLowerCase()
                            const label = String(opt.label || '').toLowerCase()
                            return label.includes(qv)
                          })
                          .slice(0, 12)
                          .map((opt) => (
                            <button
                              key={opt.id}
                              type="button"
                              className="w-full text-left px-3 py-2 text-sm hover:bg-slate-100 dark:hover:bg-slate-900/40"
                              onMouseDown={(e) => {
                                // onMouseDown so blur doesn't hide list before click.
                                e.preventDefault()
                                setBonusByOption(idx, opt)
                              }}
                            >
                              <div className="font-medium text-slate-900 dark:text-slate-100">{opt.label}</div>
                              <div className="text-xs text-slate-600 dark:text-slate-400">id {opt.id}</div>
                            </button>
                          ))}
                      </div>
                    ) : null}
                  </div>

                  <label className="col-span-5">
                    <div className="text-xs font-medium text-slate-700 dark:text-slate-300">min value</div>
                    <input
                      className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100 dark:placeholder:text-slate-500"
                      value={b.min_value}
                      onChange={(e) => updateBonus(idx, 'min_value', e.target.value)}
                      placeholder="e.g. 10"
                      inputMode="numeric"
                    />
                  </label>
                  <div className="col-span-2">
                    <button
                      className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 hover:bg-slate-100 disabled:opacity-50 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-200 dark:hover:bg-slate-900/40"
                      onClick={() => removeBonusRow(idx)}
                      disabled={(bonuses || []).length <= 1}
                      type="button"
                      title="Remove"
                    >
                      Remove
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="mt-5 border-t border-slate-200 pt-4 dark:border-slate-800">
            <div className="text-sm font-semibold">Limit to specific items (optional)</div>
            <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-3 items-start">
              <div>
                <div className="text-xs font-medium text-slate-700 dark:text-slate-300">Search items</div>
                <input
                  className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100 dark:placeholder:text-slate-500"
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                  placeholder="Type to search..."
                />
                {loadingSearch ? <div className="mt-2 text-xs text-slate-600 dark:text-slate-400">Searching…</div> : null}
                <div className="mt-2 max-h-52 overflow-auto rounded-md border border-slate-200 dark:border-slate-800">
                  {(searchResults || []).map((it) => (
                    <button
                      key={it.item_vnum}
                      className="w-full text-left px-3 py-2 text-sm hover:bg-slate-100 dark:hover:bg-slate-900/40"
                      onClick={() => addSelectedItem(it)}
                      type="button"
                    >
                      <div className="font-medium text-slate-900 dark:text-slate-100">{it.item_name}</div>
                      <div className="text-xs text-slate-600 dark:text-slate-400">vnum {it.item_vnum} · {it.item_type}</div>
                    </button>
                  ))}
                  {!q.trim() ? (
                    <div className="px-3 py-2 text-xs text-slate-600 dark:text-slate-400">Start typing to search.</div>
                  ) : null}
                  {q.trim() && !loadingSearch && (searchResults || []).length === 0 ? (
                    <div className="px-3 py-2 text-xs text-slate-600 dark:text-slate-400">No matches.</div>
                  ) : null}
                </div>
              </div>

              <div>
                <div className="text-xs font-medium text-slate-700 dark:text-slate-300">Selected items</div>
                <div className="mt-2 space-y-2">
                  {selectedItems.length === 0 ? (
                    <div className="text-sm text-slate-600 dark:text-slate-400">No item restriction.</div>
                  ) : null}
                  {selectedItems.map((it) => (
                    <div key={it.item_vnum} className="flex items-center justify-between gap-2 rounded-md border border-slate-200 px-3 py-2 dark:border-slate-800">
                      <div className="min-w-0">
                        <div className="text-sm font-medium truncate">{it.item_name}</div>
                        <div className="text-xs text-slate-600 dark:text-slate-400">{it.item_vnum}</div>
                      </div>
                      <button
                        className="rounded-md border border-slate-300 bg-white px-2 py-1 text-xs text-slate-900 hover:bg-slate-100 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-200 dark:hover:bg-slate-900/40"
                        onClick={() => removeSelectedItem(it.item_vnum)}
                        type="button"
                      >
                        Remove
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>

          <div className="mt-5 flex items-center gap-2">
            <button
              className="rounded-md bg-slate-100 px-3 py-2 text-sm text-slate-900 hover:bg-white disabled:opacity-50"
              onClick={runOnce}
              disabled={loadingRun}
            >
              {loadingRun ? 'Running…' : 'Test query'}
            </button>
            {error ? <div className="text-sm text-red-300">{error}</div> : null}
            {monitoring && lastAlertMessage ? (
              <div className="ml-auto text-sm text-slate-600 dark:text-slate-400">{lastAlertMessage}</div>
            ) : null}
          </div>
        </section>

        <section className="rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-950">
          <div className="text-sm font-semibold">Matches</div>
          <div className="text-xs text-slate-600 dark:text-slate-400">
            {monitoring ? 'Live matches (newest first)' : 'Last test query results'}
          </div>

          <div className="mt-3 overflow-auto rounded-md border border-slate-200 dark:border-slate-800">
            <table className="min-w-full text-sm">
              <thead className="bg-slate-100 text-slate-700 dark:bg-slate-900/40 dark:text-slate-200">
                <tr>
                  <th className="px-3 py-2 text-left font-medium">Time</th>
                  <th className="px-3 py-2 text-left font-medium">Server</th>
                  <th className="px-3 py-2 text-left font-medium">Item</th>
                  <th className="px-3 py-2 text-left font-medium">Price</th>
                  <th className="px-3 py-2 text-left font-medium">+</th>
                  <th className="px-3 py-2 text-left font-medium">Bonuses</th>
                </tr>
              </thead>
              <tbody>
                {(monitoring ? monitorMatches : results).map((r, idx) => (
                  <tr key={idx} className="border-t border-slate-200 dark:border-slate-800">
                    <td className="px-3 py-2 whitespace-nowrap">{String(r.transaction_timestamp).replace('T', ' ').slice(0, 19)}</td>
                    <td className="px-3 py-2 whitespace-nowrap">{r.server_id === 71 ? 'Teu' : r.server_id === 502 ? 'EU' : String(r.server_id || '')}</td>
                    <td className="px-3 py-2">
                      <div className="font-medium">{r.item_name}</div>
                      <div className="text-xs text-slate-600 dark:text-slate-400">{r.item_vnum}</div>
                    </td>
                    <td className="px-3 py-2 whitespace-nowrap">{formatYang(r.price_yang)}</td>
                    <td className="px-3 py-2 whitespace-nowrap">{r.enhancement_level ?? 0}</td>
                    <td className="px-3 py-2">
                      <div className="flex flex-wrap gap-1">
                        {(r.bonuses || []).slice(0, 6).map((b, i) => (
                          <span key={i} className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-700 dark:bg-slate-900/40 dark:text-slate-200">
                            {normalizeLabel(enchantLabelById.get(String(b.stat_id)) || `Stat ${b.stat_id}`, b.value)}
                          </span>
                        ))}
                        {(r.bonuses || []).length > 6 ? (
                          <span className="text-xs text-slate-600 dark:text-slate-400">+{(r.bonuses || []).length - 6}</span>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                ))}
                {(monitoring ? monitorMatches : results).length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-3 py-8 text-center text-sm text-slate-600 dark:text-slate-400">
                      No matches.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </section>
      </div>

      <section className="rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-950">
        <div className="text-sm font-semibold">Saved alerts</div>
        <div className="text-xs text-slate-600 dark:text-slate-400">Stored locally in your browser (localStorage).</div>

        <div className="mt-3 overflow-auto rounded-md border border-slate-200 dark:border-slate-800">
          <table className="min-w-full text-sm">
            <thead className="bg-slate-100 text-slate-700 dark:bg-slate-900/40 dark:text-slate-200">
              <tr>
                <th className="px-3 py-2 text-left font-medium">Name</th>
                <th className="px-3 py-2 text-left font-medium">Created</th>
                <th className="px-3 py-2 text-right font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {(savedAlerts || []).map((a) => (
                <tr key={a.id} className="border-t border-slate-200 dark:border-slate-800">
                  <td className="px-3 py-2">
                    <div className="font-medium">{a.name}</div>
                    <div className="text-xs text-slate-600 dark:text-slate-400">{a.id}</div>
                  </td>
                  <td className="px-3 py-2 text-slate-600 whitespace-nowrap dark:text-slate-400">{String(a.created_at || '').slice(0, 19).replace('T', ' ')}</td>
                  <td className="px-3 py-2">
                    <div className="flex justify-end gap-2">
                      <button
                        className="rounded-md border border-slate-300 bg-white px-3 py-2 text-xs text-slate-900 hover:bg-slate-100 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-200 dark:hover:bg-slate-900/40"
                        onClick={() => loadAlert(a)}
                        type="button"
                      >
                        Load
                      </button>
                      <button
                        className="rounded-md border border-slate-300 bg-white px-3 py-2 text-xs text-slate-900 hover:bg-slate-100 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-200 dark:hover:bg-slate-900/40"
                        onClick={() => deleteAlert(a.id)}
                        type="button"
                      >
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {(savedAlerts || []).length === 0 ? (
                <tr>
                  <td colSpan={3} className="px-3 py-8 text-center text-sm text-slate-600 dark:text-slate-400">
                    No saved alerts yet.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}
