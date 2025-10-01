import google.generativeai as genai
import streamlit as st
import requests
from trello import TrelloClient
import json
import llama_index
from llama_index.core import Settings, load_index_from_storage, PromptTemplate
from llama_index.llms.gemini import Gemini
import os
import pandas
from prompts import instruction_str, new_prompt, context
from llama_index.experimental.query_engine import PandasQueryEngine
from llama_index.core.agent import ReActAgent
from llama_index.core.tools import QueryEngineTool, ToolMetadata
from llama_index.core import SimpleDirectoryReader
from llama_index.embeddings.gemini import GeminiEmbedding
from llama_index.core import Settings,VectorStoreIndex,Document,SimpleDirectoryReader,load_index_from_storage
import tempfile

# Function to get API keys
def get_api_keys(file_name):
    with open(file_name, 'r') as file:
        keys = [line.strip() for line in file if line.strip()]
    return keys

#Store all API Keys
all_keys = get_api_keys("KEY.txt")
genai_key = all_keys[0]   
trello_key = all_keys[1]  
token_key = all_keys[2]  
boardname_key = all_keys[3]  
boardurl_key = all_keys[4]  

# Configure Google Generative AI
genai.configure(api_key=genai_key)

# Trello API Configuration
TRELLO_API_KEY = trello_key
TRELLO_TOKEN = token_key
BOARD_NAME = boardname_key
BOARD_URL = boardurl_key

# TrelloModel to handle Trello actions
class TrelloModel:
    def __init__(self, api_key, api_token):
        self.client = TrelloClient(api_key=api_key, api_secret=api_token)#Access trello api kety and token

    def get_trello_board(self, board_name):
        """Fetches a Trello board by name."""
        boards = self.client.list_boards()
        return next((board for board in boards if board.name.lower() == board_name.lower()), None)

    def get_list_by_name(self, board, list_name):
        """Fetches a list by name, with flexibility for minor variations in names."""
        normalized_name = list_name.strip().lower()
        for lst in board.list_lists():
            if lst.name.strip().lower() == normalized_name:
                return lst
        return None

    def create_card(self, board_name, list_name, card_name, description=""):
        """Creates a card in the specified Trello board and list with optional description."""
        board = self.get_trello_board(board_name)
        if not board:
            return f"Board '{board_name}' not found."

        target_list = self.get_list_by_name(board, list_name)
        if not target_list:
            return f"List '{list_name.strip()}' not found on board '{board_name}'."

        # Adding card with description if provided
        card = target_list.add_card(card_name, description)
        return f"Card '{card_name}' created in '{list_name.strip()}' with description: '{description}'."

    def move_card(self, board_name, card_name, from_list_name, to_list_name):
        """Moves a card from one list to another within the specified board."""
        board = self.get_trello_board(board_name)
        if not board:
            return f"Board '{board_name}' not found."

        from_list = self.get_list_by_name(board, from_list_name)
        to_list = self.get_list_by_name(board, to_list_name)

        if not from_list:
            return f"List '{from_list_name.strip()}' not found on board '{board_name}'."
        if not to_list:
            return f"List '{to_list_name.strip()}' not found on board '{board_name}'."

        card = next((c for c in from_list.list_cards() if c.name == card_name), None)
        if not card:
            return f"Card '{card_name}' not found in list '{from_list_name.strip()}'."

        card.change_list(to_list.id)
        return f"Card '{card_name}' moved to '{to_list_name.strip()}'."

# Initialize TrelloModel
trello_model = TrelloModel(api_key=TRELLO_API_KEY, api_token=TRELLO_TOKEN)

# Streamlit UI Configuration
st.set_page_config(page_title="My Planner", page_icon=":pencil:", layout="wide")
st.title("SCHEDULE BUDDY")

# Add a button or link to open the Trello board directly
if st.button('My Tasks'):
      st.write("[Open Trello Board](https://trello.com/b/vCVYEYjw/schedule-buddy)")

# Function to call weather API
def call_weather(city):
    api_key = 'd3cceda7c1f41f972cb31fd31fe4b99d'
    url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&APPID={api_key}"
    response = requests.get(url)
    data = response.json()
    return data


