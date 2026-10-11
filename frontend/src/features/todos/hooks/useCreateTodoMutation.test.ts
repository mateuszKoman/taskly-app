import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook } from '@testing-library/react'
import { createElement, type ReactNode } from 'react'
import { expect, it, vi } from 'vitest'
import { todoFixture } from '../../../test/todoFixture'
import { todoKeys } from '../api/queryKeys'
import { todosApi } from '../api/todos'
import type { Todo } from '../types'
import { useCreateTodoMutation } from './useCreateTodoMutation'

vi.mock('../api/todos', () => ({ todosApi: { create: vi.fn() } }))

it('puts the created task first in the cached list without duplicating it', async () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const other = { ...todoFixture, id: 3 }
  queryClient.setQueryData<Todo[]>(todoKeys.list, [other, todoFixture])
  const saved = { ...todoFixture, title: 'Saved' }
  vi.mocked(todosApi.create).mockResolvedValue(saved)
  const wrapper = ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children)
  const { result } = renderHook(() => useCreateTodoMutation(), { wrapper })
  const input = {
    title: 'Saved',
    description: '',
    priority: 'medium' as const,
    due_date: null,
    completed: false,
  }
  await act(async () => {
    await result.current.mutateAsync(input)
  })
  expect(todosApi.create).toHaveBeenCalledWith(input)
  expect(queryClient.getQueryData(todoKeys.list)).toEqual([saved, other])
})

it('starts a cached list when none exists', async () => {
  const queryClient = new QueryClient()
  vi.mocked(todosApi.create).mockResolvedValue(todoFixture)
  const wrapper = ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children)
  const { result } = renderHook(() => useCreateTodoMutation(), { wrapper })
  await act(async () => {
    await result.current.mutateAsync({
      title: 'x',
      description: '',
      priority: 'low',
      due_date: null,
      completed: false,
    })
  })
  expect(queryClient.getQueryData(todoKeys.list)).toEqual([todoFixture])
})
