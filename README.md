# Open Shield App

This repository contains a Streamlit app for contract analysis using Gemini AI.

## Deployment to Streamlit Community Cloud

### 1. Push to GitHub
1. Commit your local changes.
2. Push the repository to GitHub.

### 2. Set up the app on Streamlit Cloud
1. Go to https://streamlit.io/cloud.
2. Sign in with your GitHub account.
3. Click `New app`.
4. Select this repository and the branch you pushed.
5. Set the main file to `app.py`.

### 3. Add the Gemini API key as a secret
1. Open the app settings in Streamlit Cloud.
2. Go to `Secrets`.
3. Add a secret named `GEMINI_API_KEY`.
4. Use your Gemini API key as the secret value.

### 4. Required files
- `app.py`
- `app_core.py`
- `requirements.txt`
- `packages.txt`

`requirements.txt` already includes the Python dependencies.
`packages.txt` is used by Streamlit Cloud to install system packages like `poppler-utils`.

### 5. Important
- Do not commit `.streamlit/secrets.toml`.
- The repository already includes `.streamlit/secrets.toml` locally for development, but it is ignored by Git.

## Local development

1. Create a `.env` file or use `st.secrets`.
2. Set `GEMINI_API_KEY` locally if needed.
3. Run:

```bash
streamlit run app.py
```
