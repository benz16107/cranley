// Where the sun stands, from NOAA's solar position equations (the ones behind gml.noaa.gov/grad/solcalc). No DOM
// and no three.js, so it runs under `node --test`. Good to a few hundredths of a degree for dates near the present.
const RAD = Math.PI / 180
const sin = (d: number) => Math.sin(d * RAD), cos = (d: number) => Math.cos(d * RAD), tan = (d: number) => Math.tan(d * RAD)
const mod = (a: number, n: number) => ((a % n) + n) % n

/** The sun's declination (degrees) and the equation of time (minutes) at an instant. */
function orbit(t: Date) {
  const T = (t.getTime() / 86400000 + 2440587.5 - 2451545) / 36525 // Julian centuries from J2000
  const L0 = mod(280.46646 + T * (36000.76983 + 0.0003032 * T), 360)
  const M = 357.52911 + T * (35999.05029 - 0.0001537 * T)
  const e = 0.016708634 - T * (0.000042037 + 0.0000001267 * T)
  const C = sin(M) * (1.914602 - T * (0.004817 + 0.000014 * T)) + sin(2 * M) * (0.019993 - 0.000101 * T) + sin(3 * M) * 0.000289
  const omega = 125.04 - 1934.136 * T
  const lambda = L0 + C - 0.00569 - 0.00478 * sin(omega)
  const eps = 23 + (26 + (21.448 - T * (46.815 + T * (0.00059 - T * 0.001813))) / 60) / 60 + 0.00256 * cos(omega)
  const y = tan(eps / 2) ** 2
  const eot = (4 / RAD) * (y * sin(2 * L0) - 2 * e * sin(M) + 4 * e * y * sin(M) * cos(2 * L0) - 0.5 * y * y * sin(4 * L0) - 1.25 * e * e * sin(2 * M))
  return { decl: Math.asin(sin(eps) * sin(lambda)) / RAD, eot }
}

/** Degrees. `azimuth` is the compass direction to the sun (0 north, clockwise); `altitude` is above the horizon,
    negative at night. No refraction: at the horizon the real sun sits about half a degree higher. */
export function sunPosition(t: Date, lat: number, lon: number): { azimuth: number; altitude: number } {
  const { decl, eot } = orbit(t)
  const minutes = t.getUTCHours() * 60 + t.getUTCMinutes() + t.getUTCSeconds() / 60
  const ha = mod(minutes + eot + 4 * lon, 1440) / 4 - 180 // hour angle: 0 at solar noon, positive in the afternoon
  const cz = Math.min(1, Math.max(-1, sin(lat) * sin(decl) + cos(lat) * cos(decl) * cos(ha)))
  const zen = Math.acos(cz) / RAD
  const ca = Math.min(1, Math.max(-1, (sin(lat) * cz - sin(decl)) / (cos(lat) * Math.sin(zen * RAD) || 1e-9)))
  const a = Math.acos(ca) / RAD
  return { azimuth: mod(ha > 0 ? a + 180 : 540 - a, 360), altitude: 90 - zen }
}

/** Sunrise and sunset on the day of `t` (as instants) and the hours between them. `rise` and `set` are null when
    the sun does not cross the horizon that day. Uses the standard 90.833° zenith (refraction and the sun's radius). */
export function sunDay(t: Date, lat: number, lon: number): { rise: Date | null; set: Date | null; hours: number } {
  const noonUtc = Date.UTC(t.getUTCFullYear(), t.getUTCMonth(), t.getUTCDate(), 12) - lon * 240000 // local solar noon, near enough to evaluate the orbit at
  const { decl, eot } = orbit(new Date(noonUtc))
  const x = cos(90.833) / (cos(lat) * cos(decl)) - tan(lat) * tan(decl)
  if (x > 1) return { rise: null, set: null, hours: 0 }
  if (x < -1) return { rise: null, set: null, hours: 24 }
  const ha = Math.acos(x) / RAD
  const day = Date.UTC(new Date(noonUtc).getUTCFullYear(), new Date(noonUtc).getUTCMonth(), new Date(noonUtc).getUTCDate())
  const at = (m: number) => new Date(day + m * 60000)
  return { rise: at(720 - 4 * (lon + ha) - eot), set: at(720 - 4 * (lon - ha) - eot), hours: (8 * ha) / 60 }
}

/** The instant at which a wall clock in `zone` reads this date and minute of the day. */
export function zonedInstant(year: number, month: number, day: number, minutes: number, zone: string): Date {
  const guess = Date.UTC(year, month - 1, day, 0, minutes)
  const f = new Intl.DateTimeFormat('en-US', { timeZone: zone, hourCycle: 'h23', year: 'numeric', month: 'numeric', day: 'numeric', hour: 'numeric', minute: 'numeric' })
  const p = Object.fromEntries(f.formatToParts(new Date(guess)).map((x) => [x.type, Number(x.value)]))
  return new Date(guess - (Date.UTC(p.year, p.month - 1, p.day, p.hour, p.minute) - guess)) // shift by the zone's offset at that time
}
