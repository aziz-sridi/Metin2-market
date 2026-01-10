import { useEffect, useState } from 'react'

import { searchItems } from '../lib/api.js'

export function useItemSuggestions(query, { limit = 30, debounceMs = 250 } = {}) {
  const [results, setResults] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false

    async function run() {
      setError('')
      setLoading(true)
      try {
        const data = await searchItems(query, limit)
        if (!cancelled) setResults(data.results || [])
      } catch (e) {
        if (!cancelled) {
          setResults([])
          setError(String(e?.message || e))
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    if (!String(query || '').trim()) {
      setResults([])
      setLoading(false)
      setError('')
      return
    }

    const t = setTimeout(run, debounceMs)
    return () => {
      cancelled = true
      clearTimeout(t)
    }
  }, [query, limit, debounceMs])

  return { results, loading, error }
}
