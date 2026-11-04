# Website: Google sign-in and each visitor's Earth Engine project

[Project home](../README.md) · [Website entry point](../app.py) · [Deployment requirements](../requirements.txt)

This is the separate Streamlit website. It prepares a map with the existing Python
reference engine, displays the study area with its 12-class legend, and presents
the saved validation report. The working [Colab assistant](../python/Libya_Land_Cover_Assistant.ipynb)
remains the complete interface for chat, saved-work ZIPs and TIFF tile exports.
Those features have not been ported into this website.

## What a visitor does

1. Choose **Sign in with Google** and grant Earth Engine access.
2. Enter their Earth Engine Cloud **project ID**, **boundary asset** and
   **training-data asset**. They must have permission to use all three.
3. Choose the **target year** and **fallback year**, then click **Create map** once.
   **Check access** is optional and does not train a model.
4. Explore the map, read the accuracy tables and **Download accuracy report**.

No service-account JSON key, pasted access token, paid chat API or command-line
authentication is required from visitors. Signing in does not grant access to
the repository owner's private assets. Each requested operation explicitly uses
the visitor's token and selected Cloud project, including map display requests.
Project quotas and Google's eligibility/billing rules still apply; this code
does not bypass quota limits or make a paid project free.

## One-time setup by the website owner

The app cannot complete Google sign-in until its deployed URL is registered with
Google and the host has its OAuth settings. These settings identify the website;
they do **not** supply an owner service account for visitors' calculations.

1. Deploy this repository's **`main`** branch with **`app.py`** as the Streamlit
   entry point and **Python 3.12**. Install the root `requirements.txt`.
   Streamlit Community Cloud is one possible host; its availability and resource
   limits are separate from Earth Engine quota.
2. In Google Cloud / Google Auth Platform, configure a consent screen and create
   an OAuth client of type **Web application**. Configure the Earth Engine scope
   `https://www.googleapis.com/auth/earthengine` together with `openid`, `profile`
   and `email`. In testing mode, add each test visitor to the allowed test users.
   A public launch may require Google's consent/verification process for the
   requested scope and audience; follow the Google Console's requirements.
3. Register the exact authorized redirect URI:
   **`https://YOUR-WEBSITE-HOST/oauth2callback`**.
   For local development only, use **`http://localhost:8501/oauth2callback`**.
   The Google client and Streamlit settings must contain the same URI.
4. Copy the structure of [`.streamlit/secrets.example.toml`](../.streamlit/secrets.example.toml)
   into the host's private secrets settings (or local `.streamlit/secrets.toml`).
   Supply the client ID, client secret, a strong random cookie secret and the
   deployed redirect URI. Keep `expose_tokens = ["access"]` and the Earth Engine
   scope. Ordinary identity-only Google sign-in does not authorize API calls.
   **Never commit actual secrets or upload them to an issue/chat.**
5. Enable/register Earth Engine on each project used for computation. Visitors
   need the required project roles, API access and permission to read their
   selected feature collections. Account sign-in and project registration are
   separate requirements.

For a developer running this website locally:

```bash
python -m pip install -r requirements.txt
streamlit run app.py
```

No configuration is silently taken from the owner's Earth Engine credentials,
and no `ee.Authenticate()` browser or localhost flow is started on the server.
Missing deployment settings show an owner setup message before any Google API
request. The OAuth template contains placeholders, not configured credentials.

## What was repaired

| Previous problem | Website behavior now |
| --- | --- |
| Uploaded service-account key; no explicit computation project | Google account authorization with an explicit visitor-selected project |
| Hard-coded owner Fezzan/TD-V4 assets | Both asset paths are supplied by the visitor and checked for access |
| Fezzan output clipped to a fixed Tripoli rectangle | The engine's selected study-area image is displayed without replacement clipping |
| Single seed and 50-tree shortcut | Existing reference seed search and default 500-tree model |
| Access to nonexistent `metrics['user']` | User accuracy derived locally from the already saved confusion matrix |
| Nested accuracy vectors truncated | Both flat and nested vectors are handled; all 12 classes are shown |
| Invalid CSS legend colours without `#` | Valid reference palette colours |
| Result disappears on Streamlit interaction | Session-local result survives reruns; repeated identical requests reuse it |
| Display failure discards preparation | Graph and metrics are saved before display; display can be retried separately |
| Shared Earth Engine client risks mixing identities | Fresh subprocess with explicit credentials and project for each API operation |

