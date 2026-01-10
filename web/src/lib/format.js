const WON_TO_YANG = 100_000_000

function formatInt(n) {
  return Number(n).toLocaleString('en-US')
}

export function formatYang(n) {
  // Prices are stored as total yang. Display as "<won>w + <yang>y".
  // Conversion rule: 1 won = 100,000,000 yang.
  if (n === null || n === undefined) return ''
  const x = Number(n)
  if (!Number.isFinite(x)) return ''

  const sign = x < 0 ? '-' : ''
  const abs = Math.floor(Math.abs(x))

  const won = Math.floor(abs / WON_TO_YANG)
  const yang = abs % WON_TO_YANG

  if (won <= 0) return `${sign}${formatInt(yang)}y`
  if (yang <= 0) return `${sign}${formatInt(won)}w`
  return `${sign}${formatInt(won)}w + ${formatInt(yang)}y`
}

export function formatPct(n) {
  if (n === null || n === undefined) return ''
  const x = Number(n)
  if (!Number.isFinite(x)) return ''
  return `${x.toFixed(2)}%`
}