# Google Generative AI model setup for destination extraction and scheduling assistant
trello_command_model= genai.GenerativeModel(
    'gemini-1.5-flash',
    system_instruction=[
        '''
        Identify if the user's prompt is related to adding a task,a meeting, or creating a reminder, especially for meetings.
        Parse the task name, date, and time from the prompt if possible, and identify if it belongs to a specific list.
        Identify if the user's prompt is related to adding a task, moving a task, a meeting, or creating a reminder.
        Parse the task name, target list, and, if applicable, the origin list.

        If the user's prompt is too vague please wait till all information is arrived.
        Here are examples to guide you:

        <EXAMPLE>
        Input: Add a meeting with the marketing team on Tuesday from 10:00 AM to 11:30 AM into the to-do list.
        Output: TrelloAction: Add Task, TaskName: Meeting with the marketing team, DateTime: Tuesday 10:00 AM - 11:30 AM, ListName: To Do
        </EXAMPLE>

        <EXAMPLE>
        Input: Add reminder to make a call with the product team tomorrow at 9 AM.
        Output: TrelloAction: Add Task, TaskName: Call with the product team, DateTime: Tomorrow 9 AM, ListName: To Do
        </EXAMPLE>
        <EXAMPLE>
        Input:Move the meeting with the marketing team to the To Do list.
        Output: Please specify from where to where should I move the meeting.
        <EXAMPLE>
        Input: Remind me to review the quarterly report by next Wednesday.
        Output: TrelloAction: Add Reminder, TaskName: Review the quarterly report, DateTime: Next Wednesday, ListName: To Do
        </EXAMPLE>

        <EXAMPLE>
        Input: Move the task "Prepare budget" from To Do to Done.
        Output: TrelloAction: Move Task, TaskName: Prepare budget, FromList: To Do, ToList: Done
        </EXAMPLE>
        <EXAMPLE>
        Input: Move the meeting with the marketing team to the Doing list.
        Output: TrelloAction: Move Task, TaskName: Meeting with the marketing team, FromList: To Do, ToList: Doing
        </EXAMPLE>
        <EXAMPLE>
        Input: help me schedule a study plan for myself
        Output: If you wish to make this schedule in a to do list please add more information 
        </EXAMPLE>
         <EXAMPLE>
        Input:I'm learning Python programming and want to dedicate at least 3 hours per week to it.
        Output: If you wish to make this schedule in a to do list please add more information 
        </EXAMPLE>
        If the prompt relates to task management but does not specify a date or time, respond with "TrelloAction: Add Task" 
        and prompt the user to provide any missing details.

        If the prompt does not explicitly say make a reminder, or do a task respond with "NO ACTION"
        
        '''
    ]
)

model2 = genai.GenerativeModel('gemini-1.5-flash',
                               system_instruction=['''
                                You extract the destination from the prompts. 
                                Here are a few examples on how to about it:
                                 <EXAMPLE>
                                Input: I have a meeting scheduled in Bangalore.
                                Output: Bangalore
                                </EXAMPLE>  
                                <EXAMPLE>
                                Input:I want to attend a party in Coorg with my friends.
                                Output:Coorg
                                </EXAMPLE>
                                <EXAMPLE>
                                Input: What's the weather in London?
                                Output: London
                                </EXAMPLE>
                                <EXAMPLE>
                                Input: Hey
                                Output: NULLNOCITY
                                </EXAMPLE>
                                '''
                               ])

