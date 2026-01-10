async function apiGet(path) {
  const res = await fetch(path, {
    headers: {
      Accept: 'application/json',
    },
  })

  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`API ${res.status}: ${text || res.statusText}`)
  }
  return await res.json()
}

async function apiPost(path, body) {
  const res = await fetch(path, {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body ?? {}),
  })
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`API ${res.status}: ${text || res.statusText}`)
  }
  return res.json()
}

export async function searchItems(q, limit = 30) {
  const qs = new URLSearchParams({ q: q || '', limit: String(limit) })
  return await apiGet(`/api/dashboard/search?${qs.toString()}`)
}

export async function getNonEquipmentHistory(itemVnums, days = 60, opts = {}) {
  const { serverId = null, categoryId = null, enchantments = [], enchantMode = 'AND' } = opts || {}

  const qs = new URLSearchParams({ item_vnums: itemVnums.join(','), days: String(days) })
  if (serverId != null && String(serverId).trim() !== '') qs.set('server_id', String(serverId))
  if (categoryId != null && String(categoryId).trim() !== '') qs.set('category_id', String(categoryId))
  if (Array.isArray(enchantments) && enchantments.length > 0) {
    const encStr = enchantments
      .filter((e) => e && e.id != null)
      .map((e) => `${Number(e.id)}:${Number(e.minValue ?? 0)}`)
      .join(',')
    if (encStr) qs.set('enchantments', encStr)
  }
  if (enchantMode) qs.set('enchant_mode', String(enchantMode).toUpperCase())
  return await apiGet(`/api/dashboard/non-equipment/history?${qs.toString()}`)
}

export async function getEquipmentBonusImpact(itemVnum, days = 30, topN = 12, examplesPerBonus = 3) {
  const qs = new URLSearchParams({
    item_vnum: String(itemVnum),
    days: String(days),
    top_n: String(topN),
    examples_per_bonus: String(examplesPerBonus),
  })
  return await apiGet(`/api/dashboard/equipment/bonus-impact?${qs.toString()}`)
}

export async function estimateEquipment(itemVnum, bonusesText, days = 30) {
  const qs = new URLSearchParams({
    item_vnum: String(itemVnum),
    bonuses: bonusesText || '',
    days: String(days),
  })
  return await apiGet(`/api/dashboard/equipment/estimate?${qs.toString()}`)
}

export async function getDeals(limit = 30) {
  const qs = new URLSearchParams({ limit: String(limit) })
  return await apiGet(`/api/dashboard/deals?${qs.toString()}`)
}

export async function listCategories() {
  return await apiGet('/api/reference/categories')
}

export async function listEnchantments() {
  return await apiGet('/api/reference/enchantments')
}

export async function estimateItemPrice({
  itemVnum,
  serverId = null,
  categoryId = null,
  days = 30,
  enchantments = [],
  enchantMode = 'AND',
}) {
  return apiPost('/api/dashboard/item/estimate', {
    item_vnum: itemVnum,
    server_id: serverId,
    category_id: categoryId,
    days,
    enchant_mode: String(enchantMode || 'AND').toUpperCase(),
    enchantments: (enchantments || []).map((e) => ({
      stat_id: Number(e.id),
      min_value: Number(e.minValue ?? 0),
    })),
  })
}

// New APIs for the redesigned UX

export async function getKpis({ days = 1, serverId = null } = {}) {
  const qs = new URLSearchParams({ days: String(days) })
  if (serverId != null && String(serverId).trim() !== '') qs.set('server_id', String(serverId))
  return await apiGet(`/api/dashboard/kpis?${qs.toString()}`)
}

export async function queryListings(payload) {
  return await apiPost('/api/dashboard/query/listings', payload)
}

export async function getBonusPriceDistribution({
  statId,
  minValue = 0,
  days = 30,
  serverId = null,
  equipmentOnly = true,
  bins = 20,
} = {}) {
  const qs = new URLSearchParams({
    stat_id: String(statId),
    min_value: String(minValue),
    days: String(days),
    equipment_only: String(Boolean(equipmentOnly)),
    bins: String(bins),
  })
  if (serverId != null && String(serverId).trim() !== '') qs.set('server_id', String(serverId))
  return await apiGet(`/api/dashboard/analytics/bonus-price-distribution?${qs.toString()}`)
}
