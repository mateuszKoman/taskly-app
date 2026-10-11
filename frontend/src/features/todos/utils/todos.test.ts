import { afterEach, describe, expect, it, vi } from 'vitest'
import { formatDate, isOverdue, selectTodos, validateTodo } from './todos'
import type { Todo, TodoInput } from '../types'

const base: Todo = {
  id: 1,
  title: 'Sprint plan',
  description: '',
  priority: 'medium',
  completed: false,
  due_date: null,
  created_at: '2026-10-01T12:00:00Z',
  updated_at: '2026-10-01T12:00:00Z',
}

describe('selectTodos', () => {
  it('combines status with a case-insensitive search in the description', () => {
    const matching = { ...base, description: 'Discuss the API' }
    const todos = [
      matching,
      { ...matching, id: 2, completed: true },
      { ...base, id: 3 },
    ]
    expect(selectTodos(todos, 'active', ' api ', 'newest')).toEqual([matching])
  })

  it('sorts by priority without changing the source array', () => {
    const high: Todo = { ...base, id: 2, priority: 'high' }
    const todos = [base, high]
    expect(selectTodos(todos, 'all', '', 'priority')).toEqual([high, base])
    expect(todos).toEqual([base, high])
  })

  it('filters completed tasks', () => {
    const done = { ...base, id: 2, completed: true }
    expect(selectTodos([base, done], 'completed', '', 'newest')).toEqual([done])
  })

  it('sorts by due date with undated tasks last', () => {
    const late = { ...base, id: 2, due_date: '2026-12-01' }
    const soon = { ...base, id: 3, due_date: '2026-11-01' }
    expect(selectTodos([base, late, soon], 'all', '', 'due')).toEqual([
      soon,
      late,
      base,
    ])
  })

  it('sorts newest first and breaks ties by id', () => {
    const newer = { ...base, id: 2, created_at: '2026-10-02T12:00:00Z' }
    const tie = { ...base, id: 3 }
    expect(selectTodos([base, newer, tie], 'all', '', 'newest')).toEqual([
      newer,
      tie,
      base,
    ])
  })
})

describe('validateTodo', () => {
  const valid: TodoInput = {
    title: 'Task',
    description: '',
    due_date: null,
    priority: 'low',
    completed: false,
  }

  it('accepts valid input', () => {
    expect(validateTodo(valid)).toEqual({})
  })

  it('requires a non-blank title', () => {
    expect(validateTodo({ ...valid, title: '   ' }).title).toBe(
      'Enter a task title.',
    )
  })

  it('rejects titles longer than 120 characters', () => {
    expect(validateTodo({ ...valid, title: 'x'.repeat(121) }).title).toBe(
      'The title must be at most 120 characters.',
    )
  })

  it('rejects descriptions longer than 2000 characters', () => {
    expect(
      validateTodo({ ...valid, description: 'x'.repeat(2001) }).description,
    ).toBe('The description must be at most 2000 characters.')
  })

  it.each(['2026-02-30', '2026-1-1', 'tomorrow'])(
    'rejects invalid due date %s',
    (due_date) => {
      expect(validateTodo({ ...valid, due_date }).due_date).toBe(
        'Enter a valid date.',
      )
    },
  )

  it('accepts a valid due date', () => {
    expect(validateTodo({ ...valid, due_date: '2026-02-28' })).toEqual({})
  })
})

describe('isOverdue', () => {
  afterEach(() => vi.useRealTimers())

  it('is true only for active tasks due before today', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date(2026, 9, 15, 12))
    expect(isOverdue({ ...base, due_date: '2026-10-14' })).toBe(true)
    expect(isOverdue({ ...base, due_date: '2026-10-15' })).toBe(false)
    expect(isOverdue({ ...base, due_date: null })).toBe(false)
    expect(
      isOverdue({ ...base, due_date: '2026-10-14', completed: true }),
    ).toBe(false)
  })
})

describe('formatDate', () => {
  it('formats the date in en-GB style', () => {
    expect(formatDate('2026-10-05')).toBe('5 Oct 2026')
  })
})
