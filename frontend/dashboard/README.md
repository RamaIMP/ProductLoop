# Quality dashboard

React/Vite dashboard styled after `docs/quality-dashboard.html`.

Run the backend on port 8000, then run `npm install` and `npm run dev` here.
Open http://localhost:5174. `VITE_API_BASE_URL` can override the backend URL.

The page reads saved BigQuery signals through `/api/dashboard/signals`.
Refresh signals recalculates and saves the snapshot using `signal_config`.
The 7/30/90-day dashboard presets end on today's date in Asia/Kolkata. Custom ranges use the selected dates; fixed batch-job configuration does not override dashboard presets.
Counts and trends are not confirmed defects or shipment-normalized failure rates.

Local development currently shares the consumer app's installed dependencies.
Staff authentication and authorization are required before public deployment.
