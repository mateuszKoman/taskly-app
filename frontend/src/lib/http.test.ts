import { afterEach, expect, it, vi } from 'vitest'
import { request } from './http'

function stubFetch(impl: () => Promise<unknown>) {
  const fetchMock = vi.fn(impl)
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function jsonResponse(status: number, body?: unknown) {
  return new Response(body === undefined ? null : JSON.stringify(body), {
    status,
  })
}

afterEach(() => vi.unstubAllGlobals())

it('prefixes the path with /api and sends JSON headers', async () => {
  const fetchMock = stubFetch(async () => jsonResponse(200, [{ id: 1 }]))
  await expect(
    request('/todos', { headers: { 'X-Test': '1' } }),
  ).resolves.toEqual([{ id: 1 }])
  expect(fetchMock).toHaveBeenCalledWith('/api/todos', {
    headers: { 'Content-Type': 'application/json', 'X-Test': '1' },
  })
})

it('returns undefined for 204 responses', async () => {
  stubFetch(async () => new Response(null, { status: 204 }))
  await expect(
    request('/todos/1', { method: 'DELETE' }),
  ).resolves.toBeUndefined()
})

it('reports a connection error when fetch fails', async () => {
  stubFetch(() => Promise.reject(new TypeError('offline')))
  await expect(request('/todos')).rejects.toThrow(
    'Cannot connect to the server. Please try again.',
  )
})

it('rethrows the original error when the request was aborted', async () => {
  const controller = new AbortController()
  controller.abort()
  const abortError = new DOMException('Aborted', 'AbortError')
  stubFetch(() => Promise.reject(abortError))
  await expect(request('/todos', { signal: controller.signal })).rejects.toBe(
    abortError,
  )
})

it('maps 422 responses to the validation message', async () => {
  stubFetch(async () => jsonResponse(422, { detail: [{ msg: 'bad' }] }))
  await expect(request('/todos')).rejects.toThrow(/Check the task details/)
})

it('uses the string detail of an error response', async () => {
  stubFetch(async () => jsonResponse(404, { detail: 'Task not found.' }))
  await expect(request('/todos/9')).rejects.toThrow('Task not found.')
})

it('falls back to a generic message when no detail is available', async () => {
  stubFetch(async () => new Response('oops', { status: 500 }))
  await expect(request('/todos')).rejects.toThrow(
    'The operation failed. Please try again.',
  )
})
