// Shared basemap tile configuration.
//
// CARTO now requires an API key for its Dark Matter raster basemap: a keyless
// request returns HTTP 200 with a PNG that has "API KEY REQUIRED" burned into
// it, which is why the map backgrounds broke. The key is a public, domain-
// restricted basemap key (like a Google Maps JS key), so it is safe to ship in
// the client bundle. Get one free (no account needed) at
// https://carto.com/basemaps/apikey and provide it at build time as
// VITE_CARTO_KEY.
//
// If the key is missing we fall back to keyless OpenStreetMap tiles so the map
// still renders something usable instead of the watermark.
const CARTO_KEY = import.meta.env.VITE_CARTO_KEY || ''

export const TILE_URL = CARTO_KEY
  ? `https://basemaps.cartocdn.com/rastertiles/dark_all/{z}/{x}/{y}{r}.png?key=${CARTO_KEY}`
  : 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png'

export const TILE_ATTRIBUTION = CARTO_KEY
  ? '&copy; <a href="https://carto.com/">CARTO</a> &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
  : '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
