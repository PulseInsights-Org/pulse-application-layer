"""
AI prompts for entity and relationship extraction.
Based on pulse implementation, adapted for pulse-application-layer.
"""

def data_extraction_prompt(text: str) -> str:
    """
    Prompt for extracting entities and relationships from text.
    
    Args:
        text: Text to process
        
    Returns:
        Formatted prompt string
    """
    return f"""
    ## Background
    You are an NLP expert tasked with extracting structured knowledge graph data from a text corpus of organizational activity logs.
    ---
    ## Task
    From the provided text corpus, identify three types of entities:
    1. **Event** — A real-world occurrence such as a message, meeting, conversation, opinion, description of a topic, question/answer, or statement.  
    - Merge multiple sentences about the same occurrence into a **single Event entity**.  
    - Use a short but descriptive name summarizing the event.  
    - Each Event must have a clearly identifiable action and subject.
    ## Additional Metadata
        - For each Event, also extract a **Topic** — the high-level subject or category the event is about (e.g., "Feature X Deployment", "Incident Response", "Product Launch").  
        - Topics should be concise, human-readable, and reusable for grouping.
    
    2. **Actor** — A specific individual, organization, team, or group that is involved in or mentioned in the Event.  
    - Always use canonical names (full name for people, official name for orgs).  
    - Merge aliases or abbreviations into one canonical entity.  
    - Ignore generic roles (e.g., "developer", "team") unless tied to a specific person/org.
    
    3. **Time** — An exact or specific date/time when the event occurred.  
    - Use absolute times only (no purely relative terms like "yesterday").  
    - Return in ISO 8601 format (`YYYY-MM-DDTHH:MM:SSZ`) if both date & time are present, or `YYYY-MM-DD` if only date is present.  
    - If multiple absolute times are mentioned for the same event, select the one most relevant to the occurrence.
    - **IMPORTANT**: Do not interpret meeting time markers (e.g., "02:42", "21:36") as actual timestamps. These are recording time markers, not event occurrence times.
    - Only extract actual dates or timestamps mentioned in the content (e.g., "meeting on January 15th", "deadline by Friday").
    - If no actual dates are mentioned, do not create Time entities.
    ---
    ## Steps
    1. **Entity Extraction**
    - For each identified entity, extract:
        - `entity_name`: canonical name or descriptive event label.
        - `entity_type`: one of `Event`, `Actor`, `Time`.
        - `entity_description`: detailed description of what the entity is and its role in the text.
        - `topic`: only if `entity_type` is `Event`.

    2. **Relationship Extraction**
    - Identify all pairs of entities that are *clearly related*.
    - Only create relationships between entities **listed in the entities array in step 1**.
    - Use these relationship types:
        - `PERFORMED` — Actor → Event (Actor performed or triggered the Event)
        - `DISCUSSING` — Actor → Event (Actor discussed or commented on Event)
        - `OCCURRED_AT` — Event → Time (Event happened at Time)
        - `RELATED_TO` — Event ↔ Event or Event ↔ Topic (Events/Topics are related)
    - Each relationship must include:
        - `source_entity`: name of the source entity (exact from step 1)
        - `target_entity`: name of the target entity (exact from step 1)
        - `relationship_type`: one of the defined types
        - `relationship_description`: explanation of why these entities are connected
        - `relationship_strength`: confidence score between 0 and 1
    - If an exact match for either `source_entity` or `target_entity` is not found in the entities list, **skip that relationship**.
    ---
    ## Validation Rules
        - No invented entities — all must come from the text.
        - `source_entity` and `target_entity` **must** match exactly with one of the `entity_name` values in `entities`.
        - If the relationship cannot meet this rule, it must be omitted.
        - Do not include any text outside of the JSON.
    ---
    ## Output format
    Return JSON in this structure:
    {{
    "entities": [
        {{
        "entity_name": "<entity_name>",
        "entity_type": "<Event|Actor|Time>",
        "entity_description": "<detailed description>",
        "topic": "<topic>"  # only if entity_type is Event
        }}
        ...
    ],
    "relationships": [
        {{
        "source_entity": "<source_entity>",
        "target_entity": "<target_entity>",
        "relationship_type": "<PERFORMED|DISCUSSING|OCCURRED_AT|RELATED_TO>",
        "relationship_description": "<why they are related>",
        "relationship_strength": <float between 0 and 1>
        }}
        ...
    ]
    }}
    ---
    ## Text corpus
    {text}
    """


def topic_normalization_prompt(topics: list, topic: str) -> str:
    """
    Prompt for normalizing topic names.
    
    Args:
        topics: List of existing topics
        topic: New topic to normalize
        
    Returns:
        Formatted prompt string
    """
    return f"""
    #Background 
    You are classification expert. You need to classify the topic into existing topic list if it exists, otherwise create a new topic.
    ---
    #Task
    You will be provided with a list of existing topics and a new topic generated. These topics are topics of an event which specifies what is the event about.
    You need to normalize the new topic by either classifying it into the existing topics or creating a new topic.
    Note : If topic list is None, output the new topic as it is.
    ---
    ## Normalization rule
    - Return the topic in **lowercase** and **trimmed** form.

    ## Output format
    {{
    "topic": "<normalized_topic>"
    }}
    ---
    ## Existing topics
    {topics}
    ---
    ## New topic
    {topic}
    """


def summarization_prompt(text: str, focus: str = "general") -> str:
    """
    Prompt for generating text summaries.
    
    Args:
        text: Text to summarize
        focus: What to focus on in the summary
        
    Returns:
        Formatted prompt string
    """
    return f"""
    Please provide a comprehensive summary of the following text:
    
    Focus: {focus}
    
    Text:
    {text}
    
    Please provide:
    1. A concise title that captures the main topic
    2. A detailed summary that covers the key points
    3. Any important details, decisions, or action items mentioned
    
    Format your response as a clear, structured summary.
    """
