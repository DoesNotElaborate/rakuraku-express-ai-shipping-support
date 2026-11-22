# RakuRaku local demo

This is a working local policy retrieval and drafting prototype using only the included fictional PDF. On the original workspace computer, a free local Ollama Qwen3 4B Instruct model is installed under `work/ollama`. The app uses live LLM inference for complete routine cases and a deterministic safety gate for cases with missing or invalid evidence. No cloud account or paid service is used. The UI labels the route used for each case.

## Run

On the original Windows workspace, from this directory:

```powershell
.\Start_Demo.ps1
```

Open `http://127.0.0.1:8765`. The server binds only to localhost and performs no external action. If PowerShell blocks script execution, run the commands in the script manually; do not weaken machine-wide execution settings.

For use on another machine, install Python 3 and `pypdf`, plus a free local OpenAI-compatible model server. Set `RAKURAKU_LLM_URL` to its local chat completions endpoint and `RAKURAKU_LLM_MODEL` to the loaded model name, then run `python rakuraku_app.py`. The app rejects non-local endpoints. The exact CREATE prompt is included. A local LLM output still needs human review; inspect citations and calculations during testing.

The provided case defaults to a fictional standard late delivery. Use the associated test plan for the six scenarios. The UI does not send messages, approve credits, or alter tickets.
