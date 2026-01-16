# 🏭 Sistema ERP de Inventarios: Distribuidora de Acabados

![Status](https://img.shields.io/badge/Estado-Producción-brightgreen)
![Python](https://img.shields.io/badge/Python-3.12-blue)
![Streamlit](https://img.shields.io/badge/Frontend-Streamlit-red)
![Database](https://img.shields.io/badge/Database-Google%20Sheets-green)
![Storage](https://img.shields.io/badge/Storage-ImgBB-orange)

Sistema de gestión de inventarios en la nube (Cloud ERP) diseñado a medida para la administración de productos de acabados de construcción (Marcas **Celima, Trebol**, etc.). 

El sistema resuelve el problema de la **persistencia de datos y accesibilidad remota** integrando múltiples APIs gratuitas para operar sin costos de servidor.

## 🚀 Demo en Vivo

👉 **[Acceder al Sistema aquí](https://inventario-ledisa.streamlit.app/)**
*(Nota: Se requiere contraseña de acceso para editar datos)*

## 📸 Capturas de Pantalla

| Dashboard de Stock | Registro con Foto |
|:---:|:---:|
| ![Dashboard](https://i.ibb.co/SX6qj0TP/image.png) | ![Registro](https://i.ibb.co/C3st9ZwJ/image.png) |
*(El sistema visualiza KPIs financieros y stock físico en tiempo real)*

## 🛠️ Arquitectura Técnica

El proyecto utiliza una arquitectura **Serverless** desacoplada:

* **Frontend:** `Streamlit` (Interfaz Web Reactiva).
* **Backend Logic:** `Python` (Pandas para manipulación de datos).
* **Base de Datos:** `Google Sheets API` (Persistencia de datos estructurados).
* **Almacenamiento de Medios:** `ImgBB API` (Hosting de imágenes permanente).
* **Autenticación:** Sistema de Login simple basado en secretos de entorno.

### Flujo de Datos
```mermaid
graph LR
A[Usuario Móvil] -- HTTPS --> B(Streamlit Cloud)
B -- Read/Write JSON --> C{Google Sheets}
B -- Upload Image --> D[ImgBB Cloud]
D -- Return URL --> B
B -- Generate .xlsx --> E[Reporte Excel]