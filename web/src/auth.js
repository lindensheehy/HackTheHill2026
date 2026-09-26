// Optional login. With auth off (the default), nothing here runs and every request is anonymous.
// With auth on, @auth0/auth0-spa-js (MIT) handles the OIDC redirect and hands us access tokens for the API.

let client = null
let cfg = null

export async function initAuth(config) {
  cfg = config
  if (!config.enabled) return { enabled: false, authenticated: true }
  const { createAuth0Client } = await import('@auth0/auth0-spa-js')
  client = await createAuth0Client({
    domain: config.domain,
    clientId: config.client_id,
    authorizationParams: { audience: config.audience, redirect_uri: window.location.origin },
    cacheLocation: 'memory',
  })
  if (window.location.search.includes('code=') && window.location.search.includes('state=')) {
    const { appState } = await client.handleRedirectCallback()
    window.history.replaceState({}, document.title, `/${appState?.hash || window.location.hash}`)
  }
  return { enabled: true, authenticated: await client.isAuthenticated() }
}

export async function token() {
  if (!client) return null
  try {
    return await client.getTokenSilently()
  } catch {
    return null
  }
}

export const login = () => client?.loginWithRedirect({ appState: { hash: window.location.hash } })
export const logout = () => client?.logout({ logoutParams: { returnTo: window.location.origin } })
export const authEnabled = () => !!cfg?.enabled
