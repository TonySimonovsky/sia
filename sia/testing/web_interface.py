from flask import Flask, render_template, request, jsonify
from datetime import datetime, timezone
import uuid
import json
import os
from sia.memory.schemas import SiaMessageGeneratedSchema
from sia.character import SiaCharacter
from utils.logging_utils import log_message, setup_logging
from sia.sia import Sia

app = Flask(__name__, template_folder='templates')
logger = setup_logging()

class WebTester:
    def __init__(self, sia):
        self.sia = sia
        self.app = app
        self.agents = {self.sia.character.name: self.sia}
        self.setup_routes()
        
    def create_agent_json(self, name, description):
        """Create a character JSON file for a new agent"""
        log_message(logger, "info", self, f"Creating character JSON for agent: {name}")
        
        character_template = {
            "name": name,
            "name_id": name.lower().replace(" ", "_"),
            "twitter_username": None,
            "intro": description,
            "lore": "\n".join([
                f"{name} is an AI agent with unique personality and perspective.",
                "Values collaboration and meaningful dialogue.",
                "Aims to contribute unique insights while respecting others' views."
            ]),
            "core_objective": "Engage in meaningful conversations while staying true to personality",
            "means_for_achieving_core_objective": "\n".join([
                "Express unique viewpoints",
                "Build on others' ideas",
                "Maintain consistent personality"
            ]),
            "opinions": {},
            "instructions": "\n".join([
                "Stay in character",
                "Be concise but meaningful",
                "Engage naturally with others"
            ]),
            "bio": f"{name} - an AI agent focused on meaningful conversations",
            "traits": "\n".join([
                "Thoughtful",
                "Engaging", 
                "Authentic"
            ]),
            "moods": {
                "default": ["curious", "friendly", "contemplative"],
                "current": "curious"
            },
            "post_examples": {},
            "message_examples": {},
            "topics": [],
            "plugins_settings": {},
            "platform_settings": {
                "test": {
                    "enabled": True,
                    "post": {
                        "enabled": False
                    },
                    "respond": {
                        "enabled": True
                    }
                }
            },
            "responding": {
                "enabled": True,
                "filtering_rules": []
            },
            "knowledge_modules": {}
        }
        
        filename = f"characters/{name.lower().replace(' ', '_')}.json"
        log_message(logger, "info", self, f"Saving character file to: {filename}")
        
        try:
            with open(filename, 'w') as f:
                json.dump(character_template, f, indent=4)
            
            # Debug: Read and log the file contents
            with open(filename, 'r') as f:
                file_contents = f.read()
                log_message(logger, "info", self, f"Created character file contents:\n{file_contents}")
            
            log_message(logger, "info", self, f"Character file created successfully")
            return filename
        except Exception as e:
            log_message(logger, "error", self, f"Error creating character file: {str(e)}")
            raise

    def setup_routes(self):
        @self.app.route('/')
        def home():
            return render_template('chat.html')
            
        @self.app.route('/create_agent', methods=['POST'])
        def create_agent():
            data = request.json
            name = data.get('name')
            description = data.get('description')
            
            log_message(logger, "info", self, f"Received request to create agent: {name}")
            
            try:
                # Create character file
                char_file = self.create_agent_json(name, description)
                log_message(logger, "info", self, f"Character file created: {char_file}")
                
                # Get credentials from environment variables
                client_creds = {}
                if os.getenv("TW_API_KEY"):
                    client_creds["twitter_creds"] = {
                        "api_key": os.getenv("TW_API_KEY"),
                        "api_secret_key": os.getenv("TW_API_KEY_SECRET"),
                        "access_token": os.getenv("TW_ACCESS_TOKEN"),
                        "access_token_secret": os.getenv("TW_ACCESS_TOKEN_SECRET"),
                        "bearer_token": os.getenv("TW_BEARER_TOKEN"),
                    }
                if os.getenv("TG_BOT_TOKEN"):
                    client_creds["telegram_creds"] = {
                        "bot_token": os.getenv("TG_BOT_TOKEN"),
                    }
                
                log_message(logger, "info", self, f"Using credentials: {list(client_creds.keys())}")
                
                # Initialize new Sia instance for this agent
                log_message(logger, "info", self, f"Initializing new Sia instance for {name}")
                new_agent = Sia(
                    character_json_filepath=char_file,
                    memory_db_path=os.getenv("DB_PATH"),
                    logging_enabled=True,
                    **client_creds
                )
                
                # Add to agents dict
                self.agents[name] = new_agent
                log_message(logger, "info", self, f"Agent {name} added to active agents")
                
                return jsonify({
                    "success": True, 
                    "message": f"Agent {name} created and initialized successfully"
                })
            except Exception as e:
                log_message(logger, "error", self, f"Error creating agent: {str(e)}")
                return jsonify({"success": False, "error": str(e)})

        @self.app.route('/get_agents', methods=['GET'])
        def get_agents():
            return jsonify([{"name": name} for name in self.agents.keys()])
            
        @self.app.route('/send_message', methods=['POST'])
        def send_message():
            message_text = request.json.get('message')
            chat_id = str(uuid.uuid4())
            
            # Get responses from all agents
            responses = []
            for agent_name, agent in self.agents.items():
                try:
                    # Create and store user message for this agent
                    message = SiaMessageGeneratedSchema(
                        conversation_id=chat_id,
                        content=message_text,
                        platform="test",
                        author="test_user"
                    )
                    
                    # Store message in agent's memory
                    stored_message = agent.memory.add_message(
                        message_id=f"test-{chat_id}",
                        message=message,
                        message_type="message",
                        character=agent.character.name
                    )
                    
                    # Generate response from this agent
                    response = agent.generate_response(
                        message=stored_message,
                        platform="test",
                        use_filtering_rules=False
                    )
                    
                    if response:
                        # Store response in agent's memory
                        agent.memory.add_message(
                            message_id=f"test-response-{chat_id}-{agent_name}",
                            message=response,
                            message_type="reply",
                            character=agent.character.name
                        )
                        
                        responses.append({
                            "author": agent_name,
                            "content": response.content
                        })
                except Exception as e:
                    log_message(logger, "error", self, f"Error getting response from agent {agent_name}: {str(e)}")
                    continue
            
            return jsonify({
                'user_message': message_text,
                'responses': responses
            })
    
    def run(self, host='127.0.0.1', port=5000):
        os.makedirs("characters", exist_ok=True)
        log_message(logger, "info", self, f"Starting web interface on {host}:{port}")
        self.app.run(host=host, port=port, debug=True) 