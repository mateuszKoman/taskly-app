import { act, renderHook } from '@testing-library/react'
import { expect, it } from 'vitest'
import { useTodoFilters } from './useTodoFilters'

it('starts with default filter, search and sort', () => {
  const { result } = renderHook(() => useTodoFilters())
  expect(result.current.filter).toBe('all')
  expect(result.current.search).toBe('')
  expect(result.current.sort).toBe('newest')
})

it('updates filter, search and sort', () => {
  const { result } = renderHook(() => useTodoFilters())
  act(() => result.current.setFilter('due-soon'))
  act(() => result.current.setSearch('MILK'))
  act(() => result.current.setSort('priority'))
  expect(result.current.filter).toBe('due-soon')
  expect(result.current.search).toBe('MILK')
  expect(result.current.sort).toBe('priority')
})
