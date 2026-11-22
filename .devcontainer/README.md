# Medical Claim AI: live demo in GitHub Codespaces

The app is starting in the **terminal** below. The first start builds everything (about 10 minutes),
and later starts take about a minute.

When it's ready, the terminal prints:

- the address, `https://<codespace-name>-80.app.github.dev`
- an **admin** login and an **employee** login, generated for this codespace

To try it, run `bash .devcontainer/make-sample-bill.sh` in the terminal. It writes `sample-bill.png`, which you
download from the file explorer (right-click → Download). Open the address, sign in on the employee page and
upload the bill. Then sign in on the admin page to review it, with the extracted fields, the agent's steps
and the cited policy evidence.

**Automatic decisions are on** in this demo. A bill that passes the policy check with no red flags is approved,
partially approved or rejected on its own. A flagged bill goes to the admin's review queue with the reason:
duplicate, patient name mismatch, future date, unreadable or uncertain OCR, conflicting policies, missing
pre-authorisation, or confidence below 85%.

**To switch on GPT** (optional; needs a paid OpenAI API key from platform.openai.com):
1. On GitHub: **Settings → Codespaces → Secrets → New secret**. Name `OPENAI_API_KEY`, paste the key, and
   under *Repository access* choose `medical-claim-ai`. (`ANTHROPIC_API_KEY` works too.)
2. Back in the codespace, accept the "reload to apply secrets" prompt, or run `bash .devcontainer/start.sh`.

GPT then cross-checks every decision. It can only lower an amount or send the claim to a person, never
raise it. The key is stored by GitHub, not in the code.

**To share it** (for example in an interview), open the **PORTS** tab, right-click port **80**, and choose
**Port Visibility → Public**. Anyone with the link can then open it while the codespace is running.

**Free hours:** a personal GitHub account includes 120 core hours a month, which is 60 hours on this 2-core
machine. The codespace stops by itself after 30 minutes without activity. Stop it yourself from
github.com/codespaces when you're done. Your data is kept until you delete the codespace.

If the logins scroll away: `sudo cat /root/medical-claim-ai-credentials.txt`
To restart the app: `bash .devcontainer/start.sh`
