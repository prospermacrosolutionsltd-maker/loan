# Prosper Macro Solutions Loan App

This is a Streamlit loan management app that runs locally and can be exposed to the internet using ngrok.

## Install dependencies

From the workspace root:

```bash
python -m pip install -r requirements.txt
```

## Run locally

```bash
python serve_app.py
```

Then open:

- Local URL: `http://localhost:8501`

## Access from anywhere

If `pyngrok` is installed, `serve_app.py` will create a public URL for the app.

- Open the `Public URL` shown in the terminal from any device with internet access.

## Access from your phone

### Option 1: Same Wi-Fi network

If your phone is on the same Wi-Fi network as the PC, open the local IP address:

```text
http://<PC_IP_ADDRESS>:8501
```

### Option 2: Anywhere using the public ngrok URL

Open the public URL shown by `serve_app.py` in your phone browser.

## Notes

- The app must be running while you access it.
- If you want a permanent deployment, consider Streamlit Cloud or a cloud VM.
