import { createContext, useContext } from 'react'

// config: /api/config; user: /api/me; focus: what the user is looking at (sent to the assistant).
export const Session = createContext({ config: null, user: null, can: () => true, focus: {}, setFocus: () => {} })
export const useSession = () => useContext(Session)
