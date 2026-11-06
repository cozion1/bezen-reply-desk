# BEZEN Reply Desk

**A reply-handling workflow for sales and support teams: it reads what a customer is protecting, decides the next step, drafts it, and waits for a person to approve.**

Built for Vultr: Agent Rush 2026 (Challenge 2) and extended for the PayPal AI Hackathon 2026 · Team BEZEN (solo: Zion Cohen) · [bezenai.com](https://bezenai.com)

**Live:** https://108-61-171-113.sslip.io (press *Load sample inbox*)

## PayPal: a payment link only for those who are ready

An agent that sends a checkout link to every positive-sounding reply burns the customers who were only checking. "Thanks, I'll look at the price quote first" is not "Let's do it, how do I pay?". The Reply Desk tells them apart:

1. The model reads the reply and returns `pay_ready` together with `pay_evidence`, the customer's exact words that show readiness.
2. Code checks the words are really in the reply, then `payment_allowed()` in `app/critic.py` decides: only `ready_yes`, only the `answer_now` route, only with a price on the lead record, and **never** for intrusion, guilt or loss, or career risk.
3. If allowed, `app/paypal.py` creates a PayPal **Orders v2** checkout (sandbox) and logs it as a step. It is not sent.
4. A team member approves the draft; only then is the checkout link attached to the message.
5. *Check payment status* reads the order and captures it when the buyer has approved it. A paid order replaces the follow-up.

On the sample inbox of 10 replies, 2 get a PayPal link ("Let's do it. How do I pay…", "Can we start on the 1st?"); "Send me the price", "I'll look at the price quote first" and the three sensitive replies get none, each with the reason written in the log.

**AI used:** Vultr Serverless Inference, model `qwen3.8-27b`, for the reading and the draft. **PayPal used:** REST OAuth2 + Orders v2 (create, get, capture) in the sandbox. Set `PAYPAL_CLIENT_ID` and `PAYPAL_SECRET` (sandbox app) to enable it.

## The problem

A reply sorter labels a message *yes / no / question* and sends the next message. "Where did you get my email address?" looks like a question, so the bot answers it and keeps selling. "Send me the price" looks like a yes. The lead that gets burned never shows up in any report.

## The workflow

Every reply goes through six steps, each written to a log that the team can open:

| Step | What happens | Who |
|---|---|---|
| 1. Intake | A reply arrives with its lead record (company, stage, last message, what may be offered) | API or paste |
| 2. Read | The model names what the person is protecting, quoting their exact words, and what must not be done now | Vultr Serverless Inference |
| 3. Check | Code verifies the quote is word for word and the route is allowed. Failure → one retry with the reason; a second failure → a person, with no draft | Code, not a model |
| 4. Decide | One of four routes: answer now, nurture, human, close | Model + code rules |
| 5. Approve | A person approves, edits or rejects the draft. Nothing is sent without it | A person |
| 6. Follow up | A follow-up date is set by route (2 days, 10 days, 1 day, none) | Code |

Three states never get an automatic message, whatever the model says: **intrusion**, **guilt or loss**, **career risk**. That rule lives in `app/critic.py`.

## Architecture

```
Browser ──https──▶ Caddy (TLS) ──▶ FastAPI on a Vultr VM (Frankfurt, vc2-1c-2gb)
                                     │  app/pipeline.py  read → check → decide → draft → wait
                                     │  app/critic.py    verbatim-quote + routing rules (code)
                                     │  SQLite           replies, readings, every step
                                     └──▶ Vultr Serverless Inference (qwen3.8-27b, OpenAI-compatible API)
```

The VM is the control layer: it holds the queue and the state, runs the workflow, and calls the model. The model only reads; the code decides whether its reading may be used.

## Run it

```bash
pip install -r requirements.txt
export VULTR_INFERENCE_KEY=...      # Vultr Serverless Inference subscription key
export VULTR_MODEL=qwen3.8-27b
export PAYPAL_CLIENT_ID=... PAYPAL_SECRET=...   # optional, PayPal sandbox app
uvicorn app.main:app --reload       # http://localhost:8000
python -m pytest tests              # the checker and the workflow, without a model
```

Deploy on a fresh Ubuntu 24.04 Vultr VM: copy the folder to `/opt/reply-desk`, put the keys in `/opt/reply-desk/.env`, and run `sh deploy/setup.sh <your-hostname>`. It installs Caddy (automatic HTTPS), a systemd service and a firewall.

## API

| Method | Path | |
|---|---|---|
| POST | `/api/replies` | add a reply `{text, company, stage, last_message, allowed, price, offer}`; processing starts in the background |
| GET | `/api/replies`, `/api/replies/{id}` | list, or one reply with its reading and every step |
| POST | `/api/replies/{id}/approve` | `{message, by}`; a human-route reply must be written by the person |
| POST | `/api/replies/{id}/reject` | `{by, reason}` |
| POST | `/api/replies/{id}/payment` | refresh the PayPal order status (captures it when the buyer approved) |
| POST | `/api/demo/load` | reset and load 10 synthetic replies |

All sample companies and replies are fictional.

## License

MIT, see [LICENSE](LICENSE).
