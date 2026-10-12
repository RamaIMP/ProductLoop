export function serviceSearchUrl(location = '', brand = '') {
  const query = `${brand.trim()} electric shaver service centre ${location.trim() ? `near ${location.trim()}` : 'near me'}`.trim()
  return `https://www.google.com/maps/search/?${new URLSearchParams({ api: '1', query })}`
}

export function coordinatesForSearch(latitude, longitude) {
  if (!Number.isFinite(latitude) || !Number.isFinite(longitude) || Math.abs(latitude) > 90 || Math.abs(longitude) > 180) throw new Error('Invalid location')
  return `${latitude.toFixed(4)},${longitude.toFixed(4)}`
}
