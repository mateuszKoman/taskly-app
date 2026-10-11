import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import { createElement, type ReactNode } from 'react'
import { beforeEach, expect, it, vi } from 'vitest'
import { todoFixture } from '../../../test/todoFixture'
import { todoKeys } from '../api/queryKeys'
import { todosApi } from '../api/todos'
import { useTodosQuery } from './useTodosQuery'

vi.mock('../api/todos', () => ({ todosApi: { list: vi.fn() } }))
beforeEach(() => vi.clearAllMocks())

function setup(dueSoon?: boolean) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  const wrapper = ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children)
  const hook = renderHook(() => useTodosQuery(dueSoon), { wrapper })
  return { queryClient, ...hook }
}

it('loads all tasks under the list key by default', async () => {
  vi.mocked(todosApi.list).mockResolvedValue([todoFixture])
  const { result, queryClient } = setup()
  await waitFor(() => expect(result.current.isSuccess).toBe(true))
  expect(todosApi.list).toHaveBeenCalledWith(expect.anything(), {
    dueSoon: false,
  })
  expect(queryClient.getQueryData(todoKeys.list)).toEqual([todoFixture])
  expect(queryClient.getQueryData(todoKeys.dueSoon)).toBeUndefined()
})

it('loads due-soon tasks under the due-soon key', async () => {
  vi.mocked(todosApi.list).mockResolvedValue([todoFixture])
  const { result, queryClient } = setup(true)
  await waitFor(() => expect(result.current.isSuccess).toBe(true))
  expect(todosApi.list).toHaveBeenCalledWith(expect.anything(), {
    dueSoon: true,
  })
  expect(queryClient.getQueryData(todoKeys.dueSoon)).toEqual([todoFixture])
  expect(queryClient.getQueryData(todoKeys.list)).toBeUndefined()
})
