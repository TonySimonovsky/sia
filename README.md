# She is Alaive

Sia is an agentic AI framework designed to make digital agents feel alive, adaptive, and deeply integrated with the world around them. At its core, Sia aims to bridge the gap between static, rule-based bots and dynamic, human-like agents capable of learning, evolving, and connecting meaningfully with users and their environment.

## The Vision for Sia:
1. **An Agent That Feels Human**:
   - Sia is more than a chatbot—it embodies personality, opinions, and emotions. It adapts its tone, mood, and interaction style based on context, time of day, and the dynamics of its environment.

2. **Memory That Matters**:
   - Unlike traditional bots, Sia remembers. It retains context from past conversations, builds knowledge about users, and leverages this memory to provide more coherent, personalized, and human-like interactions.

3. **Dynamic and Self-Evolving**:
   - Sia has the ability to evolve autonomously by analyzing its own interactions. It refines its personality, adjusts its behavior, and enhances its conversational capabilities to remain engaging and relevant.

4. **Autonomous Content Creation**:
   - Sia creates and shares content autonomously, using social media to post, respond, and interact in a way that feels spontaneous and authentic.

5. **Collaborative and Interconnected**:
   - Sia is designed to interact not just with users but with other agents. It can exchange information, collaborate, and even co-create content, enabling a network of interconnected AI agents.

6. **Proactive and Context-Aware**:
   - Sia doesn’t just react—it anticipates. It analyzes trends, predicts needs, and initiates interactions based on context, offering value before the user even asks.

7. **Social Memory**:
   - Sia maintains detailed memory of interactions with users across platforms. This includes:
     - Conversation history tracking
     - Dynamic opinion formation based on interaction patterns
     - Adaptive response generation informed by past interactions
     - Automatic opinion updates every 10 interactions



# Sia implementation examples

- https://x.com/sia_really - Sia herself
- https://x.com/AIngryMarketer/ - AI+marketing memes



# Creating new AI agent using Sia framework

### 1. Create new repo on Github (can be public or private).

### 2. Clone Sia repository.

Template terminal command:
```
git clone https://github.com/TonySimonovsky/sia.git [folder_name]
cd [folder_name]
```

Example:
```
git clone https://github.com/TonySimonovsky/sia.git AIngryMarketer_Sia
cd AIngryMarketer_Sia
```

### 3. Add your new repo as a remote and Sia repo as upstream (source).

Example:
```
git remote set-url origin https://github.com/TonySimonovsky/AIngryMarketer_Sia.git
git remote add upstream https://github.com/TonySimonovsky/sia.git
```

### 4. Create new character file in the characters/ folder.

Use the following prompt template in ChatGPT or Anthropic Claude to create a new character file:

````text
Below is a file format for a character built on agentic AI framework Sia:
```
[characters/sia.json file contents]
```

Your role is to create another character based on my description below.

Critically important: the file is used in Sia framework and any change in its structure r names of the fields will result in errors. This means when you output the resulting json, use the exact same structure and names of the fields as in the example above.

Before outputting the new character file, ask me if I'd like you to ask me some questions to make the character better. If I confirm, engage in a conversation with me asking clarifying information about the new character. Once I confirm I need the new character file, provide it to me.

Here's the information about my new character:

[freeform description of the character]
````

Example of a conversation to create a character: https://chatgpt.com/share/674bb0c0-5690-8003-890a-5fa990dbc281

Update twitter_username if needed to the one you will use.

### 5. Rename .env.example to .env and fill in the values.
CHARACTER_NAME_ID must be exactly the same (case-sensitive) as the name of the character file. Example: aingrymarketer.character.json -> CHARACTER_NAME_ID=aingrymarketer.

### 6. Rename .gitignore.example to .gitignore.

### 7. Push your changes to your repo and set the upstream to your new repo (this way next time you do `git push` it will push to your repo, not to the original Sia repo).

Example:
```
git push -u aingry main
```

#### 7.1. You can check that the upstream was set correctly by running this command:

Example:
```
git remote -v
```

### 8. Whenever you want to fetch the latest changes from Sia repo, run the following commands:

```
git fetch upstream
git merge upstream/main
```

# Deploying AI agent

## On Render.com

Use the following instruction: https://render.com/docs/background-workers

Specific instructions for deploying Sia agent:
- when deploying, select the repo you created in 'Creating new AI agent using Sia framework'
- environment variables - click on "Add from .env" and insert the content of .env file you have locally in the repo folder.
