import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import { useNotice } from '../../hooks/useNotice'
import { todoFixture } from '../../test/todoFixture'
import { useTodoFilters } from './hooks/useTodoFilters'
import { useTodosBusy } from './hooks/useTodosBusy'
import { useTodosQuery } from './hooks/useTodosQuery'
import { useUpdateTodoMutation } from './hooks/useUpdateTodoMutation'
import { TodosPage } from './TodosPage'

vi.mock('../../design-system', () => import('../../design-system/mocks'))
vi.mock('../../hooks/useNotice', () => ({ useNotice: vi.fn() }))
vi.mock('./hooks/useTodoFilters', () => ({ useTodoFilters: vi.fn() }))
vi.mock('./hooks/useTodosBusy', () => ({ useTodosBusy: vi.fn() }))
vi.mock('./hooks/useTodosQuery', () => ({ useTodosQuery: vi.fn() }))
vi.mock('./hooks/useUpdateTodoMutation', () => ({
  useUpdateTodoMutation: vi.fn(),
}))
vi.mock('./components/TodosHeader', () => ({
  TodosHeader: ({ onCreate }: { onCreate: () => void }) => (
    <>
      <h1>Tasks</h1>
      <button onClick={onCreate}>New task</button>
    </>
  ),
}))
vi.mock('./components/TodoFilters', () => ({ TodoFilters: () => null }))
vi.mock('./components/TodoList', () => ({
  TodoList: ({
    todos,
    onToggle,
    onEdit,
    onDelete,
  }: {
    todos: { id: number }[]
    onToggle: (todo: unknown) => void
    onEdit: (todo: unknown) => void
    onDelete: (todo: unknown) => void
  }) => (
    <div>
      <p>Task list</p>
      {todos.map((todo) => (
        <div key={todo.id}>
          <button onClick={() => onToggle(todo)}>toggle</button>
          <button onClick={() => onEdit(todo)}>edit</button>
          <button onClick={() => onDelete(todo)}>delete</button>
        </div>
      ))}
    </div>
  ),
}))
vi.mock('./components/TodoEditor', () => ({
  TodoEditor: ({
    todo,
    onClose,
    onSaved,
  }: {
    todo: { title: string } | 'new'
    onClose: () => void
    onSaved: (notice: string) => void
  }) => (
    <div>
      <p>editor: {todo === 'new' ? 'new' : todo.title}</p>
      <button onClick={onClose}>close editor</button>
      <button onClick={() => onSaved('Task saved.')}>save editor</button>
    </div>
  ),
}))
vi.mock('./components/DeleteTodoDialog', () => ({
  DeleteTodoDialog: ({
    onClose,
    onDeleted,
  }: {
    onClose: () => void
    onDeleted: () => void
  }) => (
    <div>
      <p>delete dialog</p>
      <button onClick={onClose}>close dialog</button>
      <button onClick={onDeleted}>confirm delete</button>
    </div>
  ),
}))
vi.mock('../../components/SuccessNotice', () => ({ SuccessNotice: () => null }))

function setup({
  busy = false,
  mutationError = null as Error | null,
  mutateAsync = vi.fn(),
} = {}) {
  const refetch = vi.fn().mockResolvedValue(undefined)
  const reset = vi.fn()
  const notify = vi.fn()
  vi.mocked(useTodosQuery).mockReturnValue({
    data: [todoFixture],
    isPending: false,
    isFetching: false,
    isError: false,
    error: null,
    refetch,
  } as unknown as ReturnType<typeof useTodosQuery>)
  vi.mocked(useUpdateTodoMutation).mockReturnValue({
    error: mutationError,
    reset,
    mutateAsync,
  } as unknown as ReturnType<typeof useUpdateTodoMutation>)
  vi.mocked(useTodosBusy).mockReturnValue(busy)
  vi.mocked(useNotice).mockReturnValue({ message: '', notify })
  vi.mocked(useTodoFilters).mockReturnValue({
    filter: 'all',
    search: '',
    sort: 'newest',
    visible: [todoFixture],
    setFilter: vi.fn(),
    setSearch: vi.fn(),
    setSort: vi.fn(),
  })
  return { notify, mutateAsync }
}