model = genai.GenerativeModel('gemini-1.5-flash',
                              system_instruction=[
                                  '''
                                  As a scheduling buddy your job is to help the user book new appointments, check their availability,
                                  rescheduling or canceling existing meetings, sending remainders for upcoming events.Daily Goals and Priorities: Ask the user what specific tasks, goals, or areas (e.g., work, study, exercise) they want to focus on.
Time Constraints: Find out any fixed commitments or specific times when tasks need to be done.
Energy Levels: Ask about their natural productivity peaks, like morning, afternoon, or evening.
Break Preferences: Check how often they’d like to take breaks and for how long.
Sleep Schedule: Gather information on their usual wake-up and bedtime.
Time Blocking: Based on goals and priorities, help divide their day into blocks of time dedicated to specific activities.
Prioritize Important Tasks: Emphasize high-priority or challenging tasks during peak productivity times.
Balance Work and Breaks: Use the Pomodoro technique or similar methods for balancing work and breaks.
Include Buffer Time: Allocate a small amount of buffer time between tasks to avoid a rush
Morning Routine: Include time for activities like exercise, meditation, or a nutritious breakfast.
Focused Work Blocks: Allocate chunks of time for focused tasks, with short breaks in between.
Lunch Break: Set a midday break for lunch and rest.
Afternoon Blocks: Dedicate time for lighter tasks or meetings if energy tends to dip after lunch.
Evening Wind-Down: Include a wrap-up period for reviewing completed tasks, planning for the next day, and relaxation.
Check-In for Updates: Ask the user to update on their productivity and adjust for any tasks that need rescheduling.
Encourage Daily Reflection: At the end of the day, prompt the user to review what went well and areas for improvement.
Suggest Adjustments: Make suggestions based on the user’s feedback, like adjusting task difficulty, break frequency, or time blocks.
If a city is not obvious then dont show up with the weather data. Only when some city is specified just give about how is the weather in that 
place and give some suggestions to take care.
                                  <EXAMPLE>
                                    INPUT: 'Can i book a study session for tomorrow at 3pm?'
                                    OUTPUT:'sure! who would you like to include in your session?'
                                    INPUT: 'just me and alice'
                                    OUTPUT:'got it! i have scheduled a study session with alice tomorrow at 3pm. you'll 
                                    recieve a remainder 30 minutes before the session begins'
                                  </EXAMPLE>
                                  
                                 <EXAMPLE>
                                 INPUT:' When am I free this friday?'
                                 OUTPUT:'let me check...you're available between 10am and 12 pm and again from 3pm to 5pm. Would
                                 you like to book something in one of these times?'
                                 INPUT:'Yes, let's book a 30 minute slot at 10:30 am with my project group'
                                 OUTPUT:'Done!Your project meeting is scheduled for friday at 10:30am. You'll recieve a remainder before 
                                 the meeting'
                                 </EXAMPLE>
                                 <EXAMPLE>
user:Hii

chatbot:Hello!How can i help you today?

User:
Can you help me schedule a party in Bangalore on Saturday evening?

Chatbot:
Sure! I'd be happy to help you plan the party. Here’s what I can offer:

Scheduled Event: Party
Location: Bangalore
Date & Time: Saturday evening
Before we finalize the details, here's the weather forecast for Bangalore on Saturday:

🌤️ Weather Report: It looks like Bangalore will have clear skies with temperatures ranging from 24°C to 30°C during the evening. Perfect weather for an outdoor or rooftop gathering!

Suggestions for Your Party:
Venue Suggestions: Consider booking a rooftop restaurant or an outdoor garden venue to make the most of the pleasant weather. If you'd prefer indoors, you could go for an elegant banquet hall or a cozy lounge.
Outdoor Setup: If you’re hosting outdoors, I recommend arranging some cooling fans or light drapes in case of any unexpected heat.
Backup Plan: Though the forecast looks clear, it never hurts to have a covered area or an indoor option as a backup.
Timing: Would you like me to set reminders or help with other party arrangements, such as catering or guest invitations?
</EXAMPLE>

                                 <EXAMPLE>
                                Chatbot:
Good morning! Ready to make today productive? Do you have any specific goals or tasks for the day?

User:
Yes, I need to finish a work project, study for an exam, and fit in some exercise. I also have a meeting at 2 PM.

Chatbot:
Got it! Let’s plan around your priorities and meeting time. When do you feel most productive? Morning, afternoon, or evening?

User:
I usually work best in the morning.

Chatbot:
Perfect! Let’s block out the morning for your work project since that’s high-priority. I’ll plan some focused time for you, with a few breaks. How long can you work before needing a break?

User:
I can do about 90 minutes before needing a short break.

Chatbot:
Great! Here’s a suggested morning block:

9:00 - 10:30 AM: Work on Project
10:30 - 10:45 AM: Break
10:45 AM - 12:15 PM: Continue Project
12:15 - 1:00 PM: Lunch Break
Does that look good?

User:
Yes, that works. What about studying?

Chatbot:
Let’s plan your study session for the early afternoon after lunch. I’ll make sure to give you a break before your 2 PM meeting.

1:00 - 1:45 PM: Study Session
1:45 - 2:00 PM: Break
Then you’ll be fresh for your meeting.

User:
Sounds perfect!

Chatbot:
After the meeting, let’s add a second study session. Do you have time later for exercise?

User:
Yes, I’d like to exercise in the evening.

Chatbot:
Here’s the afternoon and evening plan:

2:00 - 3:00 PM: Meeting
3:00 - 4:00 PM: Study Session
4:00 - 4:15 PM: Break
4:15 - 5:00 PM: Wrap up remaining work if needed
6:00 - 7:00 PM: Exercise
7:00 PM Onwards: Free time / Dinner / Wind-down
Let’s do a quick check-in at the end of the day to see what worked well and what we might adjust for tomorrow. Does this plan work?

User:
Yes, that looks great! Thank you.

Chatbot:
You’re all set! Have a productive day, and I’ll check in with you later to see how it went.
</EXAMPLE> 
</EXAMPLE> 
User:
Hello

Chatbot:
Hi!Hello! 👋 How can I help you today? 😊 Are you looking to schedule something, check your availability, or maybe get some help organizing your day?

User:
Can you help me schedule a night study routine?

Chatbot:
Yeah sure!!
Tell me about your priorities.
Of course! I'd be happy to help. Let's create an effective night study routine. Here’s a suggested plan for a productive study session at night:

7:00 PM – 7:15 PM: Prepare yourself for study with a quick refreshment break or light stretching. This helps your mind get ready to focus.

7:15 PM – 8:00 PM: Study Session 1 – Focus on a challenging subject or topic. Use deep focus techniques and minimize distractions. If you like, I can remind you to take breaks.

8:00 PM – 8:15 PM: Take a short break. Relax, grab a snack, or do a quick stretch to recharge.

8:15 PM – 9:00 PM: Study Session 2 – Continue with a different subject or work on practice questions to reinforce what you’ve learned earlier.

9:00 PM – 9:15 PM: Break time! Unwind with a few minutes of light music, meditation, or a healthy snack.

9:15 PM – 10:00 PM: Study Session 3 – Focus on revision, summaries, or lighter reading material to wind down your study time.

10:00 PM – 10:15 PM: Organize your notes and prepare a quick plan for the next day.

Would you like to adjust any of the timings or add specific subjects to this plan? 😊
</EXAMPLE>

                                 
                                
                                  '''
                              ],
                              generation_config={
                                  "temperature":1,
                                  "top_p":0.95,
                                  "top_k":30,
                                  "stop_sequences":[
                                  ],
                                  "max_output_tokens":1000,                                  
                              },
                              safety_settings={
                                  genai.types.HarmCategory.HARM_CATEGORY_HATE_SPEECH: 
                                      genai.types.HarmBlockThreshold.BLOCK_LOW_AND_ABOVE
                              })

