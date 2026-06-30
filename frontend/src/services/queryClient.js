import { QueryClient } from '@tanstack/react-query'

/**
 * Shared React Query client.
 *
 * Defaults tuned for this app:
 *  - staleTime 60s: a value is considered fresh for a minute, so navigating
 *    back to a page within that window serves the cache instantly with zero
 *    network calls (kills the "every mount refetches" problem).
 *  - gcTime 10min: unused cache is kept around for 10 minutes before being
 *    garbage-collected, so quick round-trips between pages stay warm.
 *  - refetchOnWindowFocus off: avoids a refetch storm every time the tab
 *    regains focus; our data doesn't change second-to-second.
 *  - retry: don't retry 4xx (auth/permission/not-found are deterministic);
 *    retry other errors once.
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,
      gcTime: 10 * 60_000,
      refetchOnWindowFocus: false,
      retry: (failureCount, error) => {
        const status = error?.response?.status
        if (status && status >= 400 && status < 500) return false
        return failureCount < 1
      },
    },
  },
})

/**
 * Centralised query keys. Keeping them here prevents typos and makes
 * invalidation explicit — e.g. after an upload we invalidate `activities`
 * and `stats` so the list and dashboard refetch on next view.
 */
export const qk = {
  me: ['me'],
  settings: ['settings'],
  adminCheck: ['admin', 'check'],
  activities: (params = {}) => ['activities', params],
  activity: (id) => ['activity', String(id)],
  records: ['records'],
  heatmap: ['heatmap'],
  goals: ['goals'],
  segments: ['segments'],
  // Stats keys MUST start with 'stats' so useInvalidate().activities() (which
  // invalidates ['stats']) refreshes the dashboard after an upload.
  fitnessStats: (days = 90) => ['stats', 'fitness', days],
  weeklyStats: (weeks = 16) => ['stats', 'weekly', weeks],
  durabilityTrend: (weeks = 12) => ['stats', 'durability-trend', weeks],
  trainingLoadComparison: (days = 90) => ['stats', 'training-load-comparison', days],
  heatProfile: ['stats', 'heat-profile'],
}
