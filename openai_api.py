import openai
from settings import OPENAI_API_KEY

openai.api_key = OPENAI_API_KEY

def ask_gpt(messages):
    response = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=messages
    )
    return response["choices"][0]["message"]["content"]

def generate_image(prompt):
    response = openai.Image.create(
        model="dall-e-3",
        prompt=prompt,
        size="1024x1024"
    )
    return response["data"][0]["url"]