it('displays a query failure and resets mutation errors before retrying', async () => {
  const user = userEvent.setup()
  const refetch = vi.fn().mockResolvedValue(undefined)
  const reset = vi.fn()
  vi.mocked(useTodosQuery).mockReturnValue({
    data: [],
    isPending: false,
    isFetching: false,
    isError: true,
    error: new Error('The server is unavailable.'),
    refetch,
  } as unknown as ReturnType<typeof useTodosQuery>)
  vi.mocked(useUpdateTodoMutation).mockReturnValue({
    error: null,
    reset,
    mutateAsync: vi.fn(),
  } as unknown as ReturnType<typeof useUpdateTodoMutation>)
  vi.mocked(useTodosBusy).mockReturnValue(false)
  vi.mocked(useNotice).mockReturnValue({ message: '', notify: vi.fn() })
  vi.mocked(useTodoFilters).mockReturnValue({
    filter: 'all',
    search: '',
    sort: 'newest',
    visible: [],
    setFilter: vi.fn(),
    setSearch: vi.fn(),
    setSort: vi.fn(),
  })
  render(<TodosPage />)
  expect(screen.getByTestId('alert')).toHaveTextContent(
    'The server is unavailable.',
  )
  await user.click(screen.getByRole('button', { name: 'Try again' }))
  await waitFor(() => expect(refetch).toHaveBeenCalledTimes(1))
  expect(reset).toHaveBeenCalledTimes(1)
  expect(reset.mock.invocationCallOrder[0]).toBeLessThan(
    refetch.mock.invocationCallOrder[0],
  )
})

it('toggles a task and announces completion', async () => {
  const user = userEvent.setup()
  const { notify, mutateAsync } = setup({
    mutateAsync: vi.fn().mockResolvedValue({ ...todoFixture, completed: true }),
  })
  render(<TodosPage />)
  await user.click(screen.getByRole('button', { name: 'toggle' }))
  expect(mutateAsync).toHaveBeenCalledWith({
    id: todoFixture.id,
    input: { completed: !todoFixture.completed },
  })
  expect(notify).toHaveBeenCalledWith('Another task complete. Well done!')
})

it('announces when a task is marked active again', async () => {
  const user = userEvent.setup()
  const { notify } = setup({
    mutateAsync: vi
      .fn()
      .mockResolvedValue({ ...todoFixture, completed: false }),
  })
  render(<TodosPage />)
  await user.click(screen.getByRole('button', { name: 'toggle' }))
  expect(notify).toHaveBeenCalledWith('Task marked as active.')
})

it('does not notify when toggling fails', async () => {
  const user = userEvent.setup()
  const { notify, mutateAsync } = setup({
    mutateAsync: vi.fn().mockRejectedValue(new Error('nope')),
  })
  render(<TodosPage />)
  await user.click(screen.getByRole('button', { name: 'toggle' }))
  await waitFor(() => expect(mutateAsync).toHaveBeenCalled())
  expect(notify).not.toHaveBeenCalled()
})

it('ignores toggles while busy', async () => {
  const user = userEvent.setup()
  const { mutateAsync } = setup({ busy: true })
  render(<TodosPage />)
  await user.click(screen.getByRole('button', { name: 'toggle' }))
  expect(mutateAsync).not.toHaveBeenCalled()
})

it('shows a mutation error in the alert', () => {
  setup({ mutationError: new Error('Toggle failed.') })
  render(<TodosPage />)
  expect(screen.getByTestId('alert')).toHaveTextContent('Toggle failed.')
})

it('opens the editor for a new task and notifies when saved', async () => {
  const user = userEvent.setup()
  const { notify } = setup()
  render(<TodosPage />)
  await user.click(screen.getByRole('button', { name: 'New task' }))
  expect(screen.getByText('editor: new')).toBeVisible()
  await user.click(screen.getByRole('button', { name: 'save editor' }))
  expect(notify).toHaveBeenCalledWith('Task saved.')
  expect(screen.queryByText('editor: new')).not.toBeInTheDocument()
})

it('opens the editor for an existing task and closes it', async () => {
  const user = userEvent.setup()
  setup()
  render(<TodosPage />)
  await user.click(screen.getByRole('button', { name: 'edit' }))
  expect(screen.getByText(`editor: ${todoFixture.title}`)).toBeVisible()
  await user.click(screen.getByRole('button', { name: 'close editor' }))
  expect(screen.queryByText(/editor:/)).not.toBeInTheDocument()
})

it('closes the delete dialog and notifies after deletion', async () => {
  const user = userEvent.setup()
  const { notify } = setup()
  render(<TodosPage />)
  await user.click(screen.getByRole('button', { name: 'delete' }))
  expect(screen.getByText('delete dialog')).toBeVisible()
  await user.click(screen.getByRole('button', { name: 'close dialog' }))
  expect(screen.queryByText('delete dialog')).not.toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'delete' }))
  await user.click(screen.getByRole('button', { name: 'confirm delete' }))
  expect(notify).toHaveBeenCalledWith('Task deleted.')
  expect(screen.queryByText('delete dialog')).not.toBeInTheDocument()
})
