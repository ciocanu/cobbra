import { queryClient } from './queryClient'

const LOGGED_IN_KEY = 'cobbra_logged_in'

// No token is ever stored in JS — auth uses an httpOnly cookie set by the server.
// This flag lets the app know whether to show authenticated UI without an API call.
export const isLoggedIn   = () => localStorage.getItem(LOGGED_IN_KEY) === '1'
// Both clear the query cache, so the next account never sees the previous one's
// cached data (e.g. leaving the demo and signing up).
export const markLoggedIn  = () => { queryClient.clear(); localStorage.setItem(LOGGED_IN_KEY, '1') }
export const markLoggedOut = () => { queryClient.clear(); localStorage.removeItem(LOGGED_IN_KEY) }
