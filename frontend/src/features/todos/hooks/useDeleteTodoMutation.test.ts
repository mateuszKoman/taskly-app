import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook } from '@testing-library/react'
import { createElement, type ReactNode } from 'react'
import { expect, it, vi } from 'vitest'
import { todoFixture } from '../../../test/todoFixture'
import { todoKeys } from '../api/queryKeys'
import { todosApi } from '../api/todos'
import type { Todo } from '../types'
import { useDeleteTodoMutation } from './useDeleteTodoMutation'

vi.mock('../api/todos', () => ({ todosApi: { remove: vi.fn() } }))

it('removes the deleted task from the cached list', async () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const other = { ...todoFixture, id: 3 }
  queryClient.setQueryData<Todo[]>(todoKeys.list, [other, todoFixture])
  vi.mocked(todosApi.remove).mockResolvedValue(undefined)
  const wrapper = ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children)
  const { result } = renderHook(() => useDeleteTodoMutation(), { wrapper })
  await act(async () => {
    await result.current.mutateAsync(todoFixture.id)
  })
  expect(todosApi.remove).toHaveBeenCalledWith(todoFixture.id)
  expect(queryClient.getQueryData(todoKeys.list)).toEqual([other])
})

it('leaves the cache untouched when the list was never loaded', async () => {
  const queryClient = new QueryClient()
  vi.mocked(todosApi.remove).mockResolvedValue(undefined)
  const wrapper = ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children)
  const { result } = renderHook(() => useDeleteTodoMutation(), { wrapper })
  await act(async () => {
    await result.current.mutateAsync(1)
  })
  expect(queryClient.getQueryData(todoKeys.list)).toBeUndefined()
})
