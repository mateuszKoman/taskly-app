import { useQuery } from '@tanstack/react-query'
import { todoKeys } from '../api/queryKeys'
import { todosApi } from '../api/todos'

/** All tasks, or only the ones the server reports as due soon. */
export function useTodosQuery(dueSoon = false) {
  return useQuery({
    queryKey: dueSoon ? todoKeys.dueSoon : todoKeys.list,
    queryFn: ({ signal }) => todosApi.list(signal, { dueSoon }),
  })
}
