import { useMemo, useState } from 'react'
import { useItemSuggestions } from '../hooks/useItemSuggestions.js'

export default function ItemSearch({ onAddItem }) {
  const [q, setQ] = useState('')
  const [activeIndex, setActiveIndex] = useState(-1)

  const { results, loading, error } = useItemSuggestions(q, { limit: 30, debounceMs: 250 })
  const suggestions = useMemo(() => results || [], [results])

  function add(item) {
    if (!item) return
    onAddItem?.({ item_vnum: item.item_vnum, item_name: item.item_name })
    setQ('')
  }

  return (
    <div className="item-search-container">
      <div className="search-header">
        <h2>Add an item</h2>
        <p className="muted">Search the item catalog and add it to your watchlist.</p>
      </div>

      <div className="search-form" role="search">
        <input
          type="text"
          value={q}
          onChange={(e) => {
            setQ(e.target.value)
            setActiveIndex(-1)
          }}
          onKeyDown={(e) => {
            if (e.key === 'ArrowDown') {
              e.preventDefault()
              setActiveIndex((i) => Math.min((suggestions?.length || 0) - 1, i + 1))
            } else if (e.key === 'ArrowUp') {
              e.preventDefault()
              setActiveIndex((i) => Math.max(-1, i - 1))
            } else if (e.key === 'Enter') {
              if (activeIndex >= 0 && suggestions?.[activeIndex]) {
                e.preventDefault()
                add(suggestions[activeIndex])
              }
            }
          }}
          placeholder="Type to search items…"
          className="search-input"
          aria-label="Item search"
          autoComplete="off"
        />
        <button
          type="button"
          className="search-button"
          disabled={!suggestions?.length}
          onClick={() => add(suggestions?.[0])}
          title="Add first match"
        >
          Add
        </button>
      </div>

      {error ? <div className="mt-2 text-sm error">{error}</div> : null}

      {q.trim() ? (
        <div className="search-results">
          <div className="muted" style={{ marginBottom: 8 }}>
            {loading ? 'Searching…' : suggestions.length ? 'Suggestions' : 'No matches'}
          </div>
          <div className="results-grid">
            {suggestions.map((item, idx) => (
              <button
                type="button"
                key={item.item_vnum}
                className="result-item"
                onMouseEnter={() => setActiveIndex(idx)}
                onClick={() => add(item)}
                data-active={activeIndex === idx ? 'true' : 'false'}
              >
                <div className="result-name">{item.item_name}</div>
                <div className="result-vnum">#{item.item_vnum}</div>
                <div className="result-type">{item.item_type}</div>
              </button>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  )
}
