import { useEffect, useState } from 'react'
import DashboardCard from '../components/DashboardCard'
import ItemSearch from '../components/ItemSearch'

const DEFAULT_TRACKED = [
  { item_vnum: 80017, item_name: 'Voucher' },
  { item_vnum: 30618, item_name: 'Moonstone' },
]

function loadTrackedFromStorage() {
  try {
    const raw = localStorage.getItem('homeTrackedItems')
    if (raw === null) return DEFAULT_TRACKED
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return DEFAULT_TRACKED

    // Allow empty saved list.
    const cleaned = parsed
      .filter((x) => x && Number.isFinite(Number(x.item_vnum ?? x.itemVnum)))
      .map((x) => ({
        item_vnum: Number(x.item_vnum ?? x.itemVnum),
        item_name: String(x.item_name ?? x.itemName ?? ''),
      }))
    return cleaned
  } catch {
    return DEFAULT_TRACKED
  }
}

export default function HomePage() {
  const [tracked, setTracked] = useState(() => loadTrackedFromStorage())

  useEffect(() => {
    try {
      localStorage.setItem('homeTrackedItems', JSON.stringify(tracked))
    } catch {
      // ignore
    }
  }, [tracked])

  function addTracked(item) {
    setTracked((prev) => {
      if (!item?.item_vnum) return prev
      const exists = prev.some((p) => p.item_vnum === item.item_vnum)
      if (exists) return prev
      return [...prev, { item_vnum: item.item_vnum, item_name: item.item_name }]
    })
  }

  function removeTracked(vnum) {
    setTracked((prev) => prev.filter((p) => p.item_vnum !== vnum))
  }

  function clearTracked() {
    setTracked([])
  }

  function resetTracked() {
    setTracked(DEFAULT_TRACKED)
  }

  return (
    <div className="homepage-dashboard">
      <div className="dashboard-header">
        <h1>Market Dashboard</h1>
        <p className="dashboard-subtitle">
          Real-time tracking of key items
        </p>
      </div>

      <div className="dashboard-grid">
        {tracked.map((t) => (
          <DashboardCard
            key={t.item_vnum}
            itemVnum={t.item_vnum}
            itemName={t.item_name}
            removable
            onRemove={removeTracked}
          />
        ))}
      </div>

      <div className="search-section">
        <ItemSearch onAddItem={addTracked} />

        <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 10, flexWrap: 'wrap' }}>
          <button
            type="button"
            className="search-button"
            onClick={resetTracked}
            title="Restore default tracked items"
          >
            Reset
          </button>
          <button
            type="button"
            className="search-button"
            onClick={clearTracked}
            disabled={tracked.length === 0}
            title="Remove all tracked items"
          >
            Clear
          </button>
          <span className="muted" style={{ fontSize: 12 }}>
            Saved automatically
          </span>
        </div>
      </div>
    </div>
  )
}
