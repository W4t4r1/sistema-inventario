import google.generativeai as genai
import os

# Pega tu llave AIza... aquí
API_KEY = "AIzaSyAAZ-rBXQLnCKNbyaGDvTx7q3PMG--xths" 

genai.configure(api_key=API_KEY)

print("🔍 Buscando modelos disponibles para tu llave...")

try:
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            print(f"✅ DISPONIBLE: {m.name}")
            
except Exception as e:
    print(f"❌ Error al listar: {e}")