import { render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { todoFixture } from '../../../test/todoFixture'
import { TodoList } from './TodoList'

vi.mock('../../../design-system', () => import('../../../design-system/mocks'))
vi.mock('./TodoEmptyState', () => ({
  TodoEmptyState: () => <p>Empty task list</p>,
}))
vi.mock('./TodoItem', () => ({ TodoItem: () => <li>Task</li> }))

it('shows loading feedback before showing an empty list', () => {
  const props = {
    todos: [],
    hasTodos: false,
    failed: false,
    busy: false,
    onCreate: vi.fn(),
    onToggle: vi.fn(),
    onEdit: vi.fn(),
    onDelete: vi.fn(),
  }
  const { rerender } = render(<TodoList {...props} loading />)
  expect(screen.getByRole('status')).toHaveTextContent('Loading your tasks…')
  expect(screen.queryByText('Empty task list')).not.toBeInTheDocument()
  rerender(<TodoList {...props} loading={false} />)
  expect(screen.queryByRole('status')).not.toBeInTheDocument()
  expect(screen.getByText('Empty task list')).toBeVisible()
})

const baseProps = {
  todos: [],
  hasTodos: false,
  loading: false,
  failed: false,
  busy: false,
  onCreate: vi.fn(),
  onToggle: vi.fn(),
  onEdit: vi.fn(),
  onDelete: vi.fn(),
}

it('shows an unavailable message when loading failed with no tasks', () => {
  render(<TodoList {...baseProps} failed />)
  expect(
    screen.getByText('The task list is temporarily unavailable'),
  ).toBeVisible()
  expect(screen.queryByText('Empty task list')).not.toBeInTheDocument()
})

it('keeps showing tasks when a refresh failed but tasks are known', () => {
  render(
    <TodoList
      {...baseProps}
      failed
      hasTodos
      todos={[todoFixture, { ...todoFixture, id: 8 }]}
    />,
  )
  expect(screen.getAllByText('Task')).toHaveLength(2)
  expect(
    screen.queryByText('The task list is temporarily unavailable'),
  ).not.toBeInTheDocument()
})
