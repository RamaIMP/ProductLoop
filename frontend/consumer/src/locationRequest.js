export function locationErrorMessage(error) {
  if (error?.code === 1) return 'Location permission is blocked. Allow location in your browser’s site settings and your device settings, then retry—or enter your city/postcode below.'
  if (error?.code === 3) return 'Location detection timed out. Please retry or enter your city/postcode below.'
  return 'Your device could not provide a location. Please enter your city/postcode below.'
}

export function requestLocation(geolocation, timeoutMs = 10000) {
  return new Promise((resolve, reject) => {
    if (!geolocation) { reject(new Error('Location is unavailable in this browser. Enter your city/postcode below.')); return }
    // Also bound the permission-prompt wait, which can outlast the API timeout.
    const timer = setTimeout(() => reject({ code: 3 }), timeoutMs)
    const finish = callback => value => { clearTimeout(timer); callback(value) }
    try {
      geolocation.getCurrentPosition(finish(resolve), finish(reject), {
        enableHighAccuracy: false, timeout: timeoutMs, maximumAge: 300000,
      })
    } catch (error) { clearTimeout(timer); reject(error) }
  })
}
