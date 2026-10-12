# ProductLoop consumer app

React + Vite consumer prototype. It calls the local FastAPI development API by
default and is structured for Firebase Hosting deployment.

```bash
npm install
npm run dev
```

Run the backend in another terminal from `productloop/backend`:

```bash
../productLoop_env/bin/uvicorn app.main:app --reload --port 8000
```

Set `VITE_API_BASE_URL` when the API is deployed to Cloud Run.
