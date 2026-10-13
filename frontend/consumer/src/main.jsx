import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './styles.css'
import './media.css'
import App from './App.jsx'
import { AuthGate } from './auth.jsx'
import { AccountActions } from './accountActions'

createRoot(document.getElementById('root')).render(<StrictMode><AuthGate>{(user, actions) => <AccountActions.Provider value={actions}><App key={user.uid} user={user} /></AccountActions.Provider>}</AuthGate></StrictMode>)
