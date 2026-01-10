import { useEffect, useState } from 'react'
import { formatYang } from '../lib/format.js'

export default function DashboardCard({ itemVnum, itemName, removable = false, onRemove }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [chart, setChart] = useState(null)

  useEffect(() => {
    fetchItemData()
    fetchChart()
  }, [itemVnum])

  const fetchItemData = async () => {
    try {
      setLoading(true)
      const response = await fetch(`/api/analytics/item-min-price/${itemVnum}`)
      const result = await response.json()
      setData(result)
    } catch (error) {
      console.error('Error fetching item data:', error)
    } finally {
      setLoading(false)
    }
  }

  const fetchChart = async () => {
    try {
      const response = await fetch(`/api/analytics/dashboard-chart/${itemVnum}`)
      const result = await response.json()
      setChart(result.chart_data)
    } catch (error) {
      console.error('Error fetching chart:', error)
    }
  }

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

  if (!data || !data.latest_min_price) {
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
              <span className="history-date">{entry.date}</span>
              <span className="history-price">{formatPrice(entry.min_price)}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
