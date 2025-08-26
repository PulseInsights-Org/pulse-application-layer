from google import genai
from app.core.tools import GeminiTools
from google.genai.types import FunctionDeclaration
from google.genai import types 
from app.core.pulse_prompt import prompt_for_retrieval

class PulseLive():
    
    def __init__(self,  tools : GeminiTools, api_key = "AIzaSyBUjH-PkLSZzyDxFXeTlTw9s8PaZq2nNPc"):
        self.client = genai.Client(api_key=api_key)
        self.model = "gemini-live-2.5-flash-preview"
        self.tools = []
        self.define_tools()
        self.config = {
            "response_modalities": ["TEXT"],
            "output_audio_transcription": {},
            "temperature": 0.5,
            "tools" : self.tools,
            "system_instruction": prompt_for_retrieval(),
        }
        self.tool_executor = tools
        self.conversation_history = []
        self.chat_history = []
        self.response = ""
    
    async def _async_enumerate(self, aiterable):
        n = 0
        async for item in aiterable:
            yield n, item
            n += 1
    
    def define_tools(self):
        connections_retrieval_tool = FunctionDeclaration(
            name="connections_retrieval_tool",
            description="Fetch all the related information of one or many events",
            parameters={
                "type": "object",
                "properties": {
                    "event_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of event names of which connections should be fetched"
                    }
                },
                "required": ["event_names"],
            }
        )
        
        pc_retrieval_tool = FunctionDeclaration(
            name="pc_retrieval_tool",
            description="Fetch top relevant main events from Pinecone vector store using query text",
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The natural language query to search relevant main events"
                    }
                },
                "required": ["query"],
            }
        )
        
        self.tools = [{"function_declarations": [
            pc_retrieval_tool,
            connections_retrieval_tool,
        ]}]
    
    async def connect_to_gemini(self, text):
        self.response = ""
        
        async with self.client.aio.live.connect(
            model = self.model,
            config=self.config,
        ) as connection : 
            recent_turns = self.chat_history[-5:] if len(self.chat_history) > 5 else self.chat_history
            history_lines = []
            for t in recent_turns:
                try:
                    role = t.get("role", "user")
                    parts = t.get("parts", [])
                    content_text = parts[0].get("text") if parts and isinstance(parts[0], dict) else ""
                    history_lines.append(f"{role}: {content_text}")
                except Exception:
                    pass

            composed = ""
            if history_lines:
                composed = "Conversation history:\n" + "\n".join(history_lines) + "\n\n"
            composed += f"Question: {text}"
            
            await connection.send_client_content(
                turns={"role": "user", "parts": [{"text": composed}]}, turn_complete=True
            )

            current_turn = {"role": "user", "parts": [{"text": text}]}
            self.chat_history.append(current_turn)
            if len(self.chat_history) > 5:
                self.chat_history = self.chat_history[-5:]
            
            turn = connection.receive()
            async for n, response in self._async_enumerate(turn):
                
                if response.server_content:
                    if response.text is not None:
                        self.response += response.text
                        print(f"Chunk received: {response.text}", end="", flush=True)
                            
                elif response.tool_call:
                    try:
                        function_responses = []
                        for fc in response.tool_call.function_calls:
                            
                            function_name = fc.name
                            function_args = fc.args
                            print("function called by gemini", function_name)
                            
                            data = None  # ensure initialized to avoid unbound local on exceptions
                            try:
                                if function_name == "connections_retrieval_tool":
                                    event = (function_args or {}).get("event_names")
                                    data = self.tool_executor.get_event_connections(event)
                                    
                                elif function_name == "pc_retrieval_tool":
                                    query = (function_args or {}).get("query")
                                    data = self.tool_executor.pc_retrieval_tool(query)
                                
                                else:
                                    data = {"error": f"Unknown function: {function_name}"}
                                
                                if data is not None:
                                    print(data)
                                    
                                function_response = types.FunctionResponse(
                                    id=fc.id,
                                    name=fc.name,
                                    response={"result": data}
                                )
                                
                                function_responses.append(function_response)
                            
                            except Exception as tool_error:
                                
                                print(f"Error executing tool {function_name}: {tool_error}")
                                error_response = types.FunctionResponse(
                                    id=fc.id,
                                    name=fc.name,
                                    response={"error": str(tool_error)}
                                )
                                function_responses.append(error_response)
                        
                        if function_responses:
                            print("sending gemini function response...")
                            await connection.send_tool_response(function_responses=function_responses)
                    except Exception as e:
                        print(f"Error processing tool calls: {e}")
                        
                if n == 0:
                    try:
                        if (response.server_content and 
                            response.server_content.model_turn and 
                            response.server_content.model_turn.parts and 
                            len(response.server_content.model_turn.parts) > 0 and
                            response.server_content.model_turn.parts[0].inline_data):
                            print(f"MIME type: {response.server_content.model_turn.parts[0].inline_data.mime_type}")
                        else:
                            print("No inline data available in response")
                    except AttributeError as e:
                        print(f"Error accessing response data: {e}")
            
            
                turn_complete = bool(getattr(getattr(response, 'server_content', None), 'turn_complete', False))
                
                if turn_complete:
                    print(f"\n[Model turn complete] Final response: {self.response}")

                    self.conversation_history.append({
                        "role": "model",
                        "content": self.response,
                        "type": "text_response"
                    })
                    self.chat_history.append({
                        "role": "model",
                        "parts": [{"text": self.response}]
                    })
                    
                    if len(self.chat_history) > 5:
                        self.chat_history = self.chat_history[-5:]
                    return self.response
    
