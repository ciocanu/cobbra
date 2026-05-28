import { Navigate } from 'react-router-dom'
import { isLoggedIn } from '../services/auth'
import CobbraLanding from '../brand/CobbraLanding'

export default function Landing() {
  if (isLoggedIn()) return <Navigate to="/dashboard" replace />
  return <CobbraLanding />
}
