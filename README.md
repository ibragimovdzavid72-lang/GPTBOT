# Telegram AI Agent v2

A Telegram bot powered by OpenAI's GPT models with advanced features including prompt suggestion and interaction logging.

## Features

- AI-powered conversations using OpenAI GPT models
- Prompt suggestion capability with `/suggest_prompt` command
- Interaction logging to PostgreSQL database
- Interactive menu with quick access buttons
- Statistics viewing with `/stats` command
- Help information with `/help` command
- Configurable through environment variables
- Ready for deployment on platforms like Heroku or Railway

## Prerequisites

- Python 3.9 or higher
- PostgreSQL database
- OpenAI API key
- Telegram Bot token

## Installation

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd telegram_ai_agent_v2
   ```

2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Set up environment variables (see [Configuration](#configuration))

5. Set up PostgreSQL database:
   ```bash
   createdb telegram_bot
   psql -d telegram_bot -f schema.sql
   ```

6. Run the bot:
   ```bash
   python -m app.main
   ```

## Configuration

Create a `.env` file in the project root with the following variables:

```
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
OPENAI_API_KEY=your_openai_api_key
DATABASE_URL=postgresql://postgres:password@localhost:5432/telegram_bot
OPENAI_MODEL=gpt-3.5-turbo
TEMPERATURE=0.8
REQUEST_TIMEOUT=30
MAX_TG_REPLY=3500
```

For detailed instructions on obtaining these tokens, see [telegram_bot_instruction_ru.md](telegram_bot_instruction_ru.md) (in Russian).

## Usage

After starting the bot, you can use the following commands:

- `/start` - Open the main menu with buttons
- `/help` - Show help information
- `/stats` - Show usage statistics
- `/suggest_prompt` - Get a prompt suggestion based on interaction history

The main menu includes buttons:
- 🧠 Smart Chat - AI conversation mode
- 🎨 Create Art - Image generation feature (in development)
- 📊 Statistics - View usage statistics
- ❓ Help - Help information

## Documentation (Russian)

For Russian-speaking users, we provide comprehensive documentation in Russian:

- [README_RU.md](README_RU.md) - Main documentation in Russian
- [telegram_bot_instruction_ru.md](telegram_bot_instruction_ru.md) - Step-by-step setup instructions
- [FEATURES_RU.md](FEATURES_RU.md) - Detailed feature description in Russian
- [FAQ_RU.md](FAQ_RU.md) - Frequently asked questions in Russian

## Deployment

This bot is ready for deployment on platforms that support Procfile-based applications (like Heroku or Railway). The Procfile is already included in the repository.

### Deployment on Railway

1. Create a project on [Railway](https://railway.app/)
2. Connect your GitHub repository or upload the code manually
3. Add environment variables from the `.env.example` file
4. Add a PostgreSQL database through Railway
5. Copy the database connection string (DATABASE_URL) to your application's environment variables
6. Create the database tables by running the initialization script:
   ```bash
   python init_db.py
   ```
7. Deploy the application

### Database Initialization

To create the required tables in the database, use the `init_db.py` script:

```bash
python init_db.py
```

This script connects to the database specified in the DATABASE_URL environment variable and executes the SQL script from the `schema.sql` file, creating the `logs` and `bot_config` tables.

## Project Structure

```
telegram_ai_agent_v2/
├── app/                 # Main application code
│   ├── __init__.py
│   ├── ai.py           # OpenAI integration
│   ├── config.py       # Configuration management
│   ├── main.py         # Main bot logic
│   └── suggest.py      # Prompt suggestion functionality
├── .env.example         # Example environment variables
├── .gitignore
├── Procfile             # Deployment configuration
├── README.md
├── README_RU.md         # Russian documentation
├── init_db.py           # Database initialization script
├── FEATURES_RU.md       # Russian feature description
├── FAQ_RU.md            # Russian FAQ
├── requirements.txt     # Python dependencies
├── schema.sql           # Database schema
└── telegram_bot_instruction_ru.md  # Detailed setup instructions (Russian)
```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
