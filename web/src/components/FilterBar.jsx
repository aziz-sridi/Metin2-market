import { useMemo, useState } from 'react'

export function FilterBar({
  serverId,
  servers,
  onServerIdChange,

  category,
  categories,
  onCategoryChange,

  enchantment,
  enchantments,
  onEnchantmentChange,

  selectedEnchantments,
  onSelectedEnchantmentsChange,

  enchantMode,
  onEnchantModeChange,

  search,
  onSearchChange,
}) {
  const hasMultiEnchant =
    Array.isArray(selectedEnchantments) && typeof onSelectedEnchantmentsChange === 'function'

  const enchantLabelByValue = useMemo(() => {
    const map = new Map()
    for (const en of enchantments ?? []) {
      map.set(String(en.value), en.label)
    }
    return map
  }, [enchantments]);

  const [pickerEnchantId, setPickerEnchantId] = useState('')
  const [pickerMinValue, setPickerMinValue] = useState('0')

  function addSelectedEnchantment() {
    const id = String(pickerEnchantId || '').trim()
    if (!id) return;

    const minValueNum = Math.max(0, Number(pickerMinValue || 0) || 0)

    const prev = Array.isArray(selectedEnchantments) ? selectedEnchantments : []
    const exists = prev.some((e) => String(e.id) === id)

    const next = exists
      ? prev.map((e) => (String(e.id) === id ? { ...e, minValue: minValueNum } : e))
      : [...prev, { id, minValue: minValueNum }];

    onSelectedEnchantmentsChange(next)
    setPickerEnchantId('')
    setPickerMinValue('0')
  }

  function removeSelectedEnchantment(id) {
    const prev = Array.isArray(selectedEnchantments) ? selectedEnchantments : []
    onSelectedEnchantmentsChange(prev.filter((e) => String(e.id) !== String(id)))
  }

  function updateSelectedMinValue(id, raw) {
    const prev = Array.isArray(selectedEnchantments) ? selectedEnchantments : []
    const minValueNum = Math.max(0, Number(raw || 0) || 0)
    onSelectedEnchantmentsChange(
      prev.map((e) => (String(e.id) === String(id) ? { ...e, minValue: minValueNum } : e)),
    )
  }

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-950">
      <div className="text-sm font-semibold text-slate-900 dark:text-slate-100">Filters</div>

      <div className="mt-3 grid grid-cols-1 md:grid-cols-12 gap-3 items-end">
        <label className="md:col-span-3">
          <div className="text-xs font-medium text-slate-700 mb-1 dark:text-slate-300">Server</div>
          <select
            className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100"
            value={serverId ?? ''}
            onChange={(e) => onServerIdChange?.(e.target.value)}
          >
            {(servers ?? []).map((s) => (
              <option key={String(s.value)} value={String(s.value)}>
                {s.label}
              </option>
            ))}
          </select>
        </label>

        <label className="md:col-span-3">
          <div className="text-xs font-medium text-slate-700 mb-1 dark:text-slate-300">Category</div>
          <select
            className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100"
            value={category ?? ''}
            onChange={(e) => onCategoryChange?.(e.target.value)}
          >
            <option value="">All Categories</option>
            {(categories ?? []).map((c) => (
              <option key={String(c.value)} value={String(c.value)}>
                {c.label}
              </option>
            ))}
          </select>
        </label>

        <label className="md:col-span-6">
          <div className="text-xs font-medium text-slate-700 mb-1 dark:text-slate-300">Item search</div>
          <input
            type="text"
            className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100 dark:placeholder:text-slate-500"
            placeholder="Search item…"
            value={search ?? ''}
            onChange={(e) => onSearchChange?.(e.target.value)}
          />
        </label>

        {hasMultiEnchant ? (
          <>
            <div className="md:col-span-6">
              <div className="text-xs font-medium text-slate-700 mb-1 dark:text-slate-300">Add enchantment filter</div>
              <div className="flex gap-2">
                <select
                  className="flex-1 rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100"
                  value={pickerEnchantId}
                  onChange={(e) => setPickerEnchantId(e.target.value)}
                >
                  <option value="">Select enchantment…</option>
                  {(enchantments ?? []).map((en) => (
                    <option key={String(en.value)} value={String(en.value)}>
                      {en.label}
                    </option>
                  ))}
                </select>

                <input
                  className="w-28 rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100"
                  type="number"
                  min={0}
                  step={1}
                  value={pickerMinValue}
                  onChange={(e) => setPickerMinValue(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') addSelectedEnchantment()
                  }}
                  aria-label="Minimum value"
                  title="Minimum value"
                />

                <button
                  type="button"
                  className="rounded-md bg-slate-100 px-3 py-2 text-sm text-slate-900 hover:bg-white disabled:opacity-50"
                  onClick={addSelectedEnchantment}
                  disabled={!pickerEnchantId}
                  title="Add"
                >
                  Add
                </button>
              </div>
            </div>

            <label className="md:col-span-2">
              <div className="text-xs font-medium text-slate-700 mb-1 dark:text-slate-300">Match mode</div>
              <select
                className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100"
                value={(enchantMode || 'AND').toUpperCase()}
                onChange={(e) => onEnchantModeChange?.(e.target.value)}
                title="Match mode"
                aria-label="Enchantment match mode"
              >
                <option value="AND">AND</option>
                <option value="OR">OR</option>
              </select>
            </label>
          </>
        ) : (
          <label className="md:col-span-6">
            <div className="text-xs font-medium text-slate-700 mb-1 dark:text-slate-300">Enchantment</div>
            <select
              className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100"
              value={enchantment ?? ''}
              onChange={(e) => onEnchantmentChange?.(e.target.value)}
            >
              <option value="">All Enchantments</option>
              {(enchantments ?? []).map((en) => (
                <option key={String(en.value)} value={String(en.value)}>
                  {en.label}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>

      {hasMultiEnchant && (selectedEnchantments?.length ?? 0) > 0 ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {(selectedEnchantments ?? []).map((sel) => {
            const id = String(sel.id)
            const label = enchantLabelByValue.get(id) || id
            return (
              <div
                key={id}
                className="inline-flex items-center gap-2 rounded-md border border-slate-300 bg-slate-50 px-2 py-1 dark:border-slate-800 dark:bg-slate-900/40"
              >
                <div className="text-sm text-slate-900 max-w-[18rem] truncate dark:text-slate-100" title={label}>
                  {label}
                </div>
                <div className="text-xs text-slate-600 dark:text-slate-400">≥</div>
                <input
                  className="w-20 rounded-md border border-slate-300 bg-white p-1 text-sm text-slate-900 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100"
                  type="number"
                  min={0}
                  step={1}
                  value={String(sel.minValue ?? 0)}
                  onChange={(e) => updateSelectedMinValue(id, e.target.value)}
                />
                <button
                  type="button"
                  className="rounded-md border border-slate-300 bg-white px-2 py-1 text-xs text-slate-900 hover:bg-slate-100 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-200 dark:hover:bg-slate-900/40"
                  onClick={() => removeSelectedEnchantment(id)}
                  title="Remove"
                >
                  x
                </button>
              </div>
            )
          })}
        </div>
      ) : null}
    </div>
  )
}
