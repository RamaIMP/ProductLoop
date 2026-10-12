import React from 'react'

export default function HomeButton({ onClick }) {
  return <button type="button" onClick={onClick} aria-label="Go to Home"
    style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 6,
      flexShrink: 0, minHeight: 44, padding: '6px 8px', border: 0,
      background: 'transparent', color: '#1a73e8', fontWeight: 700,
      fontSize: 14, cursor: 'pointer' }}>
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      <path d="m3 10 9-7 9 7" />
      <path d="M5 9v11h5v-6h4v6h5V9" />
    </svg>
    <span>Home</span>
  </button>
}