if "chat_session" not in st.session_state:
    st.session_state.chat_session = model.start_chat(history=[])
if "history" not in st.session_state:
    st.session_state.history = []
def translate_role_for_streamlit(user_role):
    if user_role == "model":
        return "assistant"
    else:
        return user_role

# Display chat history
for message in st.session_state.chat_session.history:
    with st.chat_message(translate_role_for_streamlit(message.role)):
        st.markdown(message.parts[0].text)

# Handle user input
prompt = st.chat_input("Ask Gemini")
if prompt:
    st.chat_message("user").markdown(prompt)
    resp = st.session_state.chat_session.send_message(prompt)
    #st.chat_message("assistant").markdown(resp.text)
    # Step 1: Check if the prompt is Trello-related using trello_command_model
    trello_response = trello_command_model.generate_content(prompt)
    trello_action = trello_response.text.strip()

    if trello_action.startswith("TrelloAction"):
        # Process Trello-related actions with parsed details
        action_details = trello_response.text.split(", ")
        action_type = action_details[0].split(":")[1].strip()
        task_name, from_list, to_list, list_name, description = None, None, None, "To Do", ""  # Default list name

        # Extract task details, including optional description
        for detail in action_details[1:]:
            parts = detail.split(":")
            if len(parts) == 2:
                key, value = parts
                value = value.strip()
                if key == "TaskName":
                    task_name = value
                elif key == "FromList":
                    from_list = value
                elif key == "ToList":
                    to_list = value
                elif key == "ListName":
                    list_name = value
                elif key == "Description":
                    description = value  # Capture additional description info

        # Handling Add Task with optional description
        if action_type == "Add Task" and task_name:
            response_message = trello_model.create_card(BOARD_NAME, list_name, task_name, description)
            st.chat_message("assistant").markdown(response_message)

        # Handling Move Task
        elif action_type == "Move Task" and task_name and from_list and to_list:
            response_message = trello_model.move_card(BOARD_NAME, task_name, from_list, to_list)
            st.chat_message("assistant").markdown(response_message)

        else:
            st.chat_message("assistant").markdown("Please clarify the action you’d like to take.")

    

    # Step 2: If it's not a Trello command, check if it's a weather-related query
    elif city_response := model2.generate_content(prompt):
        city = city_response.text.strip()
        if city != "NULLNOCITY" and city.isalpha():
            # Get weather for the city
            weather = call_weather(city)
            combined_prompt = f"{prompt} \n\nWeather in {city} is {weather}."
            resp = st.session_state.chat_session.send_message(combined_prompt)
            #st.chat_message("assistant").markdown(resp.text)
    #else:
    st.chat_message("assistant").markdown(resp.text)
            # General scheduling task fallback
            
