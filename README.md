# Predictive Dialer with Lead Management

This project provides a FastAPI-powered multiline predictive dialer that integrates with the [Telnyx](https://telnyx.com/) Call Control API and includes a lightweight lead management system.

## Features

- Campaign, lead, and agent management APIs backed by SQLite/SQLAlchemy.
- Predictive dialing logic that considers agent availability and configured concurrency limits.
- Telnyx integration for originating outbound calls and processing webhook events.
- Simple webhook handler that updates lead status, call outcomes, and agent availability.
- `.env` driven configuration for Telnyx credentials.

## Requirements

- Python 3.11+
- Telnyx account with a Call Control connection and outbound-enabled phone number

Install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env` (or otherwise export the environment variables) and fill in your Telnyx credentials.

## Running the API

```bash
uvicorn app.main:app --reload
```

The API exposes interactive documentation at `http://localhost:8000/docs`.

Set the `DATABASE_URL` environment variable to override the default SQLite database location (`sqlite:///./predictive_dialer.db`).

### Running with Docker Compose

Build and launch the API inside a container (the SQLite database will be persisted in `./data`):

```bash
docker compose up --build
```

Once the stack is running, visit `http://localhost:8000/docs` to explore the API. Shut it down with `docker compose down`.

## Key Endpoints

- `POST /campaigns` – create a dialing campaign.
- `POST /leads` / `POST /leads/bulk` – add individual or bulk leads.
- `GET /campaigns/{id}/summary` – view aggregate lead, agent, and call metrics for a campaign.
- `POST /agents` – register contact center agents.
- `POST /dialer/start` – trigger the predictive dialer for a campaign; calls are placed asynchronously until no dialable leads remain.
- `POST /dialer/stop` – cancel the background dialer task for a campaign.
- `GET /dialer/status/{campaign_id}` – inspect whether the dialer is currently running for a campaign.
- `POST /webhooks/telnyx` – endpoint that Telnyx should call with call-control events.
- `DELETE /leads/{lead_id}` – remove a lead from the campaign list.
- `GET /call-attempts` – inspect call attempt history with optional filters for campaign, lead, and active calls.

Refer to the generated OpenAPI schema for full request/response bodies.

## Notes

- The predictive dialer stores state in `predictive_dialer.db` (SQLite) by default.
- Telnyx webhooks must be reachable from Telnyx; in development, use a tunneling tool like `ngrok` to expose the `/webhooks/telnyx` endpoint.
- Enhance the predictive logic, compliance, and retry policies as required for production workloads.
