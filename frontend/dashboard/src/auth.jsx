import React from 'react'
import { initializeApp } from 'firebase/app'
import { getAuth, GoogleAuthProvider, signInWithPopup, signOut, onIdTokenChanged, setPersistence, browserSessionPersistence } from 'firebase/auth'
import { createSession } from '../../auth/session.js'
import { createAuthGate } from '../../auth/Gate.jsx'

const env = import.meta.env
const config = { apiKey: env.VITE_FIREBASE_API_KEY, authDomain: env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: env.VITE_FIREBASE_PROJECT_ID, appId: env.VITE_FIREBASE_APP_ID }
const configured = Object.values(config).every(Boolean)
const firebase = configured ? getAuth(initializeApp(config)) : null
export const session = createSession({ currentUser: () => firebase?.currentUser,
  signOut: () => signOut(firebase), apiBase: env.VITE_API_BASE_URL || 'http://localhost:8000' })
export const authenticatedFetch = session.request
export const AuthGate = createAuthGate(React, { configured, session,
  observe: callback => onIdTokenChanged(firebase, callback),
  async login() {
    await setPersistence(firebase, browserSessionPersistence)
    const provider = new GoogleAuthProvider()
    provider.setCustomParameters({ prompt: 'select_account' })
    return signInWithPopup(firebase, provider)
  },
  logout: () => signOut(firebase) })