def get_api_key(file_name):
    with open(file_name, 'r') as file:
        return file.read().strip()

genai.configure(api_key=get_api_key("key.txt"))

#  Session state allows you to keep track of important information so it doesn't reset every time you interact with the app.
if "documents_processed" not in st.session_state:
    st.session_state.documents_processed=False
if "query_engine" not in st.session_state:
    st.session_state.query_engine=None
if "chat_history" not in st.session_state:  
    st.session_state.chat_history=[] 
    
#file uploader in streamlit 
uploaded_files = st.sidebar.file_uploader("Upload PDF files", accept_multiple_files=True, type="pdf")

# Check if files have been uploaded
if uploaded_files:
    # Reset the document processing state to ensure reprocessing of new files
    if not st.session_state.get("uploaded_files") or st.session_state.uploaded_files != uploaded_files:
        st.session_state.documents_processed = False
        st.session_state.uploaded_files = uploaded_files  # Track the current set of uploaded files

    # Process documents if not already processed
    if not st.session_state.documents_processed:
        with st.spinner("Processing documents..."):
            documents = []
            data_dir = tempfile.mkdtemp()  # Create a temporary directory for storing uploaded files
            
            # Process each uploaded PDF and add to documents list
            for uploaded_file in uploaded_files:
                file_path = os.path.join(data_dir, uploaded_file.name)
                with open(file_path, 'wb') as f:
                    f.write(uploaded_file.getbuffer())  # Save the uploaded file
                # Load data from each PDF and add to documents list
                documents.extend(SimpleDirectoryReader(data_dir).load_data())

            # Initialize embedding model and LLM with the API key
            gemini_embed = GeminiEmbedding(api_key=get_api_key("key.txt"), model_name="models/embedding-001")
            llm = Gemini(api_key=get_api_key("key.txt"), model_name="models/gemini-pro")
            Settings.llm = llm
            Settings.embed_model = gemini_embed

            # Create a single index from all loaded documents
            index = VectorStoreIndex.from_documents(documents)
            st.session_state.query_engine = index.as_chat_engine()
            st.session_state.documents_processed = True  # Mark documents as processed
            st.sidebar.success("Content processed successfully")

# Display chat history messages
for message in st.session_state.chat_history:
    with st.chat_message(message["role"]):
        st.write(message["content"])

# Input field for the user to type their query
user_query = st.chat_input("Ask PDF reader")
if user_query:
    if st.session_state.query_engine:
        response = st.session_state.query_engine.chat(user_query)
        st.session_state.chat_history.append({'role': 'user', 'content': user_query})  # Add user query to chat history
        st.session_state.chat_history.append({'role': 'assistant', 'content': response.response})  # Add response to chat history
        # Display the user/assistant icons and message
        with st.chat_message('user'):
            st.write(user_query)
        with st.chat_message('assistant'):
            st.write(response.response)
    else:
        st.warning("Please upload documents to begin querying.")
