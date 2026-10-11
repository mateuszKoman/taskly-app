export type Priority = 'low' | 'medium' | 'high'
export interface TodoInput {
  title: string
  description: string
  priority: Priority
  due_date: string | null
  completed: boolean
}
export interface Todo extends TodoInput {
  id: number
  /** Computed by the API: not completed and due within the next 48 hours. */
  due_soon: boolean
  created_at: string
  updated_at: string
}
export type Filter = 'all' | 'active' | 'completed' | 'due-soon'
export type Sort = 'newest' | 'priority' | 'due'
