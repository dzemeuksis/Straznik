# Strażnik: Incident Reporting Demo

Strażnik is a simplified demo web application for reporting safety incidents. It leverages AI-powered image description and personalized safety advice based on user-provided photos and location data. This project was developed during the [CIVIL42 hackathon](https://civil42.pl/) organized by Institute 42.

## Features
- User profile capturing basic information (age, health, capabilities)
- Incident reporting by uploading images and providing device GPS location
- Automated image analysis using OpenAI vision models to generate concise descriptions
- Personalized safety advice tailored to the user profile and incident context
- Interactive map view of reported incidents
- User-specific incident history and detail pages
- JSON API endpoint (`/api/incidents`) for incident data consumption

## Limitations
> **Note:** This is a proof-of-concept demo, not a production-ready application.
- No operator or dispatcher dashboard
- No incident severity, weight, or urgency scoring
- Simplified data storage in local JSON files (no database)
- Basic cookie-based user identification (no authentication/authorization)
- No real-time updates or concurrency control
- Limited error handling and validation

## Getting Started

### Prerequisites
- Python 3.10 or newer
- An OpenAI API key (set as the `OPENAI_API_KEY` environment variable)

### Installation
1. Clone this repository:
   ```bash
   git clone <repository-url>
   cd <repository-directory>
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. (Optional) Override the AI model:
   ```bash
   export AI_MODEL="gpt-4.1-mini-2025-04-14"
   ```
4. Run the application:
   ```bash
   python app.py
   ```
5. Open your browser and navigate to `http://localhost:5000`

## Configuration
Environment variables:
- `OPENAI_API_KEY` (required): Your OpenAI API key.
- `AI_MODEL` (optional): The OpenAI model to use (default: `gpt-4.1-mini-2025-04-14`).

## Project Structure
```
.
├── app.py              # Main Flask application
├── requirements.txt    # Python dependencies
├── data/               # JSON storage for users, reports, incidents
├── prompts/            # AI prompt templates (image description, advice)
├── templates/          # Jinja2 HTML templates
├── static/             # Static assets (logo, CSS, JS)
└── uploads/            # Uploaded image files
```

## API Reference
- **GET** `/api/incidents`
  - Returns a JSON array of incidents and their latest report details.

## Potential Future Improvements
- Operator interface for triage and incident management
- Autoassessment of the credibility of the report
- Incident severity and urgency scoring
- Persistent storage using a database (e.g., PostgreSQL)
- User authentication and authorization
- Real-time updates (WebSockets)
- Enhanced validation and error handling

## Acknowledgments
Developed as part of the [CIVIL42 hackathon](https://civil42.pl/) organized by Institute 42.

## License
This is a demo project, created entirely with the OpenAI Codex CLI agent and the o4-mini model. It is licensed under MIT, but I'm open to feedback if you have any concerns about this.
