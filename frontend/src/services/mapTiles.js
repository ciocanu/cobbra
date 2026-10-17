// Shared basemap tile configuration — spread onto every <TileLayer {...TILE_PROPS} />.
//
// CARTO now requires an API key for its Dark Matter raster basemap: a keyless
// request returns a PNG with "API KEY REQUIRED" burned into it. If a key is
// provided at build time (VITE_CARTO_KEY, free at https://carto.com/basemaps/apikey)
// we use Dark Matter. Otherwise we fall back to keyless OpenStreetMap tiles,
// darkened with a CSS filter (.tiles-dark in index.css) to match the UI.
//
// Note: tile.openstreetmap.org is volunteer-run and forbids heavy use — fine at
// our current scale; switch to a keyed provider if traffic grows.
const CARTO_KEY = import.meta.env.VITE_CARTO_KEY || ''

export const TILE_PROPS = CARTO_KEY
  ? {
      url: `https://basemaps.cartocdn.com/rastertiles/dark_all/{z}/{x}/{y}{r}.png?key=${CARTO_KEY}`,
      attribution: '&copy; <a href="https://carto.com/">CARTO</a> &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    }
  : {
      url: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
      className: 'tiles-dark',
    }
