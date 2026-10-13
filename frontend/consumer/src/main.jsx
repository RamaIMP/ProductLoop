import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './styles.css'
import './media.css'
import App from './App.jsx'
import { AuthGate } from './auth.jsx'

createRoot(document.getElementById('root')).render(<StrictMode><AuthGate>{user => <App key={user.uid} user={user} />}</AuthGate></StrictMode>)
