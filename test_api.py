import google.generativeai as genai
import os

# PEGA TU "NUEVA" API KEY AQUÍ DIRECTAMENTE PARA PROBAR
API_KEY = "AIzaSyAAZ-rBXQLnCKNbyaGDvTx7q3PMG--xths" 

genai.configure(api_key=API_KEY)

modelos_a_probar = [
    'gemini-1.5-flash',
    'gemini-2.0-flash-exp', # A veces el experimental tiene cuota separada
    'gemini-pro'
]

print(f"🔬 Diagnosticando API Key...")

for modelo in modelos_a_probar:
    try:
        print(f"\n👉 Intentando conectar con: {modelo}...")
        model = genai.GenerativeModel(modelo)
        response = model.generate_content("Responde solo con la palabra: VIVO")
        print(f"✅ ÉXITO: {modelo} está VIVO. Respuesta: {response.text}")
        break # Si uno funciona, ya sabemos que la llave sirve
    except Exception as e:
        print(f"❌ FALLO {modelo}: {e}")

print("\n--- DIAGNÓSTICO FINAL ---")