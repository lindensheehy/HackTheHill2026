// Optional login. With auth off (the default), nothing here runs and every request is anonymous.
// With auth on, @auth0/auth0-spa-js (MIT) handles the OIDC redirect and hands us access tokens for the API.
//
// Tokens are kept in localStorage with refresh tokens, so a page refresh doesn't log you out (the in-memory
// default needs third-party cookies, which Chrome increasingly blocks). The trade-off is that a script
// injected into the page could read the token; acceptable for this demo.

let client = null
let cfg = null

export const callbackUrl = () => window.location.origin

export async function initAuth(config) {
  cfg = config
  if (!config.enabled) return { enabled: false, authenticated: true }
  const params = new URLSearchParams(window.location.search)
  const { createAuth0Client } = await import('@auth0/auth0-spa-js')
  client = await createAuth0Client({
    domain: config.domain,
    clientId: config.client_id,
    authorizationParams: { audience: config.audience, redirect_uri: callbackUrl() },
    cacheLocation: 'localstorage',
    useRefreshTokens: true,
    useRefreshTokensFallback: true, // if the API doesn't allow offline access, fall back to the iframe method
  })
  // Auth0 sends failures back to our callback as ?error=…&error_description=…; surface them instead of looping.
  if (params.get('error')) {
    const error = { code: params.get('error'), description: params.get('error_description') || '' }
    window.history.replaceState({}, document.title, `/${window.location.hash}`)
    return { enabled: true, authenticated: false, error }
  }
  if (params.get('code') && params.get('state')) {
    try {
      const { appState } = await client.handleRedirectCallback()
      window.history.replaceState({}, document.title, `/${appState?.hash || window.location.hash}`)
    } catch (e) {
      window.history.replaceState({}, document.title, `/${window.location.hash}`)
      return { enabled: true, authenticated: false, error: { code: e.error || 'callback_failed', description: e.error_description || e.message } }
    }
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
export const logout = () => client?.logout({ logoutParams: { returnTo: callbackUrl() } })
export const authEnabled = () => !!cfg?.enabled
