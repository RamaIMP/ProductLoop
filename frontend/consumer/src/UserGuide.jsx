import './userGuide.css'

export default function UserGuide() {
  return <aside className="user-guide" aria-labelledby="user-guide-title">
    <span className="user-guide-eyebrow">GETTING STARTED</span>
    <h1 id="user-guide-title">How to use ProductLoop</h1>
    <p className="user-guide-intro">Help with your X500 shaver, one step at a time.</p>
    <ol>
      <li><h2>Tell us what’s happening</h2><p>Choose <strong>Report a problem</strong> on Home. Describe the issue in your own words—you don’t need to know the technical name.</p></li>
      <li><h2>Show it or say it</h2><p>Use <strong>Voice</strong> to record your explanation and review it before sending. Use <strong>Photo</strong> or <strong>Video</strong> to upload what you see, or <strong>Sound</strong> to upload a recording of the shaver’s noise. Files can be up to 15 MB.</p></li>
      <li><h2>Check the details</h2><p>Wait for the analysis, then answer any follow-up questions. Tell us if we misunderstood something. Review your report and confirm it when the details are right.</p></li>
      <li><h2>Follow the guidance</h2><p>Try the suggested steps only when it is safe. Choose <strong>That fixed it</strong> or <strong>Still not fixed</strong> to let us know the result.</p></li>
      <li><h2>Get more help</h2><p>If the issue remains, raise a support ticket. You can request a callback, find a service centre and book an appointment, or open an email to support.</p></li>
      <li><h2>Find your reports again</h2><p>Use <strong>Home</strong> or <strong>Reports</strong> to view submitted issues and their latest status. Your registered X500 details are in <strong>Profile</strong>.</p></li>
    </ol>
    <div className="user-guide-safety"><strong>Safety comes first</strong><p>If a safety warning appears, follow it instead of troubleshooting. You can save the report and go directly to service support.</p></div>
  </aside>
}
