export function profileDevice(units) {
  const matching = units.filter(unit => (unit.product_model || '').trim().toUpperCase() === 'X500')
  return matching.length === 1 ? matching[0] : null
}

export function profileDate(value, dateOnly = false) {
  if (!value) return 'Not recorded'
  const date = new Date(dateOnly ? value + 'T00:00:00' : value)
  return Number.isNaN(date.getTime()) ? 'Not recorded' : date.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })
}

export function profileFields(unit) {
  return [
    ['Product', 'X500 Electric Shaver'],
    ['Serial number', unit?.serial_number || 'Not recorded'],
    ['Purchase date', profileDate(unit?.purchase_date, true)],
    ['Registration date', profileDate(unit?.registered_at)],
    ['Batch', unit?.batch_id || 'Not recorded'],
    ['Registration region', unit?.region || 'Not recorded'],
    ['Warranty status', unit?.warranty_status || 'Not verified'],
  ]
}
