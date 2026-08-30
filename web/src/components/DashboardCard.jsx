import { useEffect, useState } from 'react'
import { formatYang } from '../lib/format.js'

export default function DashboardCard({ itemVnum, itemName, removable = false, onRemove }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [chart, setChart] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    const controller = new AbortController()

    async function fetchItemData() {
      setLoading(true)
      setError('')
      try {
        const response = await fetch(`/api/analytics/item-min-price/${itemVnum}`, {
          signal: controller.signal,
        })
        if (!response.ok) throw new Error(`Request failed with status ${response.status}`)
        setData(await response.json())
      } catch (requestError) {
        if (requestError.name !== 'AbortError') {
          setData(null)
          setError(requestError.message || 'Unable to load market data')
        }
      } finally {
        if (!controller.signal.aborted) setLoading(false)
      }
    }

    async function fetchChart() {
      try {
        const response = await fetch(`/api/analytics/dashboard-chart/${itemVnum}`, {
          signal: controller.signal,
        })
        if (!response.ok) return
        const result = await response.json()
        setChart(result.chart_data || null)
      } catch (requestError) {
        if (requestError.name !== 'AbortError') setChart(null)
      }
    }

    fetchItemData()
    fetchChart()

    return () => controller.abort()
  }, [itemVnum])

  const formatPrice = (price) => {
    if (price === null || price === undefined) return 'N/A'
    return formatYang(price) || 'N/A'
  }

  if (loading) {
    return (
      <div className="dashboard-card loading">
        <p>Loading {itemName}...</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="dashboard-card no-data" role="alert">
        <h3>{itemName}</h3>
        <p>{error}</p>
      </div>
    )
  }

  const formatSyncDate = (value) => {
    const date = new Date(String(value).replace(' ', 'T'))
    if (Number.isNaN(date.getTime())) return String(value)
    return new Intl.DateTimeFormat('en', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    }).format(date)
  }

  if (!data || data.latest_min_price == null) {
    return (
      <div className="dashboard-card no-data">
        <h3>{itemName}</h3>
        <p>No market data available</p>
      </div>
    )
  }

  const displayName = data?.item_name || itemName

  return (
    <div className="dashboard-card">
      <div className="card-header">
        <h3>{displayName}</h3>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {removable ? (
            <button
              type="button"
              className="vnum-badge"
              onClick={() => onRemove?.(data.item_vnum)}
              title="Remove"
            >
              remove
            </button>
          ) : null}
          <span className="vnum-badge">#{data.item_vnum}</span>
        </div>
      </div>

      <div className="price-display">
        <div className="price-main">
          <span className="price-label">Lowest Price</span>
          <span className="price-value">{formatPrice(data.latest_min_price)}</span>
        </div>

        <div className="price-stats">
          <div className="stat">
            <span className="stat-label">Average</span>
            <span className="stat-value">{formatPrice(data.avg_price)}</span>
          </div>
          <div className="stat">
            <span className="stat-label">Max</span>
            <span className="stat-value">{formatPrice(data.max_price)}</span>
          </div>
          <div className="stat">
            <span className="stat-label">Transactions</span>
            <span className="stat-value">{data.transaction_count}</span>
          </div>
        </div>
      </div>

      {chart && (
        <div className="chart-container">
          <img src={chart} alt={`${displayName} price chart`} className="price-chart" />
        </div>
      )}

      <div className="price-history">
        <h4>Recent History</h4>
        <div className="history-list">
          {data.price_history.slice(0, 5).map((entry, idx) => (
            <div key={idx} className="history-item">
              <span className="history-date">{formatSyncDate(entry.date)}</span>
              <span className="history-price">{formatPrice(entry.min_price)}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
