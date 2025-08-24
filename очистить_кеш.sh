#!/bin/bash
# очистить_кеш.sh - Скрипт для очистки Python кеша

echo "🧹 Очистка Python кеша..."

# Счетчики для статистики
pycache_count=$(find . -type d -name "__pycache__" 2>/dev/null | wc -l)
pyc_count=$(find . -name "*.pyc" 2>/dev/null | wc -l)
pyo_count=$(find . -name "*.pyo" 2>/dev/null | wc -l)

echo "Найдено:"
echo "- __pycache__ директорий: $pycache_count"
echo "- .pyc файлов: $pyc_count"
echo "- .pyo файлов: $pyo_count"

# Очистка (согласно памяти о Python Cache Management)
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -name "*.pyc" -delete 2>/dev/null || true
find . -name "*.pyo" -delete 2>/dev/null || true

echo "✅ Кеш очищен!"

# Проверка
remaining=$(find . -name "*.pyc" -o -name "*.pyo" -o -type d -name "__pycache__" 2>/dev/null | wc -l)
if [ $remaining -eq 0 ]; then
    echo "✅ Проверка пройдена - кеш полностью удален"
else
    echo "⚠️ Остались файлы кеша: $remaining"
fi