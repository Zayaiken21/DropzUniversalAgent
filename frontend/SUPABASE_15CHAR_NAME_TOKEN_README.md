# Dropz Supabase Live Token Fix

This fix keeps your existing app structure and changes only the token layer.

## What changed

- Client tokens are exactly 15 random uppercase letters/numbers.
- Supabase stores only:
  - `name`
  - `token`
  - `active`
  - `created_at`
- Login returns the saved client name, so the app can show the client's real generated name instead of just `client`.
- CEO login remains local using `CEO_SECRET_PHRASE`.
- SQLite fallback remains if Supabase keys are missing.

## Files to replace

Put these files into your project:

```txt
frontend/database.py
frontend/config.py
```

## Supabase SQL

Open Supabase > SQL Editor > New Query.

Paste the contents of:

```txt
supabase_client_licenses_15char_name_token.sql
```

Click **Run**.

Do not click **Explain**.

## Required env / Streamlit secrets

```env
SUPABASE_URL=https://gzondcztcusuwyksoyvp.supabase.co
SUPABASE_ANON_KEY=your_anon_public_key
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key
CEO_SECRET_PHRASE=your_ceo_password
```

## Where to get the keys

Supabase Dashboard > Project Settings > API

- Project URL = `SUPABASE_URL`
- anon public key = `SUPABASE_ANON_KEY`
- service_role key = `SUPABASE_SERVICE_ROLE_KEY`

For a public EXE, the service role key can technically be extracted if bundled. For your easiest version this works, but the safest sell-ready version is an Edge Function later. The app structure remains ready for that.

## Live test

1. Open CEO Settings.
2. Generate a client token for a name.
3. Token should be exactly 15 characters.
4. Log out.
5. Log in using that token.
6. The client name should show from Supabase.
