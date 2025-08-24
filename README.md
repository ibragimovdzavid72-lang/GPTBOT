# Telegram Bot with ChatGPT-4o Integration

This is a Telegram bot built with Python that integrates with OpenAI's ChatGPT-4o model. The bot is designed to be deployed on Railway with PostgreSQL database support.

## Features

- Telegram bot integration using python-telegram-bot
- ChatGPT-4o integration for natural language processing
- PostgreSQL database for storing chat history and user information
- Health check endpoint for Railway deployment
- Easy deployment configuration

## Prerequisites

- Python 3.8+
- Telegram Bot Token (from @BotFather on Telegram)
- OpenAI API Key
- PostgreSQL database

## Local Development

1. Clone the repository
2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Create a `.env` file with your credentials:
   ```env
   TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
   OPENAI_API_KEY=your_openai_api_key_here
   DATABASE_URL=postgresql://user:password@localhost/dbname
   ```
5. Run the application:
   ```bash
   python app.py
   ```

## Deployment to Railway

1. Create a new project on Railway
2. Connect your GitHub repository
3. Set the following environment variables in Railway:
   - `TELEGRAM_BOT_TOKEN`
   - `OPENAI_API_KEY`
   - `DATABASE_URL`
4. Railway will automatically deploy the application using the `railway.json` configuration

## Project Structure

- `app.py`: Main application file with FastAPI setup
- `telegram_bot.py`: Telegram bot implementation
- `database.py`: Database models and connection
- `requirements.txt`: Python dependencies
- `railway.json`: Railway deployment configuration
- `.env`: Environment variables (not committed to git)
- `.gitignore`: Git ignore file

## Dependencies

- python-telegram-bot==21.0.1
- openai==1.3.6
- fastapi==0.110.0
- uvicorn==0.29.0
- sqlalchemy==2.0.23
- psycopg2-binary==2.9.9
- python-dotenv==1.0.0