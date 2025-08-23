# 🚀 AI CHAT 2 - Advanced Russian Telegram AI Bot

[![Python](https://img.shields.io/badge/Python-3.9%2B-blue)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110%2B-green)](https://fastapi.tiangolo.com)
[![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4o-orange)](https://openai.com)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A production-ready, feature-rich Russian Telegram AI bot with GPT-4o integration, image generation, voice processing, and monetization capabilities.

## ✨ Key Features

### 🤖 **AI Capabilities**
- **GPT-4o Chat** - Advanced conversational AI with Russian language support
- **DALL-E 3 Image Generation** - Create stunning images from Russian text descriptions
- **Image Analysis** - Analyze and describe uploaded images with GPT-4o Vision
- **Voice Processing** - Speech-to-text and text-to-speech in Russian
- **Content Moderation** - Automatic content filtering with OpenAI moderation

### 🧙‍♂️ **AI Personas**
Chat with historical figures and experts:
- 🧠 **Albert Einstein** - Physics and science explanations
- 🎨 **Leonardo da Vinci** - Art and creative thinking
- 💼 **Steve Jobs** - Business and innovation advice
- 🧙‍♂️ **Socrates** - Philosophy and wisdom
- 👨‍🍳 **Gordon Ramsay** - Culinary expertise
- 🎭 **Shakespeare** - Literature and poetry

### 🎮 **Interactive Games**
- 🔮 **Mystical Quest** - AI-generated adventure stories
- 🧩 **Genius Puzzles** - Adaptive brain teasers
- 📚 **Story Creator** - Collaborative storytelling with AI
- 🎭 **Role Playing** - Character-based interactions
- 🎯 **Number Guessing** - Classic games with AI hints
- 🏙️ **Cities Game** - Geography challenge

### 🛠️ **Smart Tools**
- 🌤️ **Weather** - Accurate weather forecasts for any city
- 📚 **Wikipedia Search** - Quick access to Russian Wikipedia
- 🧮 **Calculator** - Mathematical computations with explanations
- 🔤 **Translator** - Multi-language translation
- ⏰ **Reminders** - Personal reminder system
- 📊 **QR Codes** - Generate QR codes for any text

### 💎 **Monetization System**
Three subscription tiers with Telegram Payments integration:
- 🔥 **Basic** (199₽/month) - 1000 messages, 50 images daily
- ⚡ **Pro** (399₽/month) - Unlimited messages, 200 images, priority
- 👑 **Elite** (799₽/month) - All features, unlimited images, exclusive support

### 📊 **Analytics & Admin**
- **User Analytics** - Detailed usage statistics and insights
- **Admin Panel** - User management and system monitoring
- **Revenue Tracking** - Subscription and payment analytics
- **Performance Metrics** - Response times and system health

## 🚀 Quick Start

### Prerequisites
- Python 3.9 or higher
- PostgreSQL database
- Telegram Bot Token (from [@BotFather](https://t.me/BotFather))
- OpenAI API Key

### Installation

1. **Clone the repository**
```bash
git clone https://github.com/yourusername/ai-chat-2-russian-bot.git
cd ai-chat-2-russian-bot
```

2. **Install dependencies**
```bash
pip install -r requirements.txt
```

3. **Configure environment**
```bash
cp .env.example .env
# Edit .env with your API keys and settings
```

4. **Set up database**
```bash
# Create PostgreSQL database (or use Railway.app)
createdb russian_bot_db
```

5. **Run the bot**
```bash
# Development
python3 main_ru.py

# Production
uvicorn main_ru:приложение --host 0.0.0.0 --port 8000
```

## 🛠️ Configuration

### Required Environment Variables

```env
# Telegram Configuration
TELEGRAM_BOT_TOKEN=your_bot_token_from_botfather
TELEGRAM_WEBHOOK_URL=https://yourdomain.com  # For production

# OpenAI Configuration
OPENAI_API_KEY=your_openai_api_key

# Database Configuration
DATABASE_URL=postgresql://user:password@host:port/database

# Admin Configuration
SUPER_ADMIN_ID=your_telegram_user_id
ADMIN_IDS=123456789,987654321  # Comma-separated admin IDs
```

### Optional Settings

```env
# Payment Configuration (for monetization)
TELEGRAM_PAYMENT_PROVIDER_TOKEN=your_payment_token

# External APIs
WEATHER_API_KEY=your_openweathermap_key

# Feature Toggles
ENABLE_PAYMENTS=true
ENABLE_VOICE=true
ENABLE_IMAGES=true
ENABLE_ANALYTICS=true

# Security
ENABLE_CONTENT_MODERATION=true
RATE_LIMIT_REQUESTS=100
```

## 🏗️ Architecture

The bot follows a modular architecture with clean separation of concerns:

```
russian_bot_package/
├── main_ru.py              # FastAPI application entry point
├── config_ru.py            # Configuration management
├── database_ru.py          # PostgreSQL database manager
├── telegram_ru.py          # Telegram API client
├── openai_ru.py            # OpenAI API integration
├── handlers_ru.py          # Message and callback handlers
├── payments_ru.py          # Payment processing
├── analytics_ru.py         # Analytics and metrics
├── admin_ru.py             # Admin panel functionality
└── requirements.txt        # Python dependencies
```

### Key Components

- **FastAPI** - High-performance async web framework
- **PostgreSQL** - Robust database with async support
- **Telegram Bot API** - Webhook-based integration
- **OpenAI API** - GPT-4o, DALL-E 3, and Whisper
- **Pydantic** - Configuration and data validation
- **Structlog** - Structured logging

## 🔧 Development

### Running Tests
```bash
python -m pytest tests/
```

### Code Quality
```bash
# Linting
flake8 .

# Type checking
mypy .

# Formatting
black .
```

### Docker Deployment
```bash
# Build image
docker build -t ai-chat-2 .

# Run container
docker run --env-file .env -p 8000:8000 ai-chat-2
```

## 📈 Deployment

### Railway (Recommended)
1. Connect your GitHub repository to Railway
2. Add PostgreSQL service
3. Set environment variables in Railway dashboard
4. Deploy automatically with git push

### Manual Server Deployment
```bash
# With Gunicorn
gunicorn main_ru:приложение --host 0.0.0.0 --port 8000 --workers 4 --worker-class uvicorn.workers.UvicornWorker

# With systemd service
sudo systemctl enable ai-chat-2
sudo systemctl start ai-chat-2
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Development Guidelines
- Follow Russian naming conventions for consistency
- Add comprehensive docstrings
- Include unit tests for new features
- Ensure backward compatibility
- Update documentation

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [OpenAI](https://openai.com) for GPT-4o and DALL-E 3 APIs
- [Telegram](https://telegram.org) for the Bot API
- [FastAPI](https://fastapi.tiangolo.com) for the excellent web framework
- Russian AI community for inspiration and feedback

## 📞 Support

- 📧 Email: support@yourdomain.com
- 💬 Telegram: [@yourusername](https://t.me/yourusername)
- 🐛 Issues: [GitHub Issues](https://github.com/yourusername/ai-chat-2-russian-bot/issues)

## 🎯 Roadmap

- [ ] Multi-language support (English, Spanish)
- [ ] Voice assistants integration
- [ ] Advanced AI models (GPT-5 when available)
- [ ] Mobile app companion
- [ ] API for third-party integrations
- [ ] Advanced analytics dashboard

---

**⭐ If you find this project useful, please give it a star!**

Made with ❤️ for the Russian AI community
