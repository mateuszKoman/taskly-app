import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook } from '@testing-library/react'
import { createElement, type ReactNode } from 'react'
import { expect, it, vi } from 'vitest'
import { todoFixture } from '../../../test/todoFixture'
import { todoKeys } from '../api/queryKeys'
import { todosApi } from '../api/todos'
import type { Todo } from '../types'
import { useUpdateTodoMutation } from './useUpdateTodoMutation'

vi.mock('../api/todos', () => ({ todosApi: { update: vi.fn() } }))

it('replaces the updated task in the cached list', async () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const other = { ...todoFixture, id: 3 }
  queryClient.setQueryData<Todo[]>(todoKeys.list, [other, todoFixture])
  const saved = { ...todoFixture, completed: true }
  vi.mocked(todosApi.update).mockResolvedValue(saved)
  const wrapper = ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children)
  const { result } = renderHook(() => useUpdateTodoMutation(), { wrapper })
  await act(async () => {
    await result.current.mutateAsync({
      id: todoFixture.id,
      input: { completed: true },
    })
  })
  expect(todosApi.update).toHaveBeenCalledWith(todoFixture.id, {
    completed: true,
  })
  expect(queryClient.getQueryData(todoKeys.list)).toEqual([other, saved])
})

it('does not create a cached list when none was loaded', async () => {
  const queryClient = new QueryClient()
  vi.mocked(todosApi.update).mockResolvedValue(todoFixture)
  const wrapper = ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children)
  const { result } = renderHook(() => useUpdateTodoMutation(), { wrapper })
  await act(async () => {
    await result.current.mutateAsync({ id: 7, input: {} })
  })
  expect(queryClient.getQueryData(todoKeys.list)).toBeUndefined()
})
