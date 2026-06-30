import { useQuery, useQueryClient } from '@tanstack/react-query'
import { qk } from './queryClient'
import {
  getMe, getSettings, adminCheck,
  getActivities, getActivity,
  getRecords, getHeatmap, getGoals, getSegments,
  getFitnessStats, getWeeklyStats, getDurabilityTrend,
  getTrainingLoadComparison, getHeatProfile,
} from './api'

// ── Read hooks ──────────────────────────────────────────────────────────────
// Each returns the unwrapped response data. Slow-changing resources (me,
// settings) get a long staleTime so they're fetched once and shared across
// every component that needs them instead of re-fetched on each mount.

export function useMe(options = {}) {
  return useQuery({
    queryKey: qk.me,
    queryFn: () => getMe().then(r => r.data),
    staleTime: 5 * 60_000,
    ...options,
  })
}

export function useSettings(options = {}) {
  return useQuery({
    queryKey: qk.settings,
    queryFn: () => getSettings().then(r => r.data),
    staleTime: 5 * 60_000,
    ...options,
  })
}

export function useAdminCheck(options = {}) {
  return useQuery({
    queryKey: qk.adminCheck,
    queryFn: () => adminCheck().then(() => true),
    staleTime: 30 * 60_000,
    retry: false,
    ...options,
  })
}

export function useActivities(params = {}, options = {}) {
  return useQuery({
    queryKey: qk.activities(params),
    queryFn: () => getActivities(params).then(r => r.data),
    ...options,
  })
}

export function useActivity(id, options = {}) {
  return useQuery({
    queryKey: qk.activity(id),
    queryFn: () => getActivity(id).then(r => r.data),
    // A ride's core data is immutable once parsed — keep it fresh for a long
    // time so revisiting an activity is instant.
    staleTime: 30 * 60_000,
    enabled: id != null,
    ...options,
  })
}

export function useRecords(options = {}) {
  return useQuery({
    queryKey: qk.records,
    queryFn: () => getRecords().then(r => r.data),
    ...options,
  })
}

export function useHeatmap(options = {}) {
  return useQuery({
    queryKey: qk.heatmap,
    queryFn: () => getHeatmap().then(r => r.data),
    ...options,
  })
}

export function useGoals(options = {}) {
  return useQuery({
    queryKey: qk.goals,
    queryFn: () => getGoals().then(r => r.data),
    ...options,
  })
}

export function useSegments(options = {}) {
  return useQuery({
    queryKey: qk.segments,
    queryFn: () => getSegments().then(r => r.data),
    ...options,
  })
}

// ── Stats hooks ───────────────────────────────────────────────────────────────
// Keys start with 'stats' so an upload (which invalidates ['stats']) refreshes
// the dashboard panels on next view.

export function useFitnessStats(days = 90, options = {}) {
  return useQuery({
    queryKey: qk.fitnessStats(days),
    queryFn: () => getFitnessStats(days).then(r => r.data),
    ...options,
  })
}

export function useWeeklyStats(weeks = 16, options = {}) {
  return useQuery({
    queryKey: qk.weeklyStats(weeks),
    queryFn: () => getWeeklyStats(weeks).then(r => r.data),
    ...options,
  })
}

export function useDurabilityTrend(weeks = 12, options = {}) {
  return useQuery({
    queryKey: qk.durabilityTrend(weeks),
    queryFn: () => getDurabilityTrend(weeks).then(r => r.data),
    ...options,
  })
}

export function useTrainingLoadComparison(days = 90, options = {}) {
  return useQuery({
    queryKey: qk.trainingLoadComparison(days),
    queryFn: () => getTrainingLoadComparison(days).then(r => r.data),
    ...options,
  })
}

export function useHeatProfile(options = {}) {
  return useQuery({
    queryKey: qk.heatProfile,
    queryFn: () => getHeatProfile().then(r => r.data),
    ...options,
  })
}

// ── Invalidation helpers ──────────────────────────────────────────────────────
// Call after a mutation so the next view refetches the affected resources.

export function useInvalidate() {
  const qc = useQueryClient()
  return {
    // After upload/delete: activity list, records, heatmap and dashboard stats
    // are all derived from the activity set.
    activities: () => {
      qc.invalidateQueries({ queryKey: ['activities'] })
      qc.invalidateQueries({ queryKey: qk.records })
      qc.invalidateQueries({ queryKey: qk.heatmap })
      qc.invalidateQueries({ queryKey: ['stats'] })
    },
    settings: () => qc.invalidateQueries({ queryKey: qk.settings }),
    me: () => qc.invalidateQueries({ queryKey: qk.me }),
    activity: (id) => qc.invalidateQueries({ queryKey: qk.activity(id) }),
    segments: () => qc.invalidateQueries({ queryKey: qk.segments }),
    goals: () => qc.invalidateQueries({ queryKey: qk.goals }),
  }
}
