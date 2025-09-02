# Telegram AI Agent v2

A Telegram bot powered by OpenAI's GPT models with advanced features including prompt suggestion and interaction logging.

## Features

- AI-powered conversations using OpenAI GPT models
- Prompt suggestion capability with `/suggest_prompt` command
- Interaction logging to PostgreSQL database
- Image generation with `/art` command
- Interactive menu with quick access buttons
- Statistics viewing with `/stats` command
- Help information with `/help` command
- Admin panel with bot management commands
- Personalized greetings for users
- AI model selection via `/mode` command
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
OPENAI_MODEL=gpt-4o
TEMPERATURE=0.8
REQUEST_TIMEOUT=30
ADMINS=123456789,987654321
MAX_TG_REPLY=3500
```

For detailed instructions on obtaining these tokens, see [telegram_bot_instruction_ru.md](telegram_bot_instruction_ru.md) (in Russian).

## Usage

After starting the bot, you can use the following commands:

- `/start` - Open the main menu with buttons
- `/help` - Show help information
- `/stats` - Show usage statistics
- `/suggest_prompt` - Get a prompt suggestion based on interaction history
- `/art` - Create an image based on a description
- `/mode MODEL` - Change AI model (e.g., `/mode gpt-4o`)

### Admin Commands

Additional commands are available for administrators:

- `/admin` - Access the admin panel with all admin commands
- `/admin_stats` - Show user and message statistics
- `/errors` - Show recent errors
- `/bot_on` - Enable the bot
- `/bot_off` - Disable the bot

Administrators also have access to a special "👑 Admin Panel" button in the main menu.

The main menu includes buttons:
- 📊 Statistics - View usage statistics
- 🎨 Create Art - Image generation feature
- ⚙️ Settings - Bot settings (in development)
- 🧠 Smart Chat - AI conversation mode

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
5. Copy the database connection string from the Postgres variables (DATABASE_URL) to your application's environment variables (GPTBOT → Variables)
6. Create the database tables using one of the following methods:

   **Method 1: Using the initialization script (recommended)**
   ```bash
   python init_db.py
   ```
   
   **Method 2: Using Railway terminal**
   ```bash
   psql "postgresql://USER:PASSWORD@HOST:5432/railway" -f schema.sql
   ```
   
   **Important:** Railway Postgres is only accessible from within Railway (via postgres.railway.internal). Local testing will not work - the connection will be refused.

7. Deploy the application

### Database Initialization

To create the required tables in the database, use the `init_db.py` script:

```bash
python init_db.py
```

This script connects to the database specified in the DATABASE_URL environment variable and executes the SQL script from the `schema.sql` file, creating the `logs`, `bot_config`, and `bot_status` tables.

**Important:** If the tables already exist, the script will not attempt to recreate them.

## Project Structure

```
telegram_ai_agent_v2/
├── app/                 # Main application code
│   ├── __init__.py
│   ├── ai.py           # OpenAI integration
│   ├── config.py       # Configuration management
│   ├── main.py         # Main bot logic
│   ├── admin.py        # Admin panel
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
