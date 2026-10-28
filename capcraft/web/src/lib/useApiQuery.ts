import { useEffect, useState } from 'react'
import { ApiError } from '../api/client'

type State<Res, Req> = { for: Req | null; data: Res | null; error: string | null }

/**
 * Run `call(req)` whenever `req` changes (pass null to wait). An older request is
 * cancelled when a newer one starts. The last good result stays on screen while the
 * next one loads, so charts do not flash empty on every slider move.
 */
export function useApiQuery<Req, Res>(req: Req | null, call: (r: Req, signal: AbortSignal) => Promise<Res>) {
  const [state, setState] = useState<State<Res, Req>>({ for: null, data: null, error: null })

  useEffect(() => {
    if (req === null) return
    const ac = new AbortController()
    call(req, ac.signal)
      .then((data) => setState({ for: req, data, error: null }))
      .catch((e) => {
        if (e instanceof DOMException && e.name === 'AbortError') return
        setState((s) => ({ for: req, data: s.data, error: e instanceof ApiError ? e.message : String(e) }))
      })
    return () => ac.abort()
    // `call` is a stable function from the api object
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [req])

  return { data: state.data, error: state.error, busy: req !== null && state.for !== req }
}