The GEE reference file, Python classifier engine and Colab notebooks are not
modified by this website repair. There are no new area statistics or additional
accuracy computations for displaying reports.

## Session and credential behavior

- Streamlit's built-in Google OIDC flow handles redirects, state and nonce.
  The access token is obtained through `st.user.tokens.access`; the ID token is
  never used as an Earth Engine credential.
- Tokens go to the worker through a private process pipe. They are not command
  arguments, report fields, application credential files or shared cached state.
  The host receives the token to make authorized API calls, so visitors must
  trust the website operator. Use HTTPS in production and restrict host access.
- Each API operation uses a new Python process, so Earth Engine's global client
  cannot switch to another visitor's account during a request.
- The website requests online access only. It does not request/store refresh
  tokens. When authorization expires, visitors sign in again. Identity-token
  expiry blocks new actions; expired/revoked API tokens also produce a safe
  reconnect message. Download the report before signing out.
- Settings, graph and report are temporary Streamlit session state. Sign-out,
  changing accounts, browser reload or host restart can clear them. The JSON
  report is not a resumable map backup and does not contain TIFF pixels.
- Failed new work preserves the previous successful result in the same session.
  A successful new map replaces the displayed result. Download its report first
  if you need to keep an earlier report.
- Mapping is synchronous, with a 45-minute worker limit. Other requests have a
  three-minute worker limit. A host may impose a shorter lifetime. This is not a
  durable background job system or a substitute for the Colab export workflow.

## Troubleshooting

| Message/symptom | What it means |
| --- | --- |
| Owner must configure Google sign-in | Missing/placeholder hosting secrets; not a visitor account failure |
| `redirect_uri_mismatch` at Google | Callback differs between Google OAuth client and hosting secrets |
| Google blocks a test visitor | Check the consent screen audience, test users and publishing/verification state |
| Connected to Google but access check fails | Check the selected computation project, Earth Engine registration/API, asset sharing and Earth Engine scope consent |
| Authorization expired | Download the report, sign out and sign in again |
| Quota limit / 429 | The visitor's selected project is limited; repeated map creation is not a fix |
| Map preparation succeeded but colours are blank | Rendering is separate and can encounter computation limits; refresh the saved display without retraining |
| Embedding coverage unavailable | Check target/fallback years, annual window and asset location |

## Validation and deployment boundary

The automated tests cover missing OAuth setup, sign-in UI, project/asset input,
target/fallback changes, reference engine delegation, metric shapes, report
redaction, account changes, rerun persistence, duplicate submission protection,
display failures, previous-result preservation, expired authorization and
credential transport. They use simulated Google responses, not real credentials.

```bash
python -m unittest discover -s tests -p 'test_website*.py' -v
```

Live Google consent, actual project permissions, computation and browser tile
rendering must be verified on the deployed host. Publishing repository code
does not configure the host's secrets or Google's OAuth client automatically.

Before public release, verify with two authorized test accounts and separate
projects: each account sees only its session's inputs/results, inaccessible
assets fail clearly, and changing accounts clears the previous result. Confirm
that sign-in, one map, a display refresh and report download all work. Do not
enable a shared owner-credential fallback if a visitor cannot access Earth Engine.

## Official references

- [Earth Engine authentication and initialization](https://developers.google.com/earth-engine/guides/auth)
- [Earth Engine access and projects](https://developers.google.com/earth-engine/guides/access)
- [Google OAuth for web-server applications](https://developers.google.com/identity/protocols/oauth2/web-server)
- [Streamlit Google login configuration](https://docs.streamlit.io/develop/api-reference/user/st.login)
- [Streamlit access-token exposure](https://docs.streamlit.io/develop/api-reference/user/st.user)
