const LOGGED_IN_KEY = 'cobbra_logged_in'

// No token is ever stored in JS — auth uses an httpOnly cookie set by the server.
// This flag lets the app know whether to show authenticated UI without an API call.
export const isLoggedIn   = () => localStorage.getItem(LOGGED_IN_KEY) === '1'
export const markLoggedIn  = () => localStorage.setItem(LOGGED_IN_KEY, '1')
export const markLoggedOut = () => localStorage.removeItem(LOGGED_IN_KEY)
