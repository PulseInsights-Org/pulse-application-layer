"""
Gemini AI model service for text processing.
Simplified version based on pulse implementation.
"""

import google.generativeai as genai
from typing import Dict, Any, Optional
from app.core.config import config
import logging

logger = logging.getLogger(__name__)

class GeminiModel:
    """Wrapper for Google Gemini AI model."""
    
    def __init__(self, model_name: Optional[str] = None, api_key: Optional[str] = None):
        """
        Initialize Gemini model.
        
        Args:
            model_name: Model name to use (defaults to config)
            api_key: API key (defaults to config)
        """
        self.model_name = model_name or config.get_secret("model_name", "gemini-1.5-flash")
        self.api_key = api_key or config.get_secret("model_api_key")
        
        if not self.api_key:
            raise ValueError("Gemini API key not found in configuration")
        
        # Configure Gemini
        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel(self.model_name)
        
        logger.info(f"✅ Gemini model initialized: {self.model_name}")
    
    def get_response(self, prompt: str, temperature: float = 0.1) -> Any:
        """
        Get response from Gemini model.
        
        Args:
            prompt: Text prompt to send to the model
            temperature: Creativity level (0.0 to 1.0)
            
        Returns:
            Model response object
        """
        try:
            response = self.model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=temperature,
                    max_output_tokens=8192,
                )
            )
            
            if response.text:
                return response
            else:
                logger.warning("Empty response from Gemini model")
                return type('Response', (), {'text': ''})()
                
        except Exception as e:
            logger.error(f"Error getting Gemini response: {e}")
            raise RuntimeError(f"Gemini API error: {str(e)}")
    
    def extract_entities_and_relationships(self, text: str) -> Dict[str, Any]:
        """
        Extract entities and relationships from text using Gemini.
        
        Args:
            text: Text to process
            
        Returns:
            Dictionary with entities and relationships
        """
        from app.prompts.extraction import data_extraction_prompt
        
        prompt = data_extraction_prompt(text)
        response = self.get_response(prompt, temperature=0.1)
        
        # Parse the response (assuming it's JSON)
        import json
        import re
        
        try:
            # Extract JSON from response
            json_match = re.search(r'\{[\s\S]*\}', response.text)
            if json_match:
                return json.loads(json_match.group(0))
            else:
                logger.error("No JSON found in Gemini response")
                return {"entities": [], "relationships": []}
                
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Gemini response as JSON: {e}")
            return {"entities": [], "relationships": []}
    
    def generate_summary(self, text: str, existing_summary: str = "") -> str:
        """
        Generate a summary of the text.
        
        Args:
            text: Text to summarize
            existing_summary: Existing summary to build upon
            
        Returns:
            Generated summary
        """
        prompt = f"""
        Please provide a concise summary of the following text:
        
        {text}
        
        {f"Build upon this existing summary: {existing_summary}" if existing_summary else ""}
        
        Provide a clear, structured summary that captures the key points.
        """
        
        response = self.get_response(prompt, temperature=0.3)
        return response.text.strip() if response.text else ""
