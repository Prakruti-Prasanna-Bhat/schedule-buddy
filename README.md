# Schedule Buddy 

**Schedule Buddy** is a Streamlit-powered planner that integrates **Google Generative AI (Gemini)** with **Trello** for seamless task and schedule management. It also provides weather-aware suggestions and supports conversational querying of uploaded PDFs.  

## Some Features
- **Task Management with Trello**  
  - Create tasks, reminders, and meetings directly from natural language.  
  - Move tasks across lists on your Trello board.  
  - Open Trello board from within the app.  

- **Smart Scheduling with Gemini**  
  - Conversational scheduling assistant powered by Google Generative AI.  
  - Helps plan daily routines, meetings, and study schedules.  
  - Suggests optimal time slots based on context.  

- **Weather-Aware Suggestions**  
  - Fetches real-time weather data using the OpenWeather API.  
  - Incorporates weather updates into event planning.  

- **PDF Upload & Conversational Querying**  
  - Upload multiple PDF files.  
  - Extract and query content conversationally using **LlamaIndex** + **Gemini embeddings**.  

## System Requirements
- Python 3.10+  
- Streamlit  
- google-generativeai  
- trello  
- requests  
- pandas  
- llama-index

## API Keys
- **You’ll need a KEY.txt file (not included in repo). Each line should contain:**
  - Google Generative AI API Key
  - Trello API Key
  - Trello Token
  - Trello Board Name
  - Trello Board URL
  - Weather API Key
- **Example KEY.txt**
